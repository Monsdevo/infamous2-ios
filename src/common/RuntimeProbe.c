#include "RuntimeProbe.h"
#include "win32_compat.h"
#include "cellFiber.h"
#include <stdatomic.h>
#include <stdarg.h>

extern uint8_t* vm_base;
static RuntimeProbeLog logger;
static void* logger_context;
static unsigned checks, failures;
static void emit(const char* format, ...) {
    char line[512];
    va_list args;
    va_start(args, format);
    vsnprintf(line, sizeof line, format, args);
    va_end(args);
    fprintf(stderr, "[runtime probe] %s\n", line);
    if (logger) logger(line, logger_context);
}
#define CHECK(c) do { checks++; if (!(c)) { failures++; emit("FAIL: %s (last_error=%u)", #c, GetLastError()); } } while (0)

static int query(const void* p, DWORD state, DWORD protect) {
    MEMORY_BASIC_INFORMATION info;
    if (VirtualQuery(p, &info, sizeof info) != sizeof info) return 0;
    const uintptr_t a = (uintptr_t)p, b = (uintptr_t)info.BaseAddress;
    return a >= b && a - b < info.RegionSize && info.State == state && info.Protect == protect;
}
static void virtual_memory(void) {
    emit("phase=vm begin");
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    size_t pg = si.dwPageSize;
    CHECK(pg && !(pg & (pg - 1)));
    unsigned char* p = VirtualAlloc(NULL, 3 * pg, MEM_RESERVE, PAGE_NOACCESS);
    CHECK(p != NULL);
    if (!p) return;
    CHECK(query(p, MEM_RESERVE, PAGE_NOACCESS));
    CHECK(VirtualAlloc(p + pg, pg, MEM_COMMIT, PAGE_READWRITE) == p + pg);
    CHECK(query(p + pg + 17, MEM_COMMIT, PAGE_READWRITE));
    MEMORY_BASIC_INFORMATION info;
    CHECK(VirtualQuery(p + pg, &info, sizeof info) == sizeof info && info.AllocationBase == p);
    CHECK(query(p, MEM_RESERVE, PAGE_NOACCESS));
    CHECK(query(p + 2 * pg, MEM_RESERVE, PAGE_NOACCESS));
    memset(p + pg, 0xA5, pg);
    CHECK(p[pg] == 0xA5 && p[2 * pg - 1] == 0xA5);
    CHECK(!IsBadReadPtr(p + pg, pg) && !IsBadWritePtr(p + pg, pg));
    CHECK(IsBadReadPtr(p + pg - 1, 2) && IsBadReadPtr(p + 2 * pg - 1, 2));
    DWORD old;
    CHECK(VirtualProtect(p + pg, pg, PAGE_READONLY, &old));
    CHECK(query(p + pg, MEM_COMMIT, PAGE_READONLY));
    CHECK(!IsBadReadPtr(p + pg, pg) && IsBadWritePtr(p + pg, 1));
    CHECK(VirtualFree(p + pg, pg, MEM_DECOMMIT));
    CHECK(query(p + pg, MEM_RESERVE, PAGE_NOACCESS));
    CHECK(VirtualFree(p, 0, MEM_RELEASE));
    CHECK(query(p, MEM_FREE, PAGE_NOACCESS));
    // These mappings are absent from the shim's reservation table. The OS
    // query must work for them too, including addresses above 4 GiB on arm64.
    unsigned char* heap = malloc(pg);
    CHECK(heap != NULL);
    if (heap) { CHECK(!IsBadWritePtr(heap, pg)); free(heap); }
    CHECK(!IsBadReadPtr(&si, sizeof si));
    CHECK(!IsBadCodePtr((const void*)(uintptr_t)&virtual_memory));
    emit("phase=vm end host_page=%zu guest_subpage_protection_tested=0 failures=%u", pg, failures);
}

