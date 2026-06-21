"""
Browser entrypoint mirroring main.py:translate_to_c, minus the gcc
compile/execute step (out of scope in-browser, no compiler in wasm).
Swaps the real `cpp` subprocess for pcpp (pure-python C preprocessor),
which has been verified byte-for-byte equivalent on the bundled examples
(see www-demo's plan/verification notes).
"""

import io

from pcpp.preprocessor import Preprocessor
from pycparser import CParser, c_generator

from tweaks import reach_error, declare_schedule_functions, fix_inline, fix_struct_def
from witness2ast import apply_witness

# Mirrors main.py's CPP_GNU_COMPAT_ARGS, expressed as pcpp #define bodies
# instead of `-D` gcc flags.
CPP_GNU_COMPAT_DEFINES = [
    "__attribute__(x)",
    "__extension__",
    "__restrict",
    "__restrict__",
    "__inline inline",
    "__inline__ inline",
    "__const const",
    "__signed__ signed",
    "__volatile__ volatile",
    "__typeof__(x) void*",
    "__builtin_va_list void*",
]


def instrument(c_path: str, witness_path: str, headers_dir: str) -> str:
    """Reads the C source at c_path (already hacks()-applied and written to
    the virtual FS by the caller), preprocesses with pcpp, parses with
    pycparser, applies the witness, regenerates C source. Returns the
    instrumented source as a string, or raises KnownErrorVerdict / a normal
    exception on failure (the caller is expected to surface these as text)."""
    with open(c_path, "r") as f:
        src = f.read()

    pre = Preprocessor()
    pre.add_path(headers_dir)
    for define in CPP_GNU_COMPAT_DEFINES:
        pre.define(define)
    pre.parse(src, c_path)
    out = io.StringIO()
    pre.write(out)
    text = out.getvalue()

    ast = CParser().parse(text, c_path)
    parsed_witness = apply_witness(ast, c_path, witness_path)

    fix_inline(ast)
    fix_struct_def(ast)
    reach_error(ast)
    declare_schedule_functions(ast)

    generator = c_generator.CGenerator()
    return generator.visit(ast), parsed_witness.data_race, parsed_witness.no_overflow
