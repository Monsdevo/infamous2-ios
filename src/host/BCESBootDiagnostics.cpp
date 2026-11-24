// A bounded first-boot observer. Does not simulate a guest or render a frame.
#include <mach/mach.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <unistd.h>

extern "C" unsigned ppu_boot_frames_presented(void);

__attribute__((constructor)) static void bces_boot_watchdog() {
    const char* seconds_env = std::getenv("BCES_BOOT_SECONDS");
    if (!seconds_env) return; // Only explicit bounded diagnostics install a watchdog.
    const unsigned seconds = static_cast<unsigned>(std::strtoul(seconds_env, nullptr, 10));
    if (!seconds || seconds > 3600) return;
    const char* memory_env = std::getenv("BCES_BOOT_PHYSICAL_LIMIT_MIB");
    const unsigned memory_mib = memory_env ? static_cast<unsigned>(std::strtoul(memory_env, nullptr, 10)) : 2048;
    std::thread([seconds, memory_mib] {
        for (unsigned elapsed = 1; elapsed <= seconds; ++elapsed) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            task_vm_info_data_t info{};
            mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
            const bool measured = task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&info), &count) == KERN_SUCCESS;
            std::fprintf(stderr, "[bces-diag] elapsed=%u virtual_bytes=%llu physical_footprint=%llu resident_bytes=%llu guest_present_calls=%u\n",
                         elapsed, static_cast<unsigned long long>(info.virtual_size),
                         static_cast<unsigned long long>(info.phys_footprint),
                         static_cast<unsigned long long>(info.resident_size), ppu_boot_frames_presented());
            if (measured && memory_mib && info.phys_footprint > static_cast<uint64_t>(memory_mib) * 1024 * 1024) {
                std::fprintf(stderr, "[bces-diag] STOP physical footprint limit exceeded; exit=125\n");
                std::fflush(nullptr);
                _exit(125);
            }
        }
        std::fprintf(stderr, "[bces-diag] STOP bounded boot deadline reached; exit=124 (not game success)\n");
        std::fflush(nullptr);
        _exit(124);
    }).detach();
}
