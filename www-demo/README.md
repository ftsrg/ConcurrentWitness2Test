# www-demo

A fully static, browser-only playground for the sv-witnesses concurrency
extension: a C editor and a YAML violation-witness editor side by side,
example programs from a local bundle and live from
[sv-benchmarks](https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks),
live linting against the real `witnesslint`, and a button that runs the
real `ConcurrentWitness2Test` instrumentation pipeline — all in-browser via
[Pyodide](https://pyodide.org), no backend.

Nothing under `www-demo/` duplicates files tracked elsewhere: the
`Dockerfile` is a multi-stage build that fetches Monaco (npm), `pcpp` (PyPI),
and the sv-witnesses linter/schemas/examples (`git clone`, branch
`concurrent-sc-violation-witnesses` — see below) fresh every build, and
copies `ConcurrentWitness2Test`'s own pure-Python modules straight from the
repo root. The only files checked in here are genuinely new:
`index.html`/`style.css`/`app.js`/`pyodide-worker.js`, `Dockerfile`/
`nginx.conf`, and three small Python entry points (`py/shim.py`,
`py/clang_ast_stub.py`, `py/cwt/instrument.py`).

## Running locally

```sh
docker build -f www-demo/Dockerfile -t cwt-demo .   # from the repo root
docker run --rm -p 8088:80 cwt-demo
```

(or `docker build -f Dockerfile -t cwt-demo .. && docker run ...` from
inside `www-demo/`). Open `http://localhost:8088`.

This is also meant to work as a plain static site with no Docker/build step
at all (e.g. GitHub Pages) — but since the Dockerfile is what assembles
`vendor/` and `py.zip` at build time, deploying without Docker currently
means running the equivalent fetch/copy steps yourself (see the Dockerfile)
before publishing the directory.

## How it works

- **Monaco** provides both editors (vendored from npm at build time).
- **Pyodide** (loaded from the jsdelivr CDN at runtime — not vendored, see
  `pyodide-worker.js` for why) runs in a Web Worker and exposes two Python
  entry points from `py/shim.py`:
  - `lint(witness_path, program_path)` calls the real `witnesslint`
    (cloned from `sv-witnesses/linter/` at build time) against files
    written into Pyodide's virtual filesystem.
  - `instrument(c_path, witness_path)` mirrors `main.py:translate_to_c`
    from this project, minus the compile/execute step (no C compiler
    exists in-browser, and the task is just to show the instrumented
    source, not run it). It swaps the real `cpp` subprocess for
    [pcpp](https://github.com/ned14/pcpp), a pure-Python preprocessor —
    verified byte-for-byte equivalent to the real CLI's output on
    sv-witnesses' regression examples. "Download instrumented program" bundles the result
    together with `svcomp.c` (copied from the repo root at build time) and
    a generated `Makefile` into a hand-rolled, store-only `.zip` (no
    compression library needed for source-sized files) so the download is
    immediately buildable with `make && make run`.
- The sidebar's live sv-benchmarks browser talks directly to the GitLab
  API (`/repository/tree`, `/repository/files/.../raw`), which sends
  permissive CORS headers — no proxy needed.
- **"Compile & Run"** (unreach-call only) compiles the C editor's *current*
  contents verbatim — not re-instrumented — together with `svcomp.c`,
  using the [Wasmer JS SDK](https://github.com/wasmerio/wasmer-js)'s real
  `clang` (the `clang/clang` Wasmer registry package, ~100MB, fetched
  lazily at runtime like Pyodide, not vendored) targeting `wasm32-wasix`,
  then runs the result via Wasmer's WASIX runtime with real multithreading
  (Web Workers + `SharedArrayBuffer`), not a single-threaded simulation.
  This needs cross-origin isolation (`nginx.conf` sets
  `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy`); every
  cross-origin resource this app loads already sends a compatible CORS or
  `Cross-Origin-Resource-Policy` header, so this doesn't break anything
  else. Gated to `unreach-call` because that's the only property a plain
  exit code can confirm (`reach_error()` calls `exit(74)`); `no-data-race`
  would need ThreadSanitizer and `no-overflow` UBSan, neither wired in.

## Why the `concurrent-sc-violation-witnesses` branch

`sv-witnesses`' `main` branch is still at witness format **2.1** and has no
`thread_id`/`memory_model` support at all — the concurrency extension this
whole repo is about only exists on the `concurrent-sc-violation-witnesses`
branch (the one backing [MR
!108](https://gitlab.com/sosy-lab/benchmarking/sv-witnesses/-/merge_requests/108)).
The Dockerfile clones that branch specifically; cloning `main` would make
every witness using `thread_id` fail schema validation. It's also the
sidebar's default ref for live-browsing `sv-witnesses`' `examples/`
directory (user-editable via the "Branch/tag" field).

## Known limitations

- `--strictChecking`'s clang-AST cross-check is unavailable (no libclang in
  wasm); `py/clang_ast_stub.py` is installed over the real
  `witnesslint/clang_ast.py` and raises, which the linter already catches
  and degrades gracefully from.
- Instrumentation only transforms the source; it doesn't compile or run it
  itself — that's what "Compile & Run" is for (see above), and the CLI
  (`../start.sh`) remains the option for the other two properties.
- "Compile & Run"'s *compilation* step was verified directly against the
  real `clang/clang` Wasmer package (valid wasm output, exit code 0) from
  a Node script using `@wasmer/sdk`'s Node entrypoint. The *execution*
  step (and specifically real multithreading) could not be verified the
  same way: running the compiled module through that same Node entrypoint
  consistently exited the process early without resolving, in a way that
  looks like a Node-specific SDK issue rather than anything about the
  approach itself — Wasmer's threading model targets the browser (Web
  Workers + `SharedArrayBuffer`), which is also this feature's actual
  runtime, not Node. This needs real-browser testing to confirm.
- On the GitHub Pages deployment (`.github/workflows/gh-pages.yml`),
  "Compile & Run" loses real multithreading: `SharedArrayBuffer` needs the
  page to be cross-origin isolated, which needs the
  `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` response
  headers `nginx.conf` sets for the Docker deployment -- and GitHub Pages
  has no mechanism to set custom response headers at all (no `_headers`
  file support like Netlify/Cloudflare Pages). Everything else (linting,
  instrumentation) is unaffected, since it doesn't depend on
  cross-origin isolation. Self-host via Docker for full Compile & Run.

## Deploying

`.github/workflows/gh-pages.yml` builds the same Dockerfile used locally,
extracts the resulting static tree (`docker create` + `docker cp`, no
re-implementation of the vendoring steps), and publishes it via GitHub's
official Pages actions. It runs on every push to `main` that touches
`www-demo/` or the Python modules it vendors, plus manual dispatch. The
repo's Pages source must be set to "GitHub Actions" once, under Settings →
Pages → Build and deployment → Source.

## Bugs found and fixed upstream while building this

Two pre-existing `ConcurrentWitness2Test` bugs were blocking the bundled
sv-witnesses examples and got fixed in the actual source (not just worked
around here), each reproduced and verified against the real, unmodified
CLI before and after:

- `hacks()` (now its own module, `../hacks.py`) blanked `//` comments using
  a paren-balance scanner meant for `__attribute__(...)`-style constructs;
  a comment containing a balanced parenthesized expression (e.g. `// so
  'if (x == 1)' is taken`) stopped the blanking early, leaving a stray `'`
  that failed to lex. Fixed by giving comments their own full-blank
  callback instead of reusing the paren-aware one.
- `witness2ast.py`'s line-matching (`find_first_statement_on_line` and
  friends) searched the *entire* AST for the first statement at or past a
  target line, ignoring which file it came from. For a raw `.c` file with
  `#include`d headers, if the witness's target line was smaller than some
  header-injected function body's line (headers restart line numbering
  from 1), instrumentation silently attached to the wrong statement
  instead. Fixed by threading the witness's own `c_file` through those
  functions and requiring `node.coord.file == c_file` — pycparser already
  tracks per-node origin file correctly via the preprocessor's `#line`
  markers, so this is a strict improvement with no behavioral change for
  the previously-working cases (verified byte-identical output on the
  existing examples before/after).
