# Examples

Run all of them via `./smoketest.sh` from the repository root.

## concurrent-unreach.i + concurrent-unreach.witness-2.2.yml (YAML, format 2.2)

Reachability (`unreach-call`) witness for a concurrent program: the writer
thread must write `x = 1` before main reads `x`. The witness pins this order
through its segment order (write in an earlier segment than the read), which
the instrumentation enforces; the expected verdict is `ALWAYS`.

## concurrent-data-race.i + concurrent-data-race.witness-2.2.yml (YAML, format 2.2)

Data race (`no-data-race`) witness: two threads write `x` without
synchronization. The racing pair is given as the two `target` waypoints of the
final multi-follow segment; the test is compiled with ThreadSanitizer, which
reports the race. The expected verdict is `ALWAYS`.
