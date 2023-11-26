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
from pycparser.c_ast import Compound, If, While, DoWhile, For, FuncDef, FuncCall, \
    NodeVisitor, ID, ExprList, Constant

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
            return {"startline": int(startline), "column": int(column), "endline": int(endline),
                    "length": int(endoffset) - int(startoffset) + 1, "content": content}
    return None


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
            for stmt in (node.block_items if node.block_items else [node]):
                if hasattr(stmt, 'coord') and stmt.coord:
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

    entry_nodes = list(nx.get_node_attributes(witness, "entry").keys())
    if len(entry_nodes) == 0:
        entry_nodes = list(set([u for u, deg in witness.in_degree() if not deg]) - set([u for u, deg in witness.out_degree() if not deg]))
        if len(entry_nodes) == 0:
            raise KnownErrorVerdict("No entry node")

    if len(entry_nodes) > 1:
        raise KnownErrorVerdict("Multiple entry nodes")

    node = entry_nodes[0]

    while len(witness.out_edges(node)) > 0:
        out_edges = witness.out_edges(node)
        if len(out_edges) > 1:
            raise KnownErrorVerdict("Has branching")
        edge = list(out_edges)[0]
        attrs = witness.get_edge_data(edge[0], edge[1])

        startline = attrs["startline"] if "startline" in attrs else None
        endline = attrs["endline"] if "endline" in attrs else None
        startoffset = attrs["startoffset"] if "startoffset" in attrs else None
        endoffset = attrs["endoffset"] if "endoffset" in attrs else None

        coords = get_coords(c_file, startline, endline, startoffset, endoffset)
        metadata = {key: attrs[key] for key in ["assumption", "control", "threadId", "createThread"] if key in attrs}
        ret.append((coords, metadata))
        node = edge[1]

    return ret


def apply_witness(ast, c_file, witnessfile):
    funcdefs = {}
    for node in ast.ext:
        if isinstance(node, FuncDef):
            funcdefs[node.decl.name] = node.body
    metadata = extract_metadata(witnessfile, c_file)
    threadid = metadata[0][1]["threadId"] if "threadId" in metadata[0][1] else 0
    i = 0
    for coords, data in metadata:
        if (data["threadId"] if "threadId" in data else threadid) != threadid and coords and "startline" in coords:
            threadid = data["threadId"] if "threadId" in data else threadid
            first_node, first_parent = find_first_statement_on_line(ast, coords["startline"])

            yield_func   = FuncCall(ID("yield"),   ExprList(
                [Constant(type='int', value=f'{i}'), Constant(type='int', value=f'{threadid}')]
            ))
            release_func = FuncCall(ID("release"), ExprList(
                [Constant(type='int', value=f'{i}'), Constant(type='int', value=f'{threadid}')]
            ))

            i = i + 1
            first_index = first_parent.block_items.index(first_node)
            first_parent.block_items.insert(first_index, yield_func)
            if isinstance(first_node, (Compound, While, DoWhile, For)):
                first_node.stmt = Compound(block_items=[release_func, first_node.stmt])
            elif isinstance(first_node, If):
                if first_node.iftrue:
                    first_node.iftrue = Compound(block_items=[release_func, first_node.iftrue])
                if first_node.iffalse:
                    first_node.iffalse = Compound(block_items=[release_func, first_node.iffalse])
            else:
                first_parent.block_items.insert(first_index + 2, release_func)
