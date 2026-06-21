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

* Steps carrying an ``assumption`` over a ``__VERIFIER_nondet_*()``
  assignment replace the nondeterministic call with a runtime guard:
  ``__c2tt_should_use_assumed(slot, logical_tid) ? VALUE : __VERIFIER_nondet_*()``.
  The guard checks both the global segment counter (``slot``) and the
  calling thread's logical witness ID so that the assumed value is only
  injected when the execution is in exactly the right scheduling epoch and
  thread.

* ``function_return`` waypoints work like assumptions but target the
  ``return __VERIFIER_nondet_*()`` expression inside the indicated function.

* Steps where the executing thread changes become *schedule points*: a
  ``__concurrentwit2test_yield(slot, tid)``/``__concurrentwit2test_release(slot, tid)``
  pair (implemented in ``svcomp.c``) that blocks the thread until all
  earlier schedule points have been passed, realizing the witness' cross-thread
  ordering. The functions are prefixed to avoid accidentally colliding with
  identifiers in the instrumented program. Both check internally that the
  *calling* thread's logical ID matches the targeted ``tid`` before doing
  anything, so code shared by several threads (or by the witnessed thread
  and unrelated ones) only pauses/advances the schedule on the one thread
  it is meant for.

* ``function_enter`` waypoints at ``pthread_create`` call sites rewrite the
  call to go through ``__c2tt_thread_proxy`` (see ``svcomp.c``), handing it
  the program's real start routine/argument plus the logical thread ID the
  new thread should run as. The ID is only assigned when the *call* happens
  in the right segment and on the right calling thread (a runtime check,
  since the same call site -- e.g. inside a loop -- may run many times,
  only one of which is the one the witness pins); other invocations pass
  ``-1``, i.e. "not a thread the witness tracks". This is deliberately not
  done by injecting a registration call into the start routine's body,
  since that routine may be shared by multiple ``pthread_create`` call
  sites with different logical IDs.

* ``assumption`` waypoints that pin a ``__VERIFIER_nondet_*()`` assignment
  to a constant value (the common case) use the runtime guard above to
  substitute the value. Any other assumption (a general C expression, not
  immediately following a matching nondet call) instead gets a single
  ``__concurrentwit2test_assume(matches, EXPR)`` call inserted -- the
  helper (see ``svcomp.c``) exits cleanly if ``matches`` (the segment/
  thread check) holds but ``EXPR`` doesn't, since that execution has
  diverged from the witness rather than replaying it.

* ``branching`` waypoints re-check the branching statement's controlling
  expression against the witness' recorded direction (or, for ``switch``,
  its integer constant) through the same ``__concurrentwit2test_assume``
  call.

