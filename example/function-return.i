// Property: G ! call(reach_error())
// Demonstrates a function_return waypoint: the witness pins the return value
// of get_value() so that the branch triggering reach_error() is taken.
// Preprocessed for pycparser (no system headers).

extern int __VERIFIER_nondet_int(void);
void reach_error(void);

int get_value(void) {
    return __VERIFIER_nondet_int();
}

int main(void) {
    int v = get_value();
    if (v > 0) {
        reach_error();
    }
    return 0;
}
