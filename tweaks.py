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
from pycparser.c_ast import FuncDef, Decl, Struct, TypeDecl


def reach_error(ast):
    for node in ast.ext:
        if isinstance(node, FuncDef) and node.decl.name == "reach_error":
            func_name = node.decl.name
            extern_decl = Decl(
                name=func_name,
                quals=[],
                storage=["extern"],
                funcspec=[],
                type=node.decl.type,
                init=None,
                bitsize=None,
            )
            ast.ext.remove(node)
            ast.ext.append(extern_decl)


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
        inline_def.decl.funcspec = ["extern", "inline"]


# This is a problem with pycparser
def fix_struct_def(ast):
    struct_decls = set()
    for node in ast.ext:
        if (
            isinstance(node, Decl)
            and isinstance(node.type, TypeDecl)
            and isinstance(node.type.type, Struct)
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
