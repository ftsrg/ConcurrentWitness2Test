/*
 *  Copyright 2023 Budapest University of Technology and Economics
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */


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
    fflush( stdout );
    exit(74);
}

atomic_int c2tt_global_counter = ATOMIC_VAR_INIT(0);
mtx_t c2tt_mtx;
cnd_t c2tt_cv;
_Bool c2tt_init;

void yield(int target_value, int threadid) {
    if(!c2tt_init) {
        c2tt_init = 1;
        mtx_init(&c2tt_mtx, mtx_plain);
        cnd_init(&c2tt_cv);
        printf("Initialized variables\n");
    }
    mtx_lock(&c2tt_mtx);

    if (atomic_load(&c2tt_global_counter) >= target_value) {
        mtx_unlock(&c2tt_mtx);
        return; // Return immediately if the global counter is greater or equal to the target value.
    }
    printf("Paused thread %d at %d until %d\n", threadid, atomic_load(&c2tt_global_counter), target_value);
    cnd_broadcast(&c2tt_cv);

    while (atomic_load(&c2tt_global_counter) < target_value) {
        cnd_wait(&c2tt_cv, &c2tt_mtx);
    }

    mtx_unlock(&c2tt_mtx);
    printf("Resumed thread %d at %d\n", threadid, target_value);
}

void release(int target_value, int threadid) {
    mtx_lock(&c2tt_mtx);
    if (atomic_load(&c2tt_global_counter) > target_value) {
        mtx_unlock(&c2tt_mtx);
        return; // Return immediately if the global counter is greater than the target value.
    }

    atomic_store(&c2tt_global_counter, target_value + 1);
    cnd_broadcast(&c2tt_cv);
    printf("Released %d\n", target_value + 1);
    mtx_unlock(&c2tt_mtx);
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
