#define NULL ((void *)0)
extern void (*signal(int sig, void (*func)(int)))(int);
extern int raise(int sig);
