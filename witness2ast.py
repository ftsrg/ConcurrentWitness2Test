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

Application of a parsed witness to the program AST.

The witness (of either format, see ``witnessparser``) is reduced to a
sequence of steps; this module turns those steps into source-level
instrumentation:

* steps carrying an ``assumption`` over a ``__VERIFIER_nondet_*()``
  assignment replace the nondeterministic call with the assumed constant;
* steps where the executing thread changes become *schedule points*: a
  ``__concurrentwit2test_yield(slot, tid)``/``__concurrentwit2test_release(slot, tid)``
  pair (implemented in ``svcomp.c``) that blocks the thread until all
  earlier schedule points have been passed, realizing the witness' cross-thread
  ordering. The functions are prefixed to avoid accidentally colliding with
  identifiers in the instrumented program.

For a ``no-data-race`` witness the racing accesses (the ``target``
waypoints of the final multi-follow segment) are special: they must stay
unsynchronized, so they share a single slot and only ``__concurrentwit2test_yield``
on it -- a ``__concurrentwit2test_release`` between them would create a
happens-before edge that hides the race from the thread sanitizer.
"""

import re

from pycparser.c_ast import (
    Compound,
    If,
    While,
    DoWhile,
    For,
    Return,
    FuncCall,
    NodeVisitor,
    ID,
    ExprList,
    Constant,
    Assignment,
)

from Exceptions import KnownErrorVerdict
from witnessparser import parse_witness, FORMAT_YAML


def find_nondet_assignment_on_line(ast, target_line, target_file):
    class LineVisitor(NodeVisitor):
        def __init__(self, target_line, target_file):
            self.target_line = target_line
            self.target_file = target_file
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
                        and stmt.coord.file == self.target_file
                        and type(stmt) == Assignment
                        and type(stmt.rvalue) == FuncCall
                        and "__VERIFIER_nondet" in stmt.rvalue.name.name
                    ):
                        self.statement = stmt
                        self.parent = node
                        self.found = True
                        return
                self.generic_visit(stmt)

    line_visitor = LineVisitor(target_line, target_file)
    line_visitor.visit(ast)

    if line_visitor.statement:
        return line_visitor.statement, line_visitor.parent
    else:
        return None, None


def find_last_nondet_assignment_before_line(ast, target_line, varnames, target_file):
    """Find the last `var = __VERIFIER_nondet_*()` with var in `varnames`
    at or before `target_line`."""

    class LineVisitor(NodeVisitor):
        def __init__(self):
            self.statement = None
            self.line = -1

        def visit_Assignment(self, node):
            if (
                node.coord
                and node.coord.file == target_file
                and self.line < node.coord.line <= target_line
                and type(node.rvalue) == FuncCall
                and type(node.rvalue.name) == ID
                and "__VERIFIER_nondet" in node.rvalue.name.name
                and getattr(node.lvalue, "name", None) in varnames
            ):
                self.statement = node
                self.line = node.coord.line
            self.generic_visit(node)

    line_visitor = LineVisitor()
    line_visitor.visit(ast)
    return line_visitor.statement


def find_first_statement_on_line(ast, target_line, target_file):
    class LineVisitor(NodeVisitor):
        def __init__(self, target_line, target_file):
            self.target_line = target_line
            self.target_file = target_file
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
                    if line >= self.target_line and stmt.coord.file == self.target_file:
                        self.statement = stmt
                        self.parent = node
                        self.found = True
                        return
                self.generic_visit(stmt)

    line_visitor = LineVisitor(target_line, target_file)
    line_visitor.visit(ast)

    if line_visitor.statement:
        return line_visitor.statement, line_visitor.parent
    else:
        return None, None


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

# TODO not perfect regex, but hard to solve well for everything ( e.g., assumption: !(var == 1) and variants )
assumption_pattern = r"([^\s]*)\s*==\s*([^\s]*)"


def apply_assumption(ast, line, assumption, target_file, anchored_after=False):
    """Fix the value of a __VERIFIER_nondet_*() assignment near `line`.

    If the assumption constrains the assigned variable to a constant
    (`var == value`), the nondeterministic call is replaced by that
    constant. Assumptions of any other shape are ignored.

    The two witness formats anchor assumptions differently: a GraphML edge
    carries the assumption on the assigning statement itself, while a YAML
    assumption waypoint holds at the sequence point *before* its location,
    i.e., it follows the assignment (anchored_after=True).
    """
    # TODO current implementation is limited: will not work if single assignment executes 1+ time (e.g., in a loop)
    assumptions = dict(re.findall(assumption_pattern, assumption))
    if anchored_after:
        nondet_assign_node = find_last_nondet_assignment_before_line(
            ast, line, set(assumptions), target_file
        )
    else:
        nondet_assign_node, _ = find_nondet_assignment_on_line(ast, line, target_file)
    if nondet_assign_node is None:
        return

    varname = nondet_assign_node.lvalue.name
    if varname in assumptions:
        if nondet_assign_node.rvalue.name.name in nondet_return_types:
            ret_type = nondet_return_types[nondet_assign_node.rvalue.name.name]
            nondet_assign_node.rvalue = Constant(
                type=ret_type, value=assumptions[varname]
            )


def make_schedule_call(name, slot, threadid):
    return FuncCall(
        ID(name),
        ExprList(
            [
                Constant(type="int", value=f"{slot}"),
                Constant(type="int", value=f"{threadid}"),
            ]
        ),
    )


def insert_schedule_point(ast, line, slot, threadid, target_file, release=True):
    """Instrument the statement at (or first after) `line` as a schedule point.

    A __concurrentwit2test_yield(slot, threadid) call before the statement
    blocks the thread until all earlier schedule points have released their
    slot; a __concurrentwit2test_release(slot, threadid) call afterwards lets
    the next schedule point proceed. For control statements the release goes
    to the start of the body/branches (so it happens only once the statement
    is really being executed), and for a return statement it goes before the
    statement (code after a return would never run).

    With release=False only the yield is inserted and the slot is not
    consumed; this keeps racing accesses of a data-race witness free of
    synchronization between one another.

    Returns the slot the next schedule point should use.
    """
    statement, parent = find_first_statement_on_line(ast, line, target_file)

    yield_func = make_schedule_call("__concurrentwit2test_yield", slot, threadid)
    first_index = parent.block_items.index(statement)
    parent.block_items.insert(first_index, yield_func)

    if not release:
        return slot

    release_func = make_schedule_call("__concurrentwit2test_release", slot, threadid)
    if isinstance(statement, Return):
        parent.block_items.insert(first_index + 1, release_func)
    elif isinstance(statement, Compound):
        statement.block_items = [release_func] + (statement.block_items or [])
    elif isinstance(statement, (While, DoWhile, For)):
        statement.stmt = Compound(block_items=[release_func, statement.stmt])
    elif isinstance(statement, If):
        if statement.iftrue:
            statement.iftrue = Compound(block_items=[release_func, statement.iftrue])
        if statement.iffalse:
            statement.iffalse = Compound(block_items=[release_func, statement.iffalse])
    else:
        parent.block_items.insert(first_index + 2, release_func)
    return slot + 1


def apply_witness(ast, c_file, witnessfile):
    """Instrument `ast` according to the witness; returns the ParsedWitness."""
    witness = parse_witness(witnessfile, c_file)
    if not witness.steps:
        raise KnownErrorVerdict("Empty witness")

    first_metadata = witness.steps[0][1]
    threadid = first_metadata["threadId"] if "threadId" in first_metadata else 0

    slot = 0
    anchored_after = witness.format == FORMAT_YAML
    for coords, data in witness.steps:
        usable_coords = coords and "startline" in coords
        if "assumption" in data and usable_coords:
            apply_assumption(
                ast, coords["startline"], data["assumption"], c_file, anchored_after
            )

        step_threadid = data["threadId"] if "threadId" in data else threadid
        if step_threadid != threadid and usable_coords:
            threadid = step_threadid
            release = not (witness.data_race and data.get("type") == "target")
            slot = insert_schedule_point(
                ast, coords["startline"], slot, threadid, c_file, release
            )

    return witness