static _Atomic unsigned spin_ready, spin_stop, spin_counter;
static size_t actual_stack;
static DWORD WINAPI spin_worker(void* arg) {
    (void)arg;
    actual_stack = pthread_get_stacksize_np(pthread_self());
    atomic_store_explicit(&spin_ready, 1, memory_order_release);
    // No locks, allocator or library calls while this worker may be suspended.
    while (!atomic_load_explicit(&spin_stop, memory_order_relaxed))
        atomic_fetch_add_explicit(&spin_counter, 1, memory_order_relaxed);
    return 73;
}
static void threads(size_t stack) {
    emit("phase=thread begin requested_stack=%zu", stack);
    atomic_store(&spin_ready, 0); atomic_store(&spin_stop, 0); atomic_store(&spin_counter, 0);
    actual_stack = 0;
    HANDLE t = CreateThread(NULL, stack, spin_worker, NULL, CREATE_SUSPENDED, NULL);
    CHECK(t != NULL);
    if (!t) return;
    CHECK(!atomic_load(&spin_ready));
    CHECK(ResumeThread(t) == 1);
    ULONGLONG deadline = GetTickCount64() + 2000;
    while ((!atomic_load_explicit(&spin_ready, memory_order_acquire) || !atomic_load(&spin_counter)) &&
           GetTickCount64() < deadline) Sleep(1);
    CHECK(atomic_load(&spin_ready) && atomic_load(&spin_counter));
    // pthread may report additional bookkeeping/alignment space. Detect a
    // fallback to a smaller default stack without requiring exact equality.
    CHECK(actual_stack >= stack);
    DWORD suspended = SuspendThread(t);
    CHECK(suspended == 0);
    if (suspended == 0) {
        unsigned frozen = atomic_load(&spin_counter);
        Sleep(10);
        CHECK(atomic_load(&spin_counter) == frozen);
        CONTEXT ctx = {0};
        ctx.ContextFlags = CONTEXT_FULL;
        BOOL got = GetThreadContext(t, &ctx);
        CHECK(got && ctx.Pc && ctx.Sp);
        if (got) {
            BOOL set = SetThreadContext(t, &ctx);
            emit("thread_context read=%d same_state_write=%d last_error=%u", got, set, GetLastError());
            CHECK(set);
        }
        DWORD nested = SuspendThread(t);
        CHECK(nested == 1);
        if (nested == 1) { CHECK(ResumeThread(t) == 2); CHECK(atomic_load(&spin_counter) == frozen); }
        CHECK(ResumeThread(t) == 1);
        deadline = GetTickCount64() + 2000;
        while (atomic_load(&spin_counter) == frozen && GetTickCount64() < deadline) Sleep(1);
        CHECK(atomic_load(&spin_counter) != frozen);
    }
    atomic_store(&spin_stop, 1);
    CHECK(WaitForSingleObject(t, 2000) == WAIT_OBJECT_0);
    DWORD exit_code = 0;
    CHECK(GetExitCodeThread(t, &exit_code) && exit_code == 73);
    CHECK(CloseHandle(t));
    emit("phase=thread end actual_stack=%zu failures=%u", actual_stack, failures);
}

