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

import re


def hacks(content):
    """Blanks out GNU extensions and constructs pycparser can't handle
    (inline asm, statement expressions, __attribute__), preserving line
    numbers so witness locations still line up."""

    def replace_with_spaces_str(match_str, offset=0):
        parens = 0
        for i, c in enumerate(match_str):
            if c == "(":
                parens = parens + 1
            elif c == ")":
                parens = parens - 1
                if parens < 0:
                    return " " * (i - offset) + match_str[i:]
                elif parens == 0:
                    return " " * (i - offset + 1) + match_str[i + 1 :]
        return " " * (len(match_str) - offset)

    def replace_with_spaces(match):
        return replace_with_spaces_str(str(match.group(0)))

    def replace_with_spaces_full(match):
        # Unlike replace_with_spaces, blanks the *entire* match regardless of
        # paren-balance. Comments can't contain trailing code that needs
        # preserving (// is bounded by \n, /* */ by its own closing marker),
        # so paren-counting here only misfires on a comment that happens to
        # contain a balanced parenthesized expression, e.g.
        # "// so 'if (x == 1)' is taken" -- replace_with_spaces would stop
        # right after the ')', leaving a stray quote that fails to lex.
        return " " * len(match.group(0))

    def replace_with_zero_padded(match):
        return "0" + replace_with_spaces_str(str(match.group(0)), 1)

    last_content = ""
    while last_content != content:
        last_content = content
        content = re.sub(r"//[^\n]*", replace_with_spaces_full, content)
        content = re.sub(r"/\*.*\*/", replace_with_spaces_full, content)
        content = re.sub(r"__attribute__[ \r\n]*\(.*\)", replace_with_spaces, content)
        content = re.sub(r"__asm__[ \r\n]*\(.*\)", replace_with_spaces, content)
        content = re.sub(r"asm volatile[ \r\n]*\(.*\)", replace_with_spaces, content)
        content = re.sub(r"asm[ \r\n]*\(.*\)", replace_with_spaces, content)
        content = re.sub(
            r"__extension__[ \r\n]*\(.*\)", replace_with_zero_padded, content
        )
        content = re.sub(r"__extension__", replace_with_spaces, content)
        content = re.sub(r"__inline", replace_with_spaces, content)
        content = re.sub(r"__restrict", replace_with_spaces, content)
        content = re.sub(r"__builtin_va_list", "int              ", content)
        content = re.sub(r"__signed__", "  signed  ", content)
        content = re.sub(
            r"\([ \r\n]*\{.*}[ \r\n]*\)", replace_with_zero_padded, content
        )
    return content
