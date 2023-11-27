"""
    Copyright 2023 Budapest University of Technology and Economics

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
import os
import re
import subprocess
import sys
import tempfile
import traceback
import argparse

from pycparser import parse_file, c_generator

from Exceptions import KnownErrorVerdict
from tweaks import reach_error, fix_inline, fix_struct_def
from witness2ast import apply_witness


def translate_to_c(filename, witness, mode):
    """ Simply use the c_generator module to emit a parsed AST.
    """
    try:
        ast = parse_file(filename, use_cpp=False)
    except KnownErrorVerdict as e:
        print("Verdict: " + e.verdict)
        sys.exit(-1)
    except:
        traceback.print_exc()
        print("Verdict: Parsing failed")
        sys.exit(-1)

    try:
        apply_witness(ast, filename, witness)
    except KnownErrorVerdict as e:
        print("Verdict: " + e.verdict)
        sys.exit(-1)
    except:
        traceback.print_exc()
        print("Verdict: Incompatible witness")
        sys.exit(-1)

    try:
        fix_inline(ast)
        fix_struct_def(ast)
        reach_error(ast)
        generator = c_generator.CGenerator()
        with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as tmp:
            tmp.write(generator.visit(ast).encode())
            tmp.flush()
            print(tmp.name)
            bin_name = tmp.name[:-2]
            print("Compilation started")
            result = subprocess.run(['gcc', '-w', tmp.name, os.path.dirname(__file__) + os.sep + 'svcomp.c', "-o", bin_name],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.stdout:
                print(result.stdout.decode())
            if result.stderr:
                print(result.stderr.decode())
            print(f"Compilation ended (exit code {result.returncode})")
            if result.returncode != 0:
                print("Verdict: Compilation error")
                sys.exit(-1)
            codes = {}
            for i in range(100):
                try:
                    result = subprocess.run([bin_name], capture_output=True, text=True)
                    print("Execution started")
                    reached_error = result.returncode == 74
                    if not reached_error and result.stdout:
                        for line in result.stdout.split("\n"):
                            if "Reached error!" in line:
                                reached_error = True
                                break
                    if result.stdout:
                        print(result.stdout)
                    if result.stderr:
                        print(result.stderr)
                    print(f"Execution ended (exit code {result.returncode})")
                    code = -1 if reached_error else 0
                    codes[code] = codes[code] + 1 if code in codes else 1
                    if mode == "strict" and not reached_error:
                        break
                    if mode == "permissive" and reached_error:
                        break
                except subprocess.TimeoutExpired:
                    print(f"Execution ended (timeout)")

            try:
                os.remove(bin_name)
            except:
                traceback.print_exc()

            print(codes)
            may_not = False
            may = False
            if 0 in codes:
                may_not = True
            if -1 in codes:
                may = True
            if may_not and may:
                print("Verdict: SOMETIMES")
            elif may_not:
                print("Verdict: NEVER")
            elif may:
                print("Verdict: ALWAYS")
            else:
                print("Verdict: TIMEOUT")
    except:
        traceback.print_exc()
        print("Verdict: Unknown error")
        sys.exit(-1)


def hacks(content):
    def replace_with_spaces_str(match_str, offset=0):
        parens = 0
        for i, c in enumerate(match_str):
            if c == "(":
                parens = parens + 1
            elif c == ")":
                parens = parens - 1
                if parens < 0:
                    return ' ' * (i - offset) + match_str[i:]
                elif parens == 0:
                    return ' ' * (i - offset + 1) + match_str[i + 1:]
        return ' ' * (len(match_str) - offset)

    def replace_with_spaces(match):
        return replace_with_spaces_str(str(match.group(0)))

    def replace_with_zero_padded(match):
        return '0' + replace_with_spaces_str(str(match.group(0)), 1)

    last_content = ""
    while last_content != content:
        last_content = content
        content = re.sub(r'//[^\n]*', replace_with_spaces, content)
        content = re.sub(r'/\*.*\*/', replace_with_spaces, content)
        content = re.sub(r'__attribute__[ \r\n]*\(.*\)', replace_with_spaces, content)
        content = re.sub(r'__asm__[ \r\n]*\(.*\)', replace_with_spaces, content)
        content = re.sub(r'asm volatile[ \r\n]*\(.*\)', replace_with_spaces, content)
        content = re.sub(r'asm[ \r\n]*\(.*\)', replace_with_spaces, content)
        content = re.sub(r'__extension__[ \r\n]*\(.*\)', replace_with_zero_padded, content)
        content = re.sub(r'__extension__', replace_with_spaces, content)
        content = re.sub(r'__inline', replace_with_spaces, content)
        content = re.sub(r'__restrict', replace_with_spaces, content)
        content = re.sub(r'__builtin_va_list', 'int              ', content)
        content = re.sub(r'__signed__', '  signed  ', content)
        content = re.sub(r'\([ \r\n]*\{.*}[ \r\n]*\)', replace_with_zero_padded, content)
    return content


def perform_hacks(filename, func):
    with open(filename, "r") as f:
        with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as tmp:
            tmp.write(hacks(f.read()).encode())
            tmp.flush()
            func(tmp.name)


def parse_arguments():
    parser = argparse.ArgumentParser(description='Parse command line arguments for ConcurrentWitness2Test.py')

    parser.add_argument('--version', action='version', version='ConcurrentWitness2Test 1.0')
    parser.add_argument('input_file', metavar='<input.c>', type=str, help='Input file (.c)')
    parser.add_argument('--witness', '--graphml-witness', metavar='<witness.graphml>', type=str, required=True, help='Witness file (graphml)')
    parser.add_argument('--mode', choices=['strict', 'normal', 'permissive'], default='normal',
                        help='Mode (default: normal)')

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    if not args.input_file:
        print('Please provide input file.')
        argparse.ArgumentParser().print_help()
        sys.exit(-1)

    if not args.witness:
        print('Please provide witness file.')
        argparse.ArgumentParser().print_help()
        sys.exit(-1)

    perform_hacks(args.input_file, lambda x: translate_to_c(x, args.witness, args.mode))