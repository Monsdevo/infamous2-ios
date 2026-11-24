#include "IOSFiberContext.h"
#include <stdlib.h>
#include <string.h>
#if !defined(__APPLE__) || !defined(__aarch64__) || defined(__arm64e__)
#error This adapter is validated only for Apple arm64, not arm64e.
#endif
// C declarations of the two assembly symbols. transfer_t is returned in
// x0/x1 on Apple arm64, matching the locked Boost.Context detail header.
typedef struct { void* context; void* data; } Transfer;
extern void* make_fcontext(void* top, size_t size, void (*entry)(Transfer));
extern Transfer jump_fcontext(void* to, void* data);
typedef struct { IOSFiberContext* from; IOSFiberContext* to; } Switch;
static _Thread_local IOSFiberContext* current;
static IOSFiberContext* arrived(Transfer transfer) {
    Switch* request = transfer.data;
    request->from->handle = transfer.context;
    current = request->to;
    return current;
}
static void trampoline(Transfer transfer) {
    IOSFiberContext* ctx = arrived(transfer);
    ctx->entry(ctx->lo, ctx->hi);
    // cellFiber's own trampoline must explicitly return to the scheduler.
    abort();
}
void ios_fiber_scheduler_init(IOSFiberContext* scheduler) {
    memset(scheduler, 0, sizeof *scheduler);
    current = scheduler;
}
int ios_fiber_make(IOSFiberContext* ctx, void* stack, size_t size,
                   void (*entry)(int, int), int lo, int hi) {
    if (!ctx || !stack || size < 4096 || !entry) return -1;
    memset(ctx, 0, sizeof *ctx);
    ctx->entry = entry; ctx->lo = lo; ctx->hi = hi;
    ctx->handle = make_fcontext((char*)stack + size, size, trampoline);
    return ctx->handle ? 0 : -1;
}
void ios_fiber_swap(IOSFiberContext* from, IOSFiberContext* to) {
    Switch request = {from, to};
    // The outgoing context is returned by jump_fcontext to its destination.
    // Save it before destination code can switch back, including A -> B.
    arrived(jump_fcontext(to->handle, &request));
}
_Noreturn void ios_fiber_set(IOSFiberContext* to) {
    ios_fiber_swap(current, to);
    abort();
}
