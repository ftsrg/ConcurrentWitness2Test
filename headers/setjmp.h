#define NULL ((void *)0)
typedef void* jmp_buf;
extern int setjmp(jmp_buf __jmpb);
extern void longjmp(jmp_buf __jmpb, int __ret);
