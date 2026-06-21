# Build context is the ConcurrentWitness2Test repo root (one level up from
# this file): `docker build -f www-demo/Dockerfile -t cwt-demo .` from there,
# or `docker build -f Dockerfile -t cwt-demo ..` from inside www-demo/.
# Nothing under www-demo/ duplicates files tracked elsewhere in this repo or
# in sv-witnesses -- everything is fetched/copied fresh at build time.

# --- Monaco editor, vendored via npm ---
FROM node:22-alpine AS monaco
WORKDIR /build
RUN npm install monaco-editor@0.55.1 --no-save

# --- Wasmer JS SDK, vendored via npm. Drives a real clang (the "clang/clang"
# Wasmer registry package, fetched lazily at runtime like Pyodide -- it's
# ~100MB, too big to vendor here) compiling to wasm32-wasix, then runs the
# result with real multithreading (Web Workers + SharedArrayBuffer), not a
# simulation. Used by "Compile & Run" for unreach-call witnesses only. ---
FROM node:22-alpine AS wasmersdk
WORKDIR /build
RUN npm install @wasmer/sdk@0.10.0 --no-save

# --- sv-witnesses' linter + format schemas + examples, straight from GitLab.
# The concurrency extension (thread_id, memory_model, format 2.2) only
# exists on this branch -- main is still at format 2.1 and has no
# thread_id, so the branch is required, not just a source of "nicer"
# examples. ---
FROM alpine:3 AS svwitnesses
RUN apk add --no-cache git
RUN git clone --depth 1 -b concurrent-sc-violation-witnesses \
    https://gitlab.com/sosy-lab/benchmarking/sv-witnesses.git /sv-witnesses

# --- pcpp: pure-python C preprocessor, drop-in for `cpp` (no compiler in wasm) ---
FROM alpine:3 AS pywheels
RUN apk add --no-cache curl
WORKDIR /wheels
RUN curl -sLO https://files.pythonhosted.org/packages/01/ca/ada7f39c5a0977893e0ef809b1617b259b2d76f6382a7abad00dd6d77904/pcpp-1.30-py2.py3-none-any.whl

# --- Assemble the python tree the Pyodide worker fetches as one archive ---
FROM alpine:3 AS pytree
RUN apk add --no-cache zip
WORKDIR /py
# ConcurrentWitness2Test's own pure-python modules (this repo)
COPY witnessparser.py witness2ast.py tweaks.py Exceptions.py hacks.py ./cwt/
COPY headers/ ./cwt/headers/
COPY www-demo/py/cwt/instrument.py ./cwt/instrument.py
# sv-witnesses' linter + schemas (clang_ast.py replaced: no libclang in wasm,
# only used by --strictChecking, which yaml_linter.py already degrades from)
COPY --from=svwitnesses /sv-witnesses/linter/witnesslint/ ./witnesslint/
COPY --from=svwitnesses /sv-witnesses/format/schemas/ ./schemas/
COPY www-demo/py/clang_ast_stub.py ./witnesslint/clang_ast.py
COPY www-demo/py/shim.py ./shim.py
RUN find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; \
    cd / && zip -rq py.zip py

# --- Final image: nginx serving the static site ---
FROM nginx:alpine
COPY www-demo/nginx.conf /etc/nginx/conf.d/default.conf
COPY www-demo/index.html www-demo/style.css www-demo/app.js www-demo/pyodide-worker.js www-demo/wasmer-run.js www-demo/coi-serviceworker.js /usr/share/nginx/html/
COPY svcomp.c /usr/share/nginx/html/svcomp.c
# Bundled examples, fetched by app.js's local-examples sidebar -- not
# duplicated into app.js itself, so they can't drift from the real files.
COPY example/ /usr/share/nginx/html/example/
COPY --from=pytree /py.zip /usr/share/nginx/html/py.zip
COPY --from=monaco /build/node_modules/monaco-editor/min/vs /usr/share/nginx/html/vendor/monaco/vs
COPY --from=wasmersdk /build/node_modules/@wasmer/sdk/dist /usr/share/nginx/html/vendor/wasmer
COPY --from=pywheels /wheels/ /usr/share/nginx/html/vendor/pypi/
EXPOSE 80
