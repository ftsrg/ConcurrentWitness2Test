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

import networkx as nx
from pycparser.c_ast import (
    Compound,
    If,
    While,
    DoWhile,
    For,
    FuncDef,
    FuncCall,
    NodeVisitor,
    ID,
    ExprList,
    Constant,
    Assignment,
)
import re

from Exceptions import KnownErrorVerdict


def get_offset_of_line(c_file, line):
    with open(c_file, "r") as f:
        for i in range(1, line):
            f.readline()
        return f.tell()


def get_line_of_offset(c_file, offset):
    with open(c_file, "r") as f:
        i = 0
        line = ""
        while f.tell() <= offset:
            line = f.readline()
            i = i + 1
        return i, len(line) - (f.tell() - offset)


def get_coords(c_file, startline=None, endline=None, startoffset=None, endoffset=None):
    if not endline and startline:
        endline = startline

    if not startoffset and startline:
        startoffset = get_offset_of_line(c_file, int(startline))

    if not endoffset and endline:
        endoffset = get_offset_of_line(c_file, int(endline) + 1)

    if endoffset:
        with open(c_file, "r") as f:
            f.seek(int(startoffset))
            content = f.read(int(endoffset) - int(startoffset) - 1)
            startline, column = get_line_of_offset(c_file, int(startoffset))
            return {
                "startline": int(startline),
                "column": int(column),
                "endline": int(endline),
                "length": int(endoffset) - int(startoffset) + 1,
                "content": content,
            }
    return None


def find_nondet_assignment_on_line(ast, target_line):
    class LineVisitor(NodeVisitor):
        def __init__(self, target_line):
            self.target_line = target_line
            self.found = False
            self.statement = None
            self.parent = None

        def visit(self, node):
            if not self.found:
                super().visit(node)

        def visit_Compound(self, node):
            if self.found:
                return
            for stmt in node.block_items if node.block_items else [node]:
                if hasattr(stmt, "coord") and stmt.coord:
                    line = stmt.coord.line
                    if (
                        line >= self.target_line
                        and type(stmt) == Assignment
                        and type(stmt.rvalue) == FuncCall
                        and "__VERIFIER_nondet" in stmt.rvalue.name.name
                    ):
                        self.statement = stmt
                        self.parent = node
                        self.found = True
                        return
                self.generic_visit(stmt)

    line_visitor = LineVisitor(target_line)
    line_visitor.visit(ast)

    if line_visitor.statement:
        return line_visitor.statement, line_visitor.parent
    else:
        return None, None


def find_first_statement_on_line(ast, target_line):
    class LineVisitor(NodeVisitor):
        def __init__(self, target_line):
            self.target_line = target_line
            self.found = False
            self.statement = None
            self.parent = None

        def visit(self, node):
            if not self.found:
                super().visit(node)

        def visit_Compound(self, node):
            if self.found:
                return
            for stmt in node.block_items if node.block_items else [node]:
                if hasattr(stmt, "coord") and stmt.coord:
                    line = stmt.coord.line
                    if line >= self.target_line:
                        self.statement = stmt
                        self.parent = node
                        self.found = True
                        return
                self.generic_visit(stmt)

    line_visitor = LineVisitor(target_line)
    line_visitor.visit(ast)

    if line_visitor.statement:
        return line_visitor.statement, line_visitor.parent
    else:
        return None, None


def extract_metadata(witnessfile, c_file):
    witness = nx.read_graphml(witnessfile)
    if witness.graph["witness-type"] != "violation_witness":
        raise KnownErrorVerdict("Correctness witness")
    ret = []

    keys = {k for node in witness.nodes for k in witness.nodes[node].keys()}
    entry_key = "entry" if "entry" in keys else "isEntryNode"
    sink_key = "sink" if "sink" in keys else "isSinkNode"

    entry_nodes = list(nx.get_node_attributes(witness, entry_key).keys())
    if len(entry_nodes) == 0:
        entry_nodes = list(
            set([u for u, deg in witness.in_degree() if not deg])
            - set([u for u, deg in witness.out_degree() if not deg])
        )
        if len(entry_nodes) == 0:
            raise KnownErrorVerdict("No entry node")

    if len(entry_nodes) > 1:
        raise KnownErrorVerdict("Multiple entry nodes")

    node = entry_nodes[0]

    sink_nodes = set(nx.get_node_attributes(witness, sink_key).keys())

    while len(witness.out_edges(node)) > 0:
        out_edges = list(
            filter(lambda x: x[1] not in sink_nodes, witness.out_edges(node))
        )
        if len(out_edges) > 1:
            raise KnownErrorVerdict("Has branching")
        edge = list(out_edges)[0]
        attrs = witness.get_edge_data(edge[0], edge[1])

        startline = attrs["startline"] if "startline" in attrs else None
        endline = attrs["endline"] if "endline" in attrs else None
        startoffset = attrs["startoffset"] if "startoffset" in attrs else None
        endoffset = attrs["endoffset"] if "endoffset" in attrs else None

        coords = get_coords(c_file, startline, endline, startoffset, endoffset)
        metadata = {
            key: attrs[key]
            for key in ["assumption", "control", "threadId", "createThread"]
            if key in attrs
        }
        ret.append((coords, metadata))
        node = edge[1]

    return ret


