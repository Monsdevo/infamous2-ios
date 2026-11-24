#include "BCESIOS.h"
#include "RSXMetalSurface.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <future>
#include <thread>
#include <cstdio>
static std::atomic<unsigned> flushes{0};
static std::atomic<bool> gpu_done{false};
extern "C" void rsx_draw_engine_flush() { ++flushes; }
extern "C" RSXSurfaceStats rsx_metal_backend_ios_stats() { return {1, gpu_done ? 1u : 0u, 0, 0}; }
int main() {
    // No new GPU batch was admitted: quick resume/pause must preserve idle.
    for (unsigned i = 0; i < 100; ++i) {
        bces_ios_set_active(1); bces_ios_set_active(0);
        assert(bces_ios_wait_renderer_idle(1));
    }
    bces_ios_set_active(1);
    std::promise<void> admitted, finish;
    auto release = finish.get_future();
    std::thread owner([&] {
        bces_ios_frame_begin(); admitted.set_value(); release.wait();
        bces_ios_frame_end();
        bces_ios_frame_begin(); bces_ios_frame_end();
    });
    admitted.get_future().wait();
    bces_ios_set_active(0);
    assert(!bces_ios_wait_renderer_idle(2)); // CPU batch still busy.
    finish.set_value();
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (!flushes && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
    assert(flushes);
    assert(!bces_ios_wait_renderer_idle(2)); // GPU completion still pending.
    gpu_done = true;
    assert(bces_ios_wait_renderer_idle(2000));
    bces_ios_set_active(1); owner.join();
    std::puts("PASS: fast resume/pause, CPU batch and GPU fence acknowledgement");
}
