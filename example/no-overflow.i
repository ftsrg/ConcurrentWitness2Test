// Property: G ! overflow
// Demonstrates a no-overflow violation witness: the witness pins x to INT_MAX
// so that x + 1 overflows.  Preprocessed for pycparser (no system headers).

extern int __VERIFIER_nondet_int(void);

int main(void) {
    int x;
    x = __VERIFIER_nondet_int();
    int y = x + 1;
    (void)y;
    return 0;
}
