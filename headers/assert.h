#define NULL ((void *)0)
extern void abort(void);
extern int printf(const char * format, ...);
/* Real glibc only ships assert() as a macro (around __assert_fail, which
   isn't a stable/linkable symbol either) -- not as a real extern function,
   so declaring it as one leaves "undefined reference to `assert'" at link
   time for any program that doesn't override the macro itself. */
#define assert(expression) ((void)((expression) ? 0 : (abort(), 0)))
