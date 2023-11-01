#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <stdatomic.h>
#include <threads.h>

void __VERIFIER_atomic_begin() {

}
void __VERIFIER_atomic_end(void) {

}
void reach_error() {
    printf("Reached error!\n");
    abort();
}

atomic_int global_counter = ATOMIC_VAR_INIT(0);
mtx_t mtx;
cnd_t cv;
_Bool init;

void yield(int target_value, int threadid) {
    if(!init) {
        init = 1;
        mtx_init(&mtx, mtx_plain);
        cnd_init(&cv);
        printf("Initialized variables\n");
    }
    mtx_lock(&mtx);

    if (atomic_load(&global_counter) >= target_value) {
        mtx_unlock(&mtx);
        return; // Return immediately if the global counter is greater or equal to the target value.
    }
    printf("Paused thread %d at %d until %d\n", threadid, atomic_load(&global_counter), target_value);
    cnd_broadcast(&cv);

    while (atomic_load(&global_counter) < target_value) {
        cnd_wait(&cv, &mtx);
    }

    mtx_unlock(&mtx);
    printf("Resumed thread %d at %d\n", threadid, target_value);
}

void release(int target_value, int threadid) {
    mtx_lock(&mtx);
    if (atomic_load(&global_counter) > target_value) {
        mtx_unlock(&mtx);
        return; // Return immediately if the global counter is greater than the target value.
    }

    atomic_store(&global_counter, target_value + 1);
    cnd_broadcast(&cv);
    printf("Released %d\n", target_value + 1);
    mtx_unlock(&mtx);
}


_Bool __VERIFIER_nondet_bool(void) { return 0; }
char __VERIFIER_nondet_char(void) { return 0; }
char* __VERIFIER_nondet_charp(void) { return 0; }
const char* __VERIFIER_nondet_const_char_pointer(void) { return 0; }
double __VERIFIER_nondet_double(void) { return 0; }
float __VERIFIER_nondet_float(void) { return 0; }
int __VERIFIER_nondet_int(void) { return 0; }
long __VERIFIER_nondet_long(void) { return 0; }
long long __VERIFIER_nondet_longlong(void) { return 0; }
void* __VERIFIER_nondet_pointer(void) { return 0; }
short __VERIFIER_nondet_short(void) { return 0; }
size_t __VERIFIER_nondet_size_t(void) { return 0; }
uint16_t __VERIFIER_nondet_u16(void) { return 0; }
uint32_t __VERIFIER_nondet_u32(void) { return 0; }
uint8_t __VERIFIER_nondet_u8(void) { return 0; }
unsigned char __VERIFIER_nondet_uchar(void) { return 0; }
unsigned int __VERIFIER_nondet_uint(void) { return 0; }
unsigned __int128 __VERIFIER_nondet_uint128(void) { return 0; }
unsigned long __VERIFIER_nondet_ulong(void) { return 0; }
unsigned long long __VERIFIER_nondet_ulonglong(void) { return 0; }
unsigned __VERIFIER_nondet_unsigned(void) { return 0; }
unsigned char __VERIFIER_nondet_unsigned_char(void) { return 0; }
unsigned int __VERIFIER_nondet_unsigned_int(void) { return 0; }
unsigned short __VERIFIER_nondet_ushort(void) { return 0; }