#include "FullRuntimeProbe.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <thread>
#include <unistd.h>
using namespace std::chrono_literals;
int main(int argc, char** argv) {
    if (argc < 2 || argc > 3) return 1;
    const bool threaded = argc == 3;
    const bool stop_test = threaded && !strcmp(argv[2], "--stop-paused");
    if (threaded && !stop_test && strcmp(argv[2], "--threaded")) return 1;
    char directory[] = "/tmp/infamous2-full-XXXXXX";
    if (!mkdtemp(directory)) return 1;
    setenv("PS3RECOMP_METAL_HEADLESS", "1", 1);
    FullRuntimeControl* control = threaded ? full_runtime_control_create() : nullptr;
    std::atomic<bool> done{};
    std::atomic<unsigned> driver_failures{};
    std::thread driver;
    if (threaded) driver = std::thread([&] {
        unsigned phase = 0;
        auto deadline = std::chrono::steady_clock::now() + 15s;
        while (!done && std::chrono::steady_clock::now() < deadline) {
            auto s = full_runtime_snapshot(control);
            if (s.completed_jobs >= (phase ? 7u : 3u)) {
                full_runtime_set_active(control, 0);
                bool idle = full_runtime_wait_quiescent(control, 2000);
                auto before = full_runtime_snapshot(control);
                std::this_thread::sleep_for(50ms);
                auto after = full_runtime_snapshot(control);
                bool stable = idle && before.completed_jobs == after.completed_jobs &&
                              !after.renderer_busy && after.renderer_idle && after.ppu_parked;
                fprintf(stderr, "[lifecycle host] pause=%u idle=%d stable=%d jobs=%llu\n",
                        phase, idle, stable, after.completed_jobs);
                if (!stable) driver_failures++;
                if (stop_test) { full_runtime_request_stop(control); return; }
                full_runtime_set_active(control, 1);
                if (++phase == 2) return;
            }
            std::this_thread::sleep_for(2ms);
        }
        if (phase != 2) { driver_failures++; full_runtime_request_stop(control); }
    });
    int rc = threaded ? full_runtime_probe_threaded(argv[1], directory, nullptr, nullptr, control, 6, 20) :
                        full_runtime_probe(argv[1], directory, nullptr, nullptr, nullptr);
    done = true;
    if (driver.joinable()) driver.join();
    if (control) {
        auto s = full_runtime_snapshot(control);
        bool clean = !s.renderer_running && s.ppu_finished && s.renderer_idle;
        fprintf(stderr, "[lifecycle host] mode=%s result=%d clean=%d driver_failures=%u\n",
                stop_test ? "stop_paused" : "pause_resume", rc, clean, driver_failures.load());
        if (!clean) driver_failures++;
        full_runtime_control_destroy(control);
    }
    std::filesystem::remove_all(directory);
    return driver_failures || rc != (stop_test ? 2 : 0) ? 1 : 0;
}