enum { SWITCHES = 4000 };
static CellFiber fibers[2];
static unsigned ran[2], bad_args, bad_stack, bad_order, last;
static int ping;
static uint32_t be32(unsigned a) {
    return ((uint32_t)vm_base[a] << 24) | ((uint32_t)vm_base[a+1] << 16) |
           ((uint32_t)vm_base[a+2] << 8) | vm_base[a+3];
}
static void fiber_entry(u64 arg) {
    unsigned who = (unsigned)(arg & 1);
    if (arg != (UINT64_C(0xA17F123400000000) | who)) bad_args++;
    for (unsigned i = 0; i < SWITCHES; ++i) {
        volatile uint64_t canary[8];
        for (unsigned k = 0; k < 8; ++k) canary[k] = arg + k + i;
        ran[who]++;
        if (ping) {
            if (last == who) bad_order++;
            last = who;
            if (who == 1 && i == SWITCHES - 1) cellFiberPpuYieldFiber();
            else cellFiberPpuSwitchFiber(fibers[1 - who]);
        } else cellFiberPpuYieldFiber();
        for (unsigned k = 0; k < 8; ++k) if (canary[k] != arg + k + i) bad_stack++;
    }
    // Returning tests the real trampoline's setcontext(scheduler) path.
}
static void fiber_round(int direct) {
    emit("phase=fiber begin direct=%d switches_per_fiber=%u", direct, SWITCHES);
    vm_base = calloc(1, 1024 * 1024);
    CHECK(vm_base != NULL);
    if (!vm_base) return;
    ran[0] = ran[1] = bad_args = bad_stack = bad_order = 0; last = 1; ping = direct;
    s32 rc = cellFiberPpuInitialize();
    CHECK(rc == CELL_OK);
    if (rc != CELL_OK) { free(vm_base); vm_base = NULL; return; }
    CHECK(cellFiberPpuAttributeInitialize((CellFiberAttribute*)(uintptr_t)0x1000) == CELL_OK);
    CHECK(be32(0x1008) == CELL_FIBER_DEFAULT_STACK_SIZE);
    int created = 1;
    for (unsigned who = 0; who < 2; ++who) {
        rc = cellFiberPpuCreateFiber((CellFiber*)(uintptr_t)(0x1100 + who * 4), fiber_entry,
            UINT64_C(0xA17F123400000000) | who, (const CellFiberAttribute*)(uintptr_t)0x1000);
        CHECK(rc == CELL_OK);
        if (rc != CELL_OK) { created = 0; break; }
        fibers[who] = be32(0x1100 + who * 4);
    }
    if (created) {
        if (direct) CHECK(cellFiberPpuSwitchFiber(fibers[0]) == CELL_OK);
        else for (unsigned i = 0; i < SWITCHES; ++i) {
            CHECK(cellFiberPpuSwitchFiber(fibers[0]) == CELL_OK);
            CHECK(cellFiberPpuSwitchFiber(fibers[1]) == CELL_OK);
        }
        CHECK(ran[0] == SWITCHES && ran[1] == SWITCHES);
        // Resume past the last yield/switch so the canaries are checked and
        // both real trampolines return to the scheduler, then inspect state.
        for (unsigned who = 0; who < 2; ++who) {
            CHECK(cellFiberPpuSwitchFiber(fibers[who]) == CELL_OK);
            CHECK(cellFiberPpuGetFiberState(fibers[who], (u32*)(uintptr_t)0x1200) == CELL_OK);
            CHECK(be32(0x1200) == CELL_FIBER_STATE_TERMINATED);
            CHECK(cellFiberPpuDeleteFiber(fibers[who]) == CELL_OK);
        }
        CHECK(!bad_args && !bad_stack && !bad_order);
    }
    CHECK(cellFiberPpuFinalize() == CELL_OK);
    free(vm_base); vm_base = NULL;
    emit("phase=fiber end direct=%d A=%u B=%u bad_args=%u bad_stack=%u bad_order=%u failures=%u",
         direct, ran[0], ran[1], bad_args, bad_stack, bad_order, failures);
}
int runtime_probe_run(RuntimeProbeLog log, void* context) {
    logger = log; logger_context = context; checks = failures = 0;
    emit("runtime_probe begin synthetic_memory=1 game_execution=0 cpu_jit=0");
    virtual_memory();
    threads(16u * 1024 * 1024);
    threads(256u * 1024 * 1024);
    int gr, ge, sr, se;
    int entered = runtime_probe_ucontext(&gr, &ge, &sr, &se);
    emit("native_ucontext get_rc=%d errno=%d swap_rc=%d errno=%d entered=%d", gr, ge, sr, se, entered);
#if defined(PS3RECOMP_IOS_FCONTEXT)
    emit("fiber_backend=boost_fcontext native_ucontext_required=0");
    fiber_round(0); fiber_round(1);
#else
    emit("fiber_backend=native_ucontext native_ucontext_required=1");
    CHECK(entered == 1);
    if (entered) { fiber_round(0); fiber_round(1); }
#endif
    emit("runtime_result=%s checks=%u failures=%u", failures ? "FAIL" : "PASS", checks, failures);
    logger = NULL; logger_context = NULL;
    return failures ? 1 : 0;
}
