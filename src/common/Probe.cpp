#include "Probe.hpp"
#include "rsx_texture_layout.h"
#include <mach/mach.h>
#include <pthread.h>
#include <setjmp.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <sstream>

namespace probe {
namespace {
constexpr size_t MiB = 1024 * 1024;
constexpr size_t ArenaSize = 0xE0000000ull;
std::string memory(const char* stage) {
    mach_task_basic_info_data_t basic{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    kern_return_t basicRC = task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
        reinterpret_cast<task_info_t>(&basic), &count);
    task_vm_info_data_t vm{};
    count = TASK_VM_INFO_COUNT;
    kern_return_t vmRC = task_info(mach_task_self(), TASK_VM_INFO,
        reinterpret_cast<task_info_t>(&vm), &count);
    char line[384];
    std::snprintf(line, sizeof line,
        "memory stage=%s virtual_MiB=%.2f resident_MiB=%.2f footprint_MiB=%.2f basic_rc=%d vm_rc=%d",
        stage, basicRC == KERN_SUCCESS ? double(basic.virtual_size) / MiB : -1,
        basicRC == KERN_SUCCESS ? double(basic.resident_size) / MiB : -1,
        vmRC == KERN_SUCCESS ? double(vm.phys_footprint) / MiB : -1, basicRC, vmRC);
    return line;
}
struct ThreadState {
    pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
    bool ready = false;
    bool release = false;
    size_t actualStack = 0;
    bool unwind = false;
};
// No nontrivial C++ locals are crossed by _longjmp.
bool checkUnwind() {
    jmp_buf exitPoint;
    return _setjmp(exitPoint) ? true : (_longjmp(exitPoint, 1), false);
}
void* worker(void* argument) {
    auto* state = static_cast<ThreadState*>(argument);
    volatile uint8_t stackPages[128 * 1024];
    const size_t page = static_cast<size_t>(getpagesize());
    for (size_t i = 0; i < sizeof stackPages; i += page) stackPages[i] = 0x5a;
    const bool unwind = checkUnwind();
    pthread_mutex_lock(&state->lock);
    state->actualStack = pthread_get_stacksize_np(pthread_self());
    state->unwind = unwind && stackPages[0] == 0x5a;
    state->ready = true;
    pthread_cond_signal(&state->condition);
    while (!state->release) pthread_cond_wait(&state->condition, &state->lock);
    pthread_mutex_unlock(&state->lock);
    return nullptr;
}
}

std::vector<uint8_t> diagnosticTexture() {
    constexpr u32 side = 64;
    std::vector<uint8_t> guest(side * side * 4), rgba(guest.size());
    for (u32 y = 0; y < side; ++y) for (u32 x = 0; x < side; ++x) {
        size_t offset = rsx_swizzle_offset(x, y, 6, 6) * 4;
        guest[offset] = 255;
        guest[offset + 1] = static_cast<uint8_t>(x * 4);
        guest[offset + 2] = static_cast<uint8_t>(y * 4);
        guest[offset + 3] = ((x / 8 + y / 8) % 2) ? 240 : 40;
    }
    rsx_tex_layout layout{};
    rsx_texture_layout(0x85, side, side, &layout);
    rsx_texture_decode(rgba.data(), side * 4, guest.data(), side, side, &layout, 0);
    return rgba;
}

Result run(const Log& log) {
    Result result{true, {}};
    auto emit = [&](const std::string& line) {
        result.report += line + "\n";
        std::fprintf(stderr, "[probe] %s\n", line.c_str());
        if (log) log(line);
    };
    emit("diagnostic_only=1 game_frames=0 cpu_jit=0");
    emit("page_bytes=" + std::to_string(getpagesize()));
    emit(memory("baseline"));
    auto pixels = diagnosticTexture();
    // Known Morton order, channel order, and inFAMOUS lighting ramp regression.
    u8 remap[4]{};
    rsx_texture_component_remap(0xAAEE, 0x94, remap);
    const bool textureOK = rsx_swizzle_offset(0, 1, 2, 2) == 2 &&
        pixels[0] == 0 && pixels[1] == 0 && pixels[2] == 40 && pixels[3] == 255 &&
        pixels[4] == 4 && pixels[63 * 4] == 252 &&
        remap[0] == 0 && remap[1] == 0 && remap[2] == 0 && remap[3] == 0;
    emit(std::string("shared_rsx_texture=") + (textureOK ? "PASS" : "FAIL"));
    result.passed &= textureOK;

    errno = 0;
    auto* allocation = static_cast<uint8_t*>(std::calloc(1, ArenaSize));
    emit("calloc_bytes=" + std::to_string(ArenaSize) + " success=" +
         std::to_string(allocation != nullptr) + " errno=" + std::to_string(errno));
    emit(memory("after_calloc"));
    result.passed &= allocation != nullptr;
    if (allocation) {
        volatile uint8_t* arena = allocation;
        const size_t page = static_cast<size_t>(getpagesize());
        for (size_t i = 0; i < 32 * MiB; i += page) arena[i] = 0x5a;
        const size_t addresses[] = {0x10000000, 0xC0000000, 0xD0000000, ArenaSize - page};
        bool sparseOK = true;
        for (auto ea : addresses) {
            sparseOK &= arena[ea] == 0;
            arena[ea] = 0xa5;
            sparseOK &= arena[ea] == 0xa5;
        }
        emit(std::string("sparse_guest_pages=") + (sparseOK ? "PASS" : "FAIL") +
             " contiguous_touch_MiB=32 additional_pages=4");
        result.passed &= sparseOK;
        emit(memory("after_touch"));
    }

    for (size_t requested : {16 * MiB, 256 * MiB}) {
        ThreadState state;
        pthread_attr_t attributes;
        int initRC = pthread_attr_init(&attributes);
        int attrRC = initRC ? initRC : pthread_attr_setstacksize(&attributes, requested);
        pthread_t thread{};
        int createRC = attrRC ? attrRC : pthread_create(&thread, &attributes, worker, &state);
        if (!initRC) pthread_attr_destroy(&attributes);
        emit("thread requested_stack_MiB=" + std::to_string(requested / MiB) +
             " attr_rc=" + std::to_string(attrRC) + " create_rc=" + std::to_string(createRC));
        result.passed &= createRC == 0;
        if (!createRC) {
            pthread_mutex_lock(&state.lock);
            while (!state.ready) pthread_cond_wait(&state.condition, &state.lock);
            emit("thread actual_stack_MiB=" + std::to_string(state.actualStack / MiB) +
                 " touched_stack_KiB=128 setjmp_unwind=" + (state.unwind ? "PASS" : "FAIL"));
            result.passed &= state.unwind && state.actualStack >= requested;
            emit(memory("worker_alive"));
            state.release = true;
            pthread_cond_signal(&state.condition);
            pthread_mutex_unlock(&state.lock);
            int joinRC = pthread_join(thread, nullptr);
            result.passed &= joinRC == 0;
            emit("thread join_rc=" + std::to_string(joinRC));
        }
        pthread_cond_destroy(&state.condition);
        pthread_mutex_destroy(&state.lock);
    }
    std::free(allocation);
    emit(memory("after_free"));
    emit(std::string("result=") + (result.passed ? "PASS" : "FAIL"));
    return result;
}
}