nondet_return_types = {
    "__VERIFIER_nondet_bool": "_Bool",
    "__VERIFIER_nondet_char": "char",
    "__VERIFIER_nondet_charp": "char*",
    "__VERIFIER_nondet_const_char_pointer": "const char*",
    "__VERIFIER_nondet_double": "double",
    "__VERIFIER_nondet_float": "float",
    "__VERIFIER_nondet_int": "int",
    "__VERIFIER_nondet_long": "long",
    "__VERIFIER_nondet_longlong": "long long",
    "__VERIFIER_nondet_pointer": "void*",
    "__VERIFIER_nondet_short": "short",
    "__VERIFIER_nondet_size_t": "size_t",
    "__VERIFIER_nondet_u16": "uint16_t",
    "__VERIFIER_nondet_u32": "uint32_t",
    "__VERIFIER_nondet_u8": "uint8_t",
    "__VERIFIER_nondet_uchar": "unsigned char",
    "__VERIFIER_nondet_uint": "unsigned int",
    "__VERIFIER_nondet_uint128": "unsigned __int128",
    "__VERIFIER_nondet_ulong": "unsigned long",
    "__VERIFIER_nondet_ulonglong": "unsigned long long",
    "__VERIFIER_nondet_unsigned": "unsigned",
    "__VERIFIER_nondet_unsigned_char": "unsigned char",
    "__VERIFIER_nondet_unsigned_int": "unsigned int",
    "__VERIFIER_nondet_ushort": "unsigned short",
}


def apply_witness(ast, c_file, witnessfile):
    funcdefs = {}
    for node in ast.ext:
        if isinstance(node, FuncDef):
            funcdefs[node.decl.name] = node.body
    metadata = extract_metadata(witnessfile, c_file)
    threadid = metadata[0][1]["threadId"] if "threadId" in metadata[0][1] else 0
    i = 0
    # TODO not perfect regex, but hard to solve well for everything ( e.g., assumption: !(var == 1) and variants )
    assumption_pattern = r"([^\s]*)\s*==\s*([^\s]*)"

    for coords, data in metadata:
        # TODO current implementation is limited: will not work if single assignment executes 1+ time (e.g., in a loop)
        if "assumption" in data and "content" in coords and "startline" in coords:
            nondet_assign_node, first_parent = find_nondet_assignment_on_line(
                ast, coords["startline"]
            )
            if nondet_assign_node is not None:
                assumptions = {}
                matches = re.findall(assumption_pattern, data["assumption"])
                for i, (varname, value) in enumerate(matches, 1):
                    assumptions[varname] = value

                varname = nondet_assign_node.lvalue.name
                if any(varname in d for d in assumptions):
                    # TODO change nondet call to value
                    if nondet_assign_node.rvalue.name.name in nondet_return_types:
                        ret_type = nondet_return_types[
                            nondet_assign_node.rvalue.name.name
                        ]
                        nondet_assign_node.rvalue = Constant(
                            type=ret_type, value=assumptions[varname]
                        )
        elif (
            (data["threadId"] if "threadId" in data else threadid) != threadid
            and coords
            and "startline" in coords
        ):
            threadid = data["threadId"] if "threadId" in data else threadid
            nondet_assign_node, first_parent = find_first_statement_on_line(
                ast, coords["startline"]
            )

            yield_func = FuncCall(
                ID("yield"),
                ExprList(
                    [
                        Constant(type="int", value=f"{i}"),
                        Constant(type="int", value=f"{threadid}"),
                    ]
                ),
            )
            release_func = FuncCall(
                ID("release"),
                ExprList(
                    [
                        Constant(type="int", value=f"{i}"),
                        Constant(type="int", value=f"{threadid}"),
                    ]
                ),
            )

            i = i + 1
            first_index = first_parent.block_items.index(nondet_assign_node)
            first_parent.block_items.insert(first_index, yield_func)
            if isinstance(nondet_assign_node, (Compound, While, DoWhile, For)):
                nondet_assign_node.stmt = Compound(
                    block_items=[release_func, nondet_assign_node.stmt]
                )
            elif isinstance(nondet_assign_node, If):
                if nondet_assign_node.iftrue:
                    nondet_assign_node.iftrue = Compound(
                        block_items=[release_func, nondet_assign_node.iftrue]
                    )
                if nondet_assign_node.iffalse:
                    nondet_assign_node.iffalse = Compound(
                        block_items=[release_func, nondet_assign_node.iffalse]
                    )
            else:
                first_parent.block_items.insert(first_index + 2, release_func)
