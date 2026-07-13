// Concurrent memory-safety violation: the freer thread frees p before main
// dereferences it, so `*p = 1` in main is a use-after-free.
// Property: G valid-deref
// Preprocessed equivalent of the sv-witnesses concurrent-mem-safety.c example.

typedef unsigned long int pthread_t;
union pthread_attr_t { char __size[56]; long int __align; };
typedef union pthread_attr_t pthread_attr_t;
extern int pthread_create(pthread_t *__newthread, const pthread_attr_t *__attr, void *(*__start_routine)(void *), void *__arg);
extern int pthread_join(pthread_t __th, void **__thread_return);

typedef unsigned long size_t;
extern void free(void *ptr);
extern void *malloc(size_t size);

int freed = 0;
int *p;

void *freer(void *arg) {
    free(p);
    freed = 1;
    return ((void *)0);
}

int main(void) {
    p = malloc(sizeof(int));
    pthread_t t;
    pthread_create(&t, ((void *)0), freer, ((void *)0));
    if (freed == 1) {
        *p = 1;
    }
    pthread_join(t, ((void *)0));
    return 0;
}
