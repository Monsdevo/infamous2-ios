#include "RuntimeCoordinator.hpp"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono_literals;
static std::atomic<unsigned> failures;
static void check(bool ok, const char* name) {
    if (!ok) { failures++; fprintf(stderr, "FAIL %s\n", name); }
}
int main() {
    // Non-atomic payload visibility across the handoff is intentional: TSAN
    // must see the mutex happens-before, not a test that hides races in atomics.
    auto* c = full_runtime_control_create();
    std::atomic<bool> finished{};
    unsigned payload = 0, shutdowns = 0;
    check(runtime_renderer_start(c, [] {}, [&] { shutdowns++; }), "start");
    std::thread producer([&] {
        runtime_ppu_begin(c);
        for (unsigned n = 1; n <= 200; ++n) {
            if (!runtime_ppu_checkpoint(c, 1)) { check(false, "unexpected_stop"); break; }
            payload = n;
            bool ran = runtime_render_call(c, [&] {
                check(payload == n, "published_payload"); payload ^= 0xA5A5;
            });
            check(ran && payload == (n ^ 0xA5A5), "returned_payload");
        }
        runtime_renderer_finish(c); runtime_ppu_end(c); finished = true;
    });
    for (unsigned n = 0; n < 20; ++n) {
        full_runtime_set_active(c, 0);
        check(full_runtime_wait_quiescent(c, 2000), "pause_ack");
        auto before = full_runtime_snapshot(c);
        std::this_thread::sleep_for(1ms);
        auto after = full_runtime_snapshot(c);
        check(before.completed_jobs == after.completed_jobs && after.renderer_idle && !after.renderer_busy,
              "paused_admission_closed");
        full_runtime_set_active(c, 1);
    }
    producer.join();
    check(finished && shutdowns == 1 && full_runtime_snapshot(c).completed_jobs == 200, "complete_and_join");
    full_runtime_control_destroy(c);

    c = full_runtime_control_create();
    std::promise<void> entered, release;
    auto gate = release.get_future().share();
    std::atomic<bool> call_returned{}, accepted{};
    check(runtime_renderer_start(c, [] {}, [] {}), "busy_start");
    std::thread stopped_producer([&] {
        runtime_ppu_begin(c);
        accepted = runtime_render_call(c, [&] { entered.set_value(); gate.wait(); });
        call_returned = true;
        runtime_renderer_finish(c); runtime_ppu_end(c);
    });
    entered.get_future().wait();
    full_runtime_request_stop(c);
    check(!full_runtime_wait_quiescent(c, 5), "busy_stop_does_not_claim_idle");
    check(!call_returned, "busy_job_not_force_cancelled");
    release.set_value(); stopped_producer.join();
    auto end = full_runtime_snapshot(c);
    check(!accepted && call_returned && end.completed_jobs == 1 && !end.renderer_running && end.ppu_finished,
          "busy_stop_finishes_and_joins");
    full_runtime_control_destroy(c);

    c = full_runtime_control_create();
    runtime_ppu_begin(c);
    std::promise<void> idle_entered, shutdown_entered;
    auto idle_signal = idle_entered.get_future();
    auto shutdown_signal = shutdown_entered.get_future();
    check(runtime_renderer_start(c, [&] { idle_entered.set_value(); },
                                    [&] { shutdown_entered.set_value(); }), "producer_guard_start");
    check(runtime_render_call(c, [] {}), "producer_guard_batch");
    full_runtime_set_active(c, 0);
    check(idle_signal.wait_for(5ms) == std::future_status::timeout, "flush_waits_for_PPU_safe_point");
    std::thread resumer([&] {
        check(full_runtime_wait_quiescent(c, 2000), "producer_guard_pause_ack");
        full_runtime_set_active(c, 1);
    });
    check(runtime_ppu_checkpoint(c), "producer_guard_resume"); resumer.join();
    full_runtime_request_stop(c);
    check(shutdown_signal.wait_for(5ms) == std::future_status::timeout, "teardown_waits_for_PPU_safe_point");
    check(!runtime_ppu_checkpoint(c), "producer_guard_stop");
    runtime_renderer_finish(c); runtime_ppu_end(c);
    check(shutdown_signal.wait_for(0ms) == std::future_status::ready, "producer_guard_join");
    full_runtime_control_destroy(c);

    // Exercise the startup/stop race: observing a transient renderer-running
    // flag is insufficient; the starter needs a monotonic thread-started flag.
    for (unsigned n = 0; n < 100; ++n) {
        c = full_runtime_control_create();
        std::thread starter([&] {
            runtime_renderer_start(c, [] {}, [] {}); runtime_renderer_finish(c);
        });
        full_runtime_request_stop(c); starter.join();
        check(!full_runtime_snapshot(c).renderer_running, "startup_stop_join");
        full_runtime_control_destroy(c);
    }
    fprintf(stderr, "coordinator_stress result=%s failures=%u\n", failures ? "FAIL" : "PASS", failures.load());
    return failures ? 1 : 0;
}
