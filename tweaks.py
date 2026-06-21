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

from pycparser import CParser, c_generator
from pycparser.c_ast import FuncDef, Decl, Pragma, Struct, TypeDecl


def declare_schedule_functions(ast):
    """Add explicit prototypes for the schedule-point and runtime-guard functions.

    They are otherwise called without ever being declared in the
    instrumented file (their definition only exists in svcomp.c, compiled
    separately), which relies on implicit-function-declaration being
    tolerated by the compiler.
    """
    prototypes = (
        CParser()
        .parse(
            "void __concurrentwit2test_yield(int, int);\n"
            "void __concurrentwit2test_release(int, int);\n"
            "int __c2tt_should_use_assumed(int, int);\n"
            "void __concurrentwit2test_assume(int, int);\n"
            "void *__c2tt_thread_proxy(void *);\n"
            "void *__c2tt_make_thread_arg(void *(*)(void *), void *, int);\n"
            "void __c2tt_set_expected_final_slot(int);\n"
        )
        .ext
    )
    ast.ext[0:0] = prototypes


class LineDirectiveCGenerator(c_generator.CGenerator):
    """A CGenerator that emits ``#line`` directives ahead of each original
    statement/declaration, so the regenerated (reformatted, instrumented)
    file's line numbers as seen by the compiler -- and therefore gcc
    diagnostics and UBSan/TSan runtime error locations -- match the
    *original* source file instead of this generator's own pretty-printed
    layout.

    Nodes pycparser parsed from the original source carry a ``.coord``
    (file, line); nodes witness2ast.py constructs and inserts (yield/
    release/assume calls, the rewritten pthread_create arguments, ...)
    don't, since there's no original-source line to attribute them to --
    they're left unanchored, and whichever coord-bearing node comes next
    re-anchors correctly regardless of how far the implicit line count
    drifted in between. Approximate bookkeeping (e.g. opening braces
    aren't tracked) can only produce a redundant-but-still-correct extra
    directive, never a wrong one, since every directive that *is* emitted
    always carries the node's own ground-truth coord.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._line_file = None
        self._next_line = None

    def _line_prefix(self, coord, upcoming_text):
        prefix = ""
        if coord is not None and coord.line is not None and coord.file:
            if coord.file != self._line_file or coord.line != self._next_line:
                prefix = '#line {} "{}"\n'.format(coord.line, coord.file)
                self._line_file = coord.file
                self._next_line = coord.line
        if self._next_line is not None:
            self._next_line += upcoming_text.count("\n")
        return prefix

    def _generate_stmt(self, n, add_indent=False):
        text = super()._generate_stmt(n, add_indent=add_indent)
        return self._line_prefix(getattr(n, "coord", None), text) + text

    def visit_FuncDef(self, n):
        decl_text = self.visit(n.decl)
        prefix = self._line_prefix(getattr(n, "coord", None), decl_text + "\n")
        # The body Compound's opening "{" is emitted directly by
        # visit_Compound, bypassing _generate_stmt -- so it's an untracked
        # physical line. Forget the running belief rather than risk it
        # coincidentally (and wrongly) matching the body's first statement's
        # real coord, which would suppress a directive that's actually needed.
        self._next_line = None
        self.indent_level = 0
        body = self.visit(n.body)
        if n.param_decls:
            knrdecls = ";\n".join(self.visit(p) for p in n.param_decls)
            return prefix + decl_text + "\n" + knrdecls + ";\n" + body + "\n"
        return prefix + decl_text + "\n" + body + "\n"

    def visit_FileAST(self, n):
        s = ""
        for ext in n.ext:
            if isinstance(ext, FuncDef):
                s += self.visit(ext)
                continue
            text = (
                self.visit(ext) + "\n"
                if isinstance(ext, Pragma)
                else self.visit(ext) + ";\n"
            )
            s += self._line_prefix(getattr(ext, "coord", None), text) + text
        return s


def reach_error(ast):
    for node in ast.ext:
        if isinstance(node, FuncDef) and node.decl.name == "reach_error":
            func_name = node.decl.name
            extern_decl = Decl(
                name=func_name,
                quals=[],
                align=[],
                storage=["extern"],
                funcspec=[],
                type=node.decl.type,
                init=None,
                bitsize=None,
            )
            ast.ext.remove(node)
            ast.ext.insert(0, extern_decl)


# This is a problem with some SV-COMP benchmarks
def fix_inline(ast):
    inline_defs = [
        node
        for node in ast.ext
        if isinstance(node, FuncDef)
        and "inline" in node.decl.funcspec
        and "static" not in node.decl.storage
    ]
    for inline_def in inline_defs:
        inline_def.decl.storage = ["extern"]
        inline_def.decl.funcspec = ["inline"]


# This is a problem with pycparser
def fix_struct_def(ast):
    struct_decls = set()
    for node in ast.ext:
        if (
            isinstance(node, Decl)
            and isinstance(node.type, TypeDecl)
            and isinstance(node.type.type, Struct)
            and node.type.type.name is not None  # anonymous structs are never repeats
        ):
            if node.type.type.name in struct_decls:
                node.type.type = Struct(node.type.type.name, decls=None)
            else:
                struct_decls.add(node.type.type.name)


# Known bug: pycparser cannot handle curly braces inside parentheses. Example:
# int main(){
#   int a = ({1;});
# }
# Issue: https://github.com/eliben/pycparser/issues/519