For a ``no-data-race`` witness the racing accesses (the ``target``
waypoints of the final multi-follow segment) are special: they must stay
unsynchronized, so they share a single slot and only ``__concurrentwit2test_yield``
on it -- a ``__concurrentwit2test_release`` between them would create a
happens-before edge that hides the race from the thread sanitizer.
"""

import re

from pycparser import CParser
from pycparser.c_ast import (
    Compound,
    If,
    While,
    DoWhile,
    For,
    Return,
    FuncCall,
    FuncDef,
    NodeVisitor,
    ID,
    ExprList,
    Constant,
    Assignment,
    TernaryOp,
    UnaryOp,
    BinaryOp,
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


def find_return_nondet_on_line(ast, target_line, target_file):
    """Find a ``return __VERIFIER_nondet_*()`` statement at or after target_line."""

    class ReturnVisitor(NodeVisitor):
        def __init__(self):
            self.statement = None

        def visit_Return(self, node):
            if (
                node.coord
                and node.coord.file == target_file
                and node.coord.line >= target_line
                and node.expr is not None
                and isinstance(node.expr, FuncCall)
                and isinstance(node.expr.name, ID)
                and "__VERIFIER_nondet" in node.expr.name.name
                and self.statement is None
            ):
                self.statement = node
            self.generic_visit(node)

    v = ReturnVisitor()
    v.visit(ast)
    return v.statement


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


def find_pthread_create_call(ast, target_line, target_file):
    """Return the ``pthread_create(...)`` FuncCall node at target_line, or None."""

    class Visitor(NodeVisitor):
        def __init__(self):
            self.call = None

        def visit_FuncCall(self, node):
            if (
                self.call is None
                and node.coord
                and node.coord.file == target_file
                and node.coord.line == target_line
                and isinstance(node.name, ID)
                and node.name.name == "pthread_create"
                and node.args is not None
                and len(node.args.exprs) >= 4
            ):
                self.call = node
            self.generic_visit(node)

    v = Visitor()
    v.visit(ast)
    return v.call


def make_segment_match_call(slot, logical_tid):
    return FuncCall(
        ID("__c2tt_should_use_assumed"),
        ExprList(
            [
                Constant(type="int", value=str(slot)),
                Constant(type="int", value=str(logical_tid)),
            ]
        ),
    )


def instrument_pthread_create(
    ast, line, target_file, slot, calling_threadid, logical_tid
):
    """Rewrite the ``pthread_create`` call at `line` to spawn through
    ``__c2tt_thread_proxy``, so the new thread's logical witness ID is fixed
    (to `logical_tid`, or -1 if this particular call turns out, at runtime,
    not to be the one the witness pins) before it runs any program code.

    If the call site was already rewritten -- the same source line can
    spawn many real threads, e.g. inside a loop, with only one of them
    being the one a given function_enter waypoint refers to -- the new
    segment/thread check is chained onto the existing logical-tid ternary
    instead of overwriting it.
    """
    call = find_pthread_create_call(ast, line, target_file)
    if call is None:
        return

    match_call = make_segment_match_call(slot, calling_threadid)
    already_instrumented = (
        isinstance(call.args.exprs[2], ID)
        and call.args.exprs[2].name == "__c2tt_thread_proxy"
    )

    if not already_instrumented:
        real_func = call.args.exprs[2]
        real_arg = call.args.exprs[3]
        tid_expr = TernaryOp(
            cond=match_call,
            iftrue=Constant(type="int", value=str(logical_tid)),
            iffalse=Constant(type="int", value="-1"),
        )
        call.args.exprs[2] = ID("__c2tt_thread_proxy")
        call.args.exprs[3] = FuncCall(
            ID("__c2tt_make_thread_arg"),
            ExprList([real_func, real_arg, tid_expr]),
        )
    else:
        make_thread_arg_call = call.args.exprs[3]
        previous_tid_expr = make_thread_arg_call.args.exprs[2]
        make_thread_arg_call.args.exprs[2] = TernaryOp(
            cond=match_call,
            iftrue=Constant(type="int", value=str(logical_tid)),
            iffalse=previous_tid_expr,
        )


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


def _make_guarded_nondet(nondet_call, ret_type, value, slot, logical_tid):
    """Wrap a nondet call in a runtime guard:
    ``__c2tt_should_use_assumed(slot, tid) ? VALUE : __VERIFIER_nondet_*()``.

    When slot or logical_tid is None the guard is skipped and the constant
    is substituted directly (GraphML path with no slot information, or any
    context where the slot is unknown).
    """
    if slot is None or logical_tid is None:
        return Constant(type=ret_type, value=value)
    return TernaryOp(
        cond=make_segment_match_call(slot, logical_tid),
        iftrue=Constant(type=ret_type, value=value),
        iffalse=nondet_call,
    )


def make_match_expr(slot, logical_tid):
    """An expression that's true exactly when the witness wants something
    checked right now: unconditionally true (1) if slot/logical_tid are
    unknown (GraphML has no segment counter), else the segment/thread
    match check.
    """
    if slot is None or logical_tid is None:
        return Constant(type="int", value="1")
    return make_segment_match_call(slot, logical_tid)


def make_assume_call(slot, logical_tid, holds_expr):
    """``__concurrentwit2test_assume(matches, holds)`` (see svcomp.c): a
    single call standing in for ``if (matches && !holds) exit(0);``, so
    general assumption/branching guards are one statement in the AST
    instead of a constructed If/Compound/exit tree.
    """
    return FuncCall(
        ID("__concurrentwit2test_assume"),
        ExprList([make_match_expr(slot, logical_tid), holds_expr]),
    )


def parse_c_expression(expr_str, target_file):
    """Parse a standalone C expression string into a pycparser expression node."""
    wrapper_ast = CParser().parse(
        f"void __c2tt_expr_wrapper(void) {{ ({expr_str}); }}", target_file
    )
    return wrapper_ast.ext[-1].body.block_items[0]


def insert_assumption_guard(ast, line, assumption, target_file, slot, logical_tid):
    """General fallback for assumption waypoints that don't pin a nondet
    call: insert a ``__concurrentwit2test_assume(matches, EXPR)`` call right
    before the located statement. An execution that disagrees with the
    witness' assumption is not a replay of it, so it exits cleanly instead
    of running on down an unwitnessed path.
    """
    statement, parent = find_first_statement_on_line(ast, line, target_file)
    if statement is None:
        return
    try:
        expr = parse_c_expression(assumption, target_file)
    except Exception:
        return

    call = make_assume_call(slot, logical_tid, expr)
    idx = parent.block_items.index(statement)
    parent.block_items.insert(idx, call)


def apply_assumption(
    ast,
    line,
    assumption,
    target_file,
    anchored_after=False,
    slot=None,
    logical_tid=None,
):
    """Fix the value of a __VERIFIER_nondet_*() assignment near `line`, or
    fall back to a general runtime-checked assumption.

    If the assumption constrains the assigned variable to a constant
    (`var == value`) immediately after a matching nondet call, the
    nondeterministic call is replaced by a runtime guard that returns the
    assumed constant only when the global segment counter equals `slot`
    and the calling thread's logical ID equals `logical_tid`.  When
    slot/logical_tid are None (GraphML witnesses) the constant is
    substituted unconditionally as before.

    Otherwise (a general assumption, not the "easy" nondet-substitution
    case) a guarded ``if (!(EXPR)) exit(0);`` is inserted instead -- see
    ``insert_assumption_guard``.

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

    if nondet_assign_node is not None:
        varname = nondet_assign_node.lvalue.name
        if varname in assumptions:
            nondet_name = getattr(nondet_assign_node.rvalue.name, "name", None)
            if nondet_name in nondet_return_types:
                ret_type = nondet_return_types[nondet_name]
                original_call = nondet_assign_node.rvalue
                nondet_assign_node.rvalue = _make_guarded_nondet(
                    original_call, ret_type, assumptions[varname], slot, logical_tid
                )
                return

    insert_assumption_guard(ast, line, assumption, target_file, slot, logical_tid)


