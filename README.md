[![Build-Test-Deploy](https://github.com/ftsrg/ConcurrentWitness2Test/actions/workflows/linux-build-test-deploy.yml/badge.svg)](https://github.com/ftsrg/ConcurrentWitness2Test/actions/workflows/linux-build-test-deploy.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=ftsrg_ConcurrentWitness2Test&metric=coverage)](https://sonarcloud.io/summary/new_code?id=ftsrg_ConcurrentWitness2Test)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=ftsrg_ConcurrentWitness2Test&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=ftsrg_ConcurrentWitness2Test)


# ConcurrentWitness2Test 

ConcurrentWitness2Test validates violation witnesses for the ConcurrencySafety category at [SV-COMP](https://sv-comp.sosy-lab.org/) by *executing* them: the witness is compiled into the program as source-level instrumentation that steers the schedule (and fixes nondeterministic values), and the resulting test is run repeatedly to see whether the claimed violation is reached.

Both witness formats of SV-COMP are supported and detected automatically:

* **GraphML** (witness format 1.0): the single non-branching path of the witness automaton is replayed; `threadId` changes along the path become schedule points.
* **YAML** (witness format 2.0–2.2, `violation_sequence` entries): the `follow` waypoints are replayed in segment order. The format 2.2 concurrency extension is supported: the optional `thread_id` field on waypoints identifies the executing thread, and the segment order is enforced as the cross-thread (happens-before) order.

Two kinds of properties are supported:

* **Reachability** (`unreach-call` and similar): the violation is observed when the instrumented program calls `reach_error()`.
* **Data races** (`no-data-race`, YAML witnesses): the program is compiled with [ThreadSanitizer](https://github.com/google/sanitizers/wiki/ThreadSanitizerCppManual) (`gcc -fsanitize=thread`) and the violation is observed when the sanitizer reports a data race. The racing pair — the two `target` waypoints of the witness' final multi-follow segment — is deliberately *not* synchronized by the instrumentation (the accesses only wait for the preceding segments), since any synchronization between them would establish a happens-before edge and hide the very race the witness claims.

## Installation

Minimal necessary packages for Ubuntu 24.04 LTS:
* python3
* gcc (with `libtsan` for data race validation)

The python dependencies in `requirements.txt` are expected in a virtualenv at `./venv` (used by `start.sh`):
```sh
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
```

## Contents of the Repository
```
CONTRIBUTORS.md  -- code contributors to the project
LICENSE          -- apache 2.0 license
README.md        -- this README
example/         -- example programs and witnesses (see example/README.md)
headers/         -- minimal stub system headers used to preprocess input files (see headers/NOTICE.md)
main.py          -- main python entrypoint: compiles and runs the test, derives the verdict
requirements.txt -- python dependencies (included in venv)
smoketest.sh     -- runs the bundled examples
start.sh         -- script to start the validation process
svcomp.c         -- test harness (yield/release scheduler, SV-COMP stubs)
tweaks.py        -- AST fixes for pycparser/SV-COMP quirks
witnessparser.py -- parses GraphML and YAML witnesses into a common step sequence
witness2ast.py   -- applies the parsed witness to the program AST
```

## Usage
Run `./start.sh <c-file> --witness <witnessfile> [--mode <strict/normal/permissive>] [--timeout <seconds>]` to validate a violation witness (GraphML or YAML). The C file is preprocessed automatically (against a minimal set of stub system headers in `headers/`, since pycparser cannot handle the GNU extensions present in real glibc headers); files using system headers outside that stub set (e.g. `<stdatomic.h>`) or GCC inline assembly are not supported.

The instrumented test is executed up to 100 times (each run limited to `--timeout` seconds, 10 by default), and the mode decides when to stop:

* `strict`: stop at the first execution that does **not** reach the violation,
* `permissive`: stop at the first execution that **does** reach the violation,
* `normal`: run all repetitions.

The verdict summarizes the observed executions: `ALWAYS` (every execution reached the violation), `SOMETIMES`, `NEVER`, or `TIMEOUT` (no execution finished in time).

## Publications
For more information on how the validation works, check out our SV-COMP 2023 [tool paper](https://leventebajczi.com/publications/tacas24cwt.pdf) and [slides](https://leventebajczi.com/publications/slides/tacas24cwt.pdf).

## Tool Support

[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/bubaak/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/bubaak/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cbmc/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cbmc/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-algo-selection/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-algo-selection/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-parallel-portfolio/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/coveriteam-verifier-parallel-portfolio/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpa-lockator/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpa-lockator/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpachecker/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cpachecker/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cseq/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/cseq/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/dartagnan/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/dartagnan/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/deagle/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/deagle/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/divine/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/divine/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ebf/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ebf/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-incr/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-incr/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-kind/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/esbmc-kind/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/goblint/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/goblint/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves-par/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves-par/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/graves/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/infer/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/infer/)
[![](https://img.shields.io/badge/lazycseq-Unknown%20(0/0/0)-lightgrey)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/lazycseq/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/lf-checker/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/lf-checker/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pesco/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pesco/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pichecker/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/pichecker/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/symbiotic/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/symbiotic/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/theta/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/theta/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/uautomizer/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/uautomizer/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ugemcutter/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/ugemcutter/)
[![](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/utaipan/badge.svg)](https://ftsrg.mit.bme.hu/ConcurrentWitness2Test/benchmark-results/main/utaipan/)
