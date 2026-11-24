#include "RuntimeCoordinator.hpp"
#include <pthread.h>
#include <condition_variable>
#include <chrono>
#include <mutex>
#include <utility>

struct FullRuntimeControl {
    std::mutex mutex;
    std::condition_variable changed;
    bool active = true, stop = false, closing = false;
    bool registered = false, ppu_parked = false, ppu_finished = false;
    bool renderer = false, busy = false, idle = true, pending = false;
    bool thread_created = false, thread_started = false;
    uint64_t submitted = 0, completed = 0, cancelled = 0;
    pthread_t thread{};
    std::function<void()> job, quiesce, shutdown;
};
using Lock = std::unique_lock<std::mutex>;
using namespace std::chrono_literals;
extern "C" void apple_runtime_with_pool(void (*)(void*), void*);
static void pooled(std::function<void()>& work) {
    apple_runtime_with_pool([](void* p) { (*static_cast<std::function<void()>*>(p))(); }, &work);
}

FullRuntimeControl* full_runtime_control_create(void) { return new FullRuntimeControl; }
void full_runtime_control_destroy(FullRuntimeControl* c) { delete c; } // only after PPU join
void full_runtime_set_active(FullRuntimeControl* c, int active) {
    if (!c) return;
    Lock lock(c->mutex);
    if (c->stop || c->closing) return;
    c->active = active != 0;
    // Changing admission is not GPU work. Invalidating an already-idle
    // renderer here loses acknowledgement on rapid resume -> pause when the
    // sleeping renderer has not observed the short resume edge yet.
    c->changed.notify_all();
}
void full_runtime_request_stop(FullRuntimeControl* c) {
    if (!c) return;
    Lock lock(c->mutex);
    c->stop = true; c->active = false;
    c->changed.notify_all();
}
FullRuntimeSnapshot full_runtime_snapshot(FullRuntimeControl* c) {
    if (!c) return {};
    Lock lock(c->mutex);
    return {c->submitted, c->completed, c->cancelled, c->active, c->stop,
            c->renderer, c->busy, c->idle, c->registered, c->ppu_parked, c->ppu_finished};
}
int full_runtime_wait_quiescent(FullRuntimeControl* c, unsigned timeout_ms) {
    if (!c) return 0;
    Lock lock(c->mutex);
    return c->changed.wait_for(lock, std::chrono::milliseconds(timeout_ms), [&] {
        return !c->busy && c->idle && (!c->registered || c->ppu_parked || c->ppu_finished);
    });
}
void runtime_ppu_begin(FullRuntimeControl* c) {
    Lock lock(c->mutex); c->registered = true; c->changed.notify_all();
}
void runtime_ppu_end(FullRuntimeControl* c) {
    Lock lock(c->mutex); c->ppu_finished = true; c->ppu_parked = true; c->changed.notify_all();
}
static bool checkpoint_locked(FullRuntimeControl* c, Lock& lock) {
    if (!c->active || c->stop) {
        c->ppu_parked = true; c->changed.notify_all();
        c->changed.wait(lock, [&] { return c->active || c->stop; });
    }
    if (c->stop) return false;
    c->ppu_parked = false;
    return true;
}
bool runtime_ppu_checkpoint(FullRuntimeControl* c, unsigned delay_ms) {
    Lock lock(c->mutex);
    if (!checkpoint_locked(c, lock)) return false;
    if (delay_ms) {
        // Test pacing is interruptible by pause/stop. This is not a title clock.
        c->changed.wait_for(lock, std::chrono::milliseconds(delay_ms), [&] { return !c->active || c->stop; });
        return checkpoint_locked(c, lock);
    }
    return true;
}
static void* renderer_main(void* opaque) {
    auto* c = static_cast<FullRuntimeControl*>(opaque);
    pthread_setname_np("inFAMOUS RSX owner");
    Lock lock(c->mutex);
    c->renderer = true; c->thread_started = true; c->changed.notify_all();
    for (;;) {
        if (c->stop || c->closing) break;
        if (!c->active) {
            // GCM setup/callback code on the PPU can also touch renderer
            // state. Do not flush or release it until the producer is parked.
            if (c->registered && !c->ppu_parked && !c->ppu_finished) {
                c->changed.wait(lock, [&] {
                    return c->ppu_parked || c->ppu_finished || c->active || c->stop || c->closing;
                });
                continue;
            }
            if (!c->idle) {
                lock.unlock(); pooled(c->quiesce); lock.lock();
                c->idle = true; c->changed.notify_all();
            }
            c->changed.wait(lock, [&] { return c->active || c->stop || c->closing; });
            continue;
        }
        if (!c->pending) {
            c->changed.wait(lock, [&] { return c->pending || !c->active || c->stop || c->closing; });
            continue;
        }
        auto job = std::move(c->job);
        c->pending = false; c->busy = true; c->idle = false;
        lock.unlock(); pooled(job); lock.lock();
        c->busy = false; c->completed++; c->changed.notify_all();
    }
    c->changed.wait(lock, [&] { return !c->registered || c->ppu_parked || c->ppu_finished; });
    if (c->pending) { c->job = {}; c->pending = false; c->cancelled++; }
    c->busy = true; // teardown also belongs to the renderer, including GPU wait
    lock.unlock(); pooled(c->shutdown); lock.lock();
    c->busy = false; c->idle = true; c->renderer = false; c->changed.notify_all();
    return nullptr;
}
bool runtime_renderer_start(FullRuntimeControl* c, std::function<void()> idle,
                            std::function<void()> shutdown) {
    Lock lock(c->mutex);
    if (c->thread_created || c->thread_started || c->stop || c->closing) return false;
    c->quiesce = std::move(idle); c->shutdown = std::move(shutdown);
    pthread_attr_t attr;
    int rc = pthread_attr_init(&attr);
    bool initialized = rc == 0;
    if (!rc) rc = pthread_attr_setstacksize(&attr, 16u * 1024 * 1024);
    if (!rc) rc = pthread_create(&c->thread, &attr, renderer_main, c);
    if (initialized) pthread_attr_destroy(&attr);
    if (rc) return false;
    c->thread_created = true;
    c->changed.wait(lock, [&] { return c->thread_started; });
    return true;
}
bool runtime_render_call(FullRuntimeControl* c, std::function<void()> job) {
    Lock lock(c->mutex);
    if (!checkpoint_locked(c, lock) || !c->renderer || c->closing) return false;
    c->job = std::move(job); c->pending = true; c->submitted++;
    const uint64_t sequence = c->submitted;
    c->ppu_parked = true; c->changed.notify_all();
    c->changed.wait(lock, [&] { return c->completed >= sequence || !c->renderer; });
    if (c->completed < sequence) return false; // pending work cancelled by stop
    return checkpoint_locked(c, lock);
}
void runtime_renderer_finish(FullRuntimeControl* c) {
    {
        Lock lock(c->mutex);
        if (!c->thread_created) return;
        c->closing = true; c->ppu_parked = true; c->changed.notify_all();
    }
    pthread_join(c->thread, nullptr);
    Lock lock(c->mutex); c->thread_created = false;
    c->job = {}; c->quiesce = {}; c->shutdown = {};
}
