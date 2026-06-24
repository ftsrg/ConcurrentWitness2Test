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
#include <pthread.h>
#include <stdlib.h>

void __VERIFIER_atomic_begin() {

}
void __VERIFIER_atomic_end(void) {

}
atomic_int c2tt_global_counter = 0;
mtx_t c2tt_mtx;
cnd_t c2tt_cv;
once_flag c2tt_once = ONCE_FLAG_INIT;

/* The segment counter value the witness expects once every one of its
 * segments has been passed, set once (before any thread is spawned, see
 * witness2ast.inject_expected_final_slot) from the witness' last computed
 * slot. -1 (the default, for any program svcomp.c is linked into that
 * isn't actually witness-instrumented) means "no constraint": reach_error()
 * always counts. */
static int c2tt_expected_final_slot = -1;

void __c2tt_set_expected_final_slot(int slot) {
    c2tt_expected_final_slot = slot;
}

void reach_error() {
    /* A reach_error() reached while the witness' schedule hasn't been
     * fully played out yet -- some other, unrelated nondeterministic
     * choice got the program here -- doesn't confirm the witness, so it
     * doesn't count as the violation. */
    if (c2tt_expected_final_slot >= 0
        && atomic_load(&c2tt_global_counter) != c2tt_expected_final_slot) {
        return;
    }
    printf("Reached error!\n");
    fflush( stdout );
    exit(74);
}

/* Thread-local logical thread ID: 0 = main thread, k = k-th spawned thread.
 * Spawned threads never set this themselves -- it is fixed before they run
 * a single line of program code, by __c2tt_thread_proxy below. The main
 * thread is pre-initialized to 0 by c2tt_init(), called from main() below. */
static _Thread_local int c2tt_logical_tid = -1;

/* Pre-initialize the main thread's logical tid. Called from main() (the
 * real entry point, defined at the bottom of this file) before __c2tt_main
 * -- the instrumented program's renamed main -- runs any program code. */
static void c2tt_init(void) {
    c2tt_logical_tid = 0;
}

/* call_once keeps the initialization race-free: a plain initialized-flag
 * would itself be reported as a data race by the thread sanitizer. */
static void c2tt_initialize(void) {
    mtx_init(&c2tt_mtx, mtx_plain);
    cnd_init(&c2tt_cv);
    printf("Initialized variables\n");
}

/* Returns 1 iff the current segment counter equals `slot` and the current
 * thread's logical witness ID equals `logical_tid`. Used by the runtime
 * nondet/assumption/branching guards to decide whether the witness wants
 * something to happen right here, right now, on this thread. */
int __c2tt_should_use_assumed(int slot, int logical_tid) {
    return atomic_load(&c2tt_global_counter) == slot
        && c2tt_logical_tid == logical_tid;
}

/* General assumption/branching guard: `matches` is the segment/thread
 * check above (or 1, unconditionally, for formats with no segment counter);
 * `holds` is whatever the witness claims should be true right now (an
 * assumption's expression, or a branching statement's controlling
 * expression compared against the witness' recorded direction). If the
 * witness wanted this checked and it doesn't hold, this execution has
 * diverged from the witness, so it exits cleanly instead of running on
 * down a path the witness doesn't describe. */
void __concurrentwit2test_assume(int matches, int holds) {
    if (matches && !holds) {
        exit(0);
    }
}

/* Blob handed from pthread_create's caller to __c2tt_thread_proxy: the
 * program's real start routine and argument, plus the logical witness ID
 * the new thread should run as (or -1 if this particular pthread_create
 * call is not the one the witness is pinning -- e.g. a different loop
 * iteration spawning with the same start routine). Heap-allocated because
 * pthread_create can return, unwinding the caller's stack, before the new
 * thread gets around to reading it. */
struct __c2tt_thread_arg {
    void *real_arg;
    void *(*real_func)(void *);
    int logical_tid;
};

void *__c2tt_make_thread_arg(void *(*real_func)(void *), void *real_arg, int logical_tid) {
    struct __c2tt_thread_arg *targ = malloc(sizeof(struct __c2tt_thread_arg));
    targ->real_func = real_func;
    targ->real_arg = real_arg;
    targ->logical_tid = logical_tid;
    return targ;
}

/* Passed to pthread_create in place of the program's real start routine.
 * The real routine may be shared by several pthread_create call sites (or
 * the same call site looped), so the logical ID lives on this per-call
 * argument blob rather than on the routine itself. */
void *__c2tt_thread_proxy(void *raw_arg) {
    struct __c2tt_thread_arg *targ = (struct __c2tt_thread_arg *)raw_arg;
    void *real_arg = targ->real_arg;
    void *(*real_func)(void *) = targ->real_func;
    c2tt_logical_tid = targ->logical_tid;
    free(targ);
    printf("Thread %d starting\n", c2tt_logical_tid);
    return real_func(real_arg);
}

void __concurrentwit2test_yield(int target_value, int threadid) {
    /* Code shared by threads outside the witness' schedule (or a thread
     * other than the one this particular schedule point targets) must run
     * on without participating -- it has nothing to wait for and nothing
     * to release. */
    if (c2tt_logical_tid != threadid) {
        return;
    }
    call_once(&c2tt_once, c2tt_initialize);
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

void __concurrentwit2test_release(int target_value, int threadid) {
    /* Symmetric with yield: not the targeted thread, nothing to do. */
    if (c2tt_logical_tid != threadid) {
        return;
    }
    call_once(&c2tt_once, c2tt_initialize);
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

/* witness2ast renames the instrumented program's main to __c2tt_main and
 * normalizes its signature to (int, char **) -- adding the two parameters
 * even when the program's main took none -- so this call always matches the
 * definition. The match is required on WASM/WASIX (the web demo runtime),
 * where a direct call whose signature differs from the callee's definition
 * traps, rather than ignoring the extra arguments as a native ABI does. */
extern int __c2tt_main(int argc, char **argv);

/* We drive __c2tt_main from a real main here so the process can
 * pthread_exit() rather than return. Returning from the original main would
 * tear the process down the moment the main thread is done, even while
 * spawned threads still have schedule segments -- or, for a data-race
 * witness, the final racing access -- left to execute. Calling pthread_exit
 * on the main thread instead keeps the process alive until every other
 * thread has finished. */
int main(int argc, char **argv) {
    printf("Starting main\n");
    c2tt_init();
    printf("Calling __c2tt_main\n");
    __c2tt_main(argc, argv);
    printf("Main done, calling pthread_exit\n");
    pthread_exit(NULL);
    return 0;
}
