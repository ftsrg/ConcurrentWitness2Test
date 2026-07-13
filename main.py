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
import subprocess
import sys
import tempfile
import traceback
import argparse

from pycparser import preprocess_file, CParser

from Exceptions import KnownErrorVerdict
from hacks import hacks
from tweaks import (
    reach_error,
    fix_inline,
    fix_struct_def,
    declare_schedule_functions,
    LineDirectiveCGenerator,
)
from witness2ast import apply_witness

HEADERS_DIR = os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "headers"

# pycparser only understands standard C, so GNU extensions used by the stub
# headers (and by real system headers, for anything the stubs don't cover)
# are preprocessed away rather than parsed.
CPP_GNU_COMPAT_ARGS = [
    "-D__attribute__(x)=",
    "-D__extension__=",
    "-D__restrict=",
    "-D__restrict__=",
    "-D__inline=inline",
    "-D__inline__=inline",
    "-D__const=const",
    "-D__signed__=signed",
    "-D__volatile__=volatile",
    "-D__typeof__(x)=void*",
    "-D__builtin_va_list=void*",
]


def translate_to_c(filename, witness, mode, timeout):
    """Apply the witness to the parsed AST, then compile and run the result."""
    try:
        text = preprocess_file(
            filename,
            cpp_path="cpp",
            cpp_args=["-I" + HEADERS_DIR] + CPP_GNU_COMPAT_ARGS,
        )
        ast = CParser().parse(text, filename)
    except KnownErrorVerdict as e:
        print("Verdict: " + e.verdict)
        sys.exit(-1)
    except:
        traceback.print_exc()
        print("Verdict: Parsing failed")
        sys.exit(-1)

    try:
        parsed_witness = apply_witness(
            ast, filename, witness, input_only=(mode == "INPUT_ONLY")
        )
    except KnownErrorVerdict as e:
        print("Verdict: " + e.verdict)
        sys.exit(-1)
    except:
        traceback.print_exc()
        print("Verdict: Incompatible witness")
        sys.exit(-1)

    # For a no-data-race witness the violation is observed by the thread
    # sanitizer at runtime instead of a reach_error() call.
    data_race = parsed_witness.data_race
    if data_race:
        print("Data race witness: compiling with ThreadSanitizer")

    # For a no-overflow witness the violation is an integer overflow detected
    # by UBSan at runtime.
    no_overflow = parsed_witness.no_overflow
    if no_overflow:
        print("Overflow witness: compiling with UBSan")

    # For a memory-safety witness the violation is an invalid memory access
    # (e.g. a use-after-free) detected by AddressSanitizer at runtime.
    memory_safety = parsed_witness.memory_safety
    if memory_safety:
        print("Memory-safety witness: compiling with AddressSanitizer")

    try:
        fix_inline(ast)
        fix_struct_def(ast)
        reach_error(ast)
        declare_schedule_functions(ast)
        generator = LineDirectiveCGenerator()
        with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as tmp:
            tmp.write(generator.visit(ast).encode())
            tmp.flush()
            print(tmp.name)
            bin_name = tmp.name[:-2]
            print("Compilation started")
            result = subprocess.run(
                [
                    "gcc",
                    "-w",
                    "-Wno-implicit-function-declaration",
                    "-pthread",
                ]
                + (["-fsanitize=thread", "-g"] if data_race else [])
                + (
                    ["-fsanitize=undefined", "-fno-sanitize-recover=all", "-g"]
                    if no_overflow
                    else []
                )
                + (["-fsanitize=address", "-g"] if memory_safety else [])
                + [
                    tmp.name,
                    os.path.dirname(os.path.abspath(sys.argv[0])) + os.sep + "svcomp.c",
                    "-o",
                    bin_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.stdout:
                print(result.stdout.decode())
            if result.stderr:
                print(result.stderr.decode())
            print(f"Compilation ended (exit code {result.returncode})")
            if result.returncode != 0:
                print("Verdict: Compilation error")
                sys.exit(-1)
            env = os.environ.copy()
            if data_race:
                # Stop at the first race and reuse the reach_error() exit
                # code, so race detection follows the same path below.
                env["TSAN_OPTIONS"] = "halt_on_error=1 exitcode=74"
            if no_overflow:
                # UBSan: halt on first overflow and exit with the same
                # sentinel code 74 as reach_error(), so the verdict logic
                # below is reused unchanged.
                env["UBSAN_OPTIONS"] = "halt_on_error=1:exitcode=74:print_stacktrace=1"
            if memory_safety:
                # ASan: halt on the first invalid access and exit with the same
                # sentinel code 74 as reach_error(), so the verdict logic below
                # is reused unchanged.
                env["ASAN_OPTIONS"] = "halt_on_error=1:exitcode=74"
            codes = {}
            for i in range(100):
                try:
                    print("Execution started")
                    result = subprocess.run(
                        [bin_name],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=env,
                    )
                    reached_error = result.returncode == 74
                    if not reached_error and result.stdout:
                        for line in result.stdout.split("\n"):
                            if "Reached error!" in line:
                                reached_error = True
                                break
                    if (
                        not reached_error
                        and data_race
                        and result.stderr
                        and "ThreadSanitizer: data race" in result.stderr
                    ):
                        reached_error = True
                    if (
                        not reached_error
                        and no_overflow
                        and result.stderr
                        and "runtime error:" in result.stderr
                    ):
                        reached_error = True
                    if (
                        not reached_error
                        and memory_safety
                        and result.stderr
                        and "AddressSanitizer:" in result.stderr
                    ):
                        reached_error = True
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


def perform_hacks(filename, func):
    with open(filename, "r") as f:
        with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as tmp:
            tmp.write(hacks(f.read()).encode())
            tmp.flush()
            func(tmp.name)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Parse command line arguments for ConcurrentWitness2Test.py"
    )

    parser.add_argument("--version", action="version", version="2.0")
    parser.add_argument(
        "input_file", metavar="<input.c>", type=str, help="Input file (.c)"
    )
    parser.add_argument(
        "--witness",
        "--graphml-witness",
        "--yaml-witness",
        metavar="<witness.graphml|witness.yml>",
        type=str,
        required=True,
        help="Witness file; GraphML (format 1.0) and YAML (format 2.x) "
        "violation witnesses are detected automatically",
    )
    parser.add_argument(
        "--mode",
        choices=["strict", "normal", "permissive", "INPUT_ONLY"],
        default="normal",
        help="Mode (default: normal): strict stops at the first execution "
        "missing the error, permissive at the first one reaching it, "
        "normal runs all repetitions, INPUT_ONLY pins the witness' inputs "
        "(nondet values, assumptions) but leaves the thread schedule free "
        "(no blocking schedule yields; the segment counter still advances "
        "per passed segment)",
    )
    parser.add_argument(
        "--timeout",
        metavar="<seconds>",
        type=float,
        default=10.0,
        help="Timeout for a single execution of the test in seconds " "(default: 10)",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    if not args.input_file:
        print("Please provide input file.")
        argparse.ArgumentParser().print_help()
        sys.exit(-1)

    if not args.witness:
        print("Please provide witness file.")
        argparse.ArgumentParser().print_help()
        sys.exit(-1)

    perform_hacks(
        args.input_file,
        lambda x: translate_to_c(x, args.witness, args.mode, args.timeout),
    )
