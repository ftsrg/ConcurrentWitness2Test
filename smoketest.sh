#!/bin/bash
set -e

check_verdict() {
    out=$("$@")
    echo "$out"
    grep -q "Verdict: ALWAYS" <<< "$out"
}

# GraphML (format 1.0) witness. The bundled witness is known to be
# incomplete (see example/README.md), so only successful test generation
# is checked here, not the verdict.
./start.sh example/mix000.opt.i --witness example/mix000.opt.i.graphml --mode permissive

# YAML (format 2.2) concurrent reachability witness
check_verdict ./start.sh example/concurrent-unreach.i --witness example/concurrent-unreach.witness-2.2.yml --mode permissive

# YAML (format 2.2) data race witness (requires gcc with ThreadSanitizer)
check_verdict ./start.sh example/concurrent-data-race.i --witness example/concurrent-data-race.witness-2.2.yml --mode permissive

# YAML (format 2.2) no-overflow witness (requires gcc with UBSan)
check_verdict ./start.sh example/no-overflow.i --witness example/no-overflow.witness-2.2.yml --mode permissive

# YAML (format 2.2) function_return waypoint witness
check_verdict ./start.sh example/function-return.i --witness example/function-return.witness-2.2.yml --mode permissive

# YAML (format 2.2) concurrent reachability with nondet + thread-ID tracking
check_verdict ./start.sh example/concurrent-nondet.i --witness example/concurrent-nondet.witness-2.2.yml --mode permissive
