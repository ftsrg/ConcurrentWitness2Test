These minimal stub system headers let `pycparser` parse SV-COMP benchmarks
that still contain `#include` directives, without dragging in real glibc
headers (which use GNU extensions pycparser's grammar doesn't support).

Adapted from theta's C frontend
(`subprojects/frontends/c-frontend/.../frontend/stdlib/*.h.kt`,
https://github.com/ftsrg/theta), itself taken from the
[c-std-headers](https://github.com/eliphatfs/c-std-headers) project.
Both are licensed under the Apache License, Version 2.0 (see `../LICENSE`).

Local additions on top of the theta originals (`NULL`, `intptr_t`/`uintptr_t`)
fill gaps that theta's own frontend papers over with special-cased Java
logic instead of a textual macro/typedef.
