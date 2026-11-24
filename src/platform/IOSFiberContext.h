#pragma once
#include <stddef.h>
// Cooperative contexts only, on one host thread. Not a signal/ucontext or
// arbitrary thread-register replacement. ABI: Boost.Context 1.88 fcontext.
typedef struct IOSFiberContext {
    void* handle;
    void (*entry)(int, int);
    int lo, hi;
} IOSFiberContext;
void ios_fiber_scheduler_init(IOSFiberContext* scheduler);
int ios_fiber_make(IOSFiberContext* ctx, void* stack, size_t size,
                   void (*entry)(int, int), int lo, int hi);
void ios_fiber_swap(IOSFiberContext* from, IOSFiberContext* to);
_Noreturn void ios_fiber_set(IOSFiberContext* to);
