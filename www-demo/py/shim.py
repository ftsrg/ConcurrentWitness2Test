"""
Entry points called from pyodide-worker.js. Kept dependency-light and
side-effect-free per call (re-clears witnesslint's module-level logging
handlers each time, since they're created once and would otherwise pin to
the first call's redirected stdout/stderr).
"""

import contextlib
import io
import logging
import sys

sys.path.insert(0, "/py/cwt")
sys.path.insert(0, "/py")


def lint(witness_path: str, program_path: str | None, strict: bool = False) -> dict:
    from witnesslint import main as witnesslint_main

    for name in ("with_position", "without_position"):
        logging.getLogger(name).handlers.clear()

    argv = ["--witness", witness_path]
    if program_path:
        argv.append(program_path)
    if strict:
        argv.append("--strictChecking")

    buf = io.StringIO()
    exit_code = None
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            witnesslint_main.main(argv)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        except Exception as e:  # noqa: BLE001 - surfaced to the UI, not swallowed
            buf.write("\nINTERNAL ERROR: {}: {}\n".format(type(e).__name__, e))
            exit_code = -1
    return {"exit_code": exit_code, "output": buf.getvalue()}


def instrument(c_path: str, witness_path: str) -> dict:
    from hacks import hacks
    from instrument import instrument as run_instrument

    headers_dir = "/py/cwt/headers"
    buf = io.StringIO()
    try:
        with open(c_path, "r") as f:
            src = f.read()
        hacked = hacks(src)
        with open(c_path, "w") as f:
            f.write(hacked)

        source, data_race, no_overflow = run_instrument(
            c_path, witness_path, headers_dir
        )
        return {
            "ok": True,
            "source": source,
            "data_race": data_race,
            "no_overflow": no_overflow,
            "log": buf.getvalue(),
        }
    except Exception as e:  # noqa: BLE001 - surfaced to the UI, not swallowed
        return {
            "ok": False,
            "error": "{}: {}".format(type(e).__name__, e),
            "log": buf.getvalue(),
        }