def apply_function_return(
    ast, line, assumption, target_file, slot=None, logical_tid=None
):
    """Fix the return value of a __VERIFIER_nondet_*() return statement near `line`.

    The constraint value is parsed with the same ``var == value`` pattern
    as assumptions (``var`` is ignored for return statements -- only the
    value matters).  The return expression is replaced by a runtime guard.
    """
    values = re.findall(assumption_pattern, assumption)
    if values:
        value = values[0][1]
    else:
        # Allow bare literal: "5" or "-1" etc.
        value = assumption.strip()

    ret_node = find_return_nondet_on_line(ast, line, target_file)
    if ret_node is None:
        return

    nondet_name = getattr(ret_node.expr.name, "name", None)
    if nondet_name not in nondet_return_types:
        return

    ret_type = nondet_return_types[nondet_name]
    original_call = ret_node.expr
    ret_node.expr = _make_guarded_nondet(
        original_call, ret_type, value, slot, logical_tid
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


def apply_branching(
    ast, line, constraint_value, target_file, slot=None, logical_tid=None
):
    """Branching waypoint: re-check the branching statement's (``if``,
    ``while``, ``do``, ``for``, or ``switch``) controlling expression
    against the witness' recorded direction, via the same
    ``__concurrentwit2test_assume`` helper as general assumptions.

    The controlling expression is duplicated rather than lifted into a
    temporary, so this -- like ``apply_assumption`` -- is unsound if it has
    side effects; the same known limitation applies here.
    """
    statement, parent = find_first_statement_on_line(ast, line, target_file)
    if statement is None or getattr(statement, "cond", None) is None:
        return

    cond = statement.cond
    if constraint_value in ("true", "false"):
        wanted_true = constraint_value == "true"
        holds = cond if wanted_true else UnaryOp("!", cond)
    else:
        try:
            int(constraint_value)
        except (TypeError, ValueError):
            # 'default' switch label or other unsupported constraint forms.
            return
        holds = BinaryOp("==", cond, Constant(type="int", value=str(constraint_value)))

    call = make_assume_call(slot, logical_tid, holds)
    idx = parent.block_items.index(statement)
    parent.block_items.insert(idx, call)


def inject_expected_final_slot(ast, final_slot):
    """Prepend ``__c2tt_set_expected_final_slot(final_slot)`` to main()'s
    body, so reach_error() (see svcomp.c) only counts as confirming the
    witness once every one of its segments has actually been passed --
    not merely whenever the program happens to reach it via some other,
    unrelated nondeterministic choice. Must run before any thread is
    spawned, hence prepended to main() itself rather than set some other
    way.
    """
    for node in ast.ext:
        if isinstance(node, FuncDef) and node.decl.name == "main":
            call = FuncCall(
                ID("__c2tt_set_expected_final_slot"),
                ExprList([Constant(type="int", value=str(final_slot))]),
            )
            body = node.body
            if body.block_items is None:
                body.block_items = [call]
            else:
                body.block_items.insert(0, call)
            return


def apply_witness(ast, c_file, witnessfile):
    """Instrument `ast` according to the witness; returns the ParsedWitness."""
    witness = parse_witness(witnessfile, c_file)
    if not witness.steps:
        raise KnownErrorVerdict("Empty witness")

    first_metadata = witness.steps[0][1]
    threadid = first_metadata["threadId"] if "threadId" in first_metadata else 0

    slot = 0
    anchored_after = witness.format == FORMAT_YAML

    # The k-th function_enter at a pthread_create call gets logical thread k.
    next_created_thread = 1

    for coords, data in witness.steps:
        usable_coords = coords and "startline" in coords

        waypoint_type = data.get("type")
        step_threadid = data["threadId"] if "threadId" in data else threadid

        # function_enter at a pthread_create: route the call through
        # __c2tt_thread_proxy so the new thread's logical ID is fixed
        # before it runs any program code (see instrument_pthread_create).
        if waypoint_type == "function_enter" and usable_coords:
            instrument_pthread_create(
                ast,
                coords["startline"],
                c_file,
                slot,
                step_threadid,
                next_created_thread,
            )
            next_created_thread += 1

        if "assumption" in data and usable_coords:
            if waypoint_type == "function_return":
                apply_function_return(
                    ast,
                    coords["startline"],
                    data["assumption"],
                    c_file,
                    slot=slot,
                    logical_tid=step_threadid,
                )
            elif waypoint_type == "branching":
                apply_branching(
                    ast,
                    coords["startline"],
                    data["assumption"],
                    c_file,
                    slot=slot,
                    logical_tid=step_threadid,
                )
            else:
                apply_assumption(
                    ast,
                    coords["startline"],
                    data["assumption"],
                    c_file,
                    anchored_after,
                    slot=slot,
                    logical_tid=step_threadid,
                )

        if step_threadid != threadid and usable_coords:
            threadid = step_threadid
            release = not (witness.data_race and data.get("type") == "target")
            slot = insert_schedule_point(
                ast, coords["startline"], slot, threadid, c_file, release
            )

    inject_expected_final_slot(ast, slot)
    return witness
