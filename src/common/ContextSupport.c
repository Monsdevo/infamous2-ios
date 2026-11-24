#define _XOPEN_SOURCE 600
#include "RuntimeProbe.h"
#include <ucontext.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
static ucontext_t caller, callee;
static int entered;
static void entry(void) { entered = 1; setcontext(&caller); abort(); }
int runtime_probe_ucontext(int* get_rc, int* get_error, int* swap_rc, int* swap_error) {
    entered = 0;
    memset(&caller, 0, sizeof caller); memset(&callee, 0, sizeof callee);
    errno = 0;
    *get_rc = getcontext(&callee); *get_error = errno;
    *swap_rc = -999; *swap_error = 0;
    if (*get_rc != 0) return 0;
    void* stack = malloc(64 * 1024);
    if (!stack) return 0;
    callee.uc_stack.ss_sp = stack; callee.uc_stack.ss_size = 64 * 1024; callee.uc_link = &caller;
    makecontext(&callee, entry, 0);
    errno = 0;
    *swap_rc = swapcontext(&caller, &callee); *swap_error = errno;
    free(stack);
    return entered;
}
