#include "HalfDepthProbe.h"
#include "ps3emu/ps3_ftrace.h"
#include <pthread.h>
#include <stdio.h>
#include <string.h>

extern uint8_t* vm_base;
static char directory[1024];
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static uint32_t guest_address;
static uint32_t admitted_frame, admitted_state;
static uint32_t reference_frame, reference_address, queued_frame;
static uint64_t admission_trace, trace_id, finished_trace;
static uint8_t reference[BCES_HALF_DEPTH_BYTES];
// The FIFO sets this immediately around the matching vtable call.
static _Thread_local uint32_t selected_frame;

void bces_half_depth_configure(const char* path)
{
    if (path) snprintf(directory, sizeof directory, "%s", path);
}

static uint64_t active_trace_time(void)
{
    if (!PS3_FT_ON()) return 0;
    const uint64_t now = ps3_ft_now();
    return now >= g_ps3_ft.start && now <= g_ps3_ft.end ? now : 0;
}

void bces_half_depth_admit(uint32_t frame, uint32_t state, uint32_t address)
{
    const uint64_t now = active_trace_time();
    if (!now) return;
    pthread_mutex_lock(&lock);
    if (admission_trace != g_ps3_ft.start || frame != admitted_frame || state != admitted_state ||
        address != __atomic_load_n(&guest_address, __ATOMIC_RELAXED)) {
        admission_trace = g_ps3_ft.start;
        admitted_frame = frame;
        admitted_state = state;
        __atomic_store_n(&guest_address, address, __ATOMIC_RELEASE);
        ps3_ft_span(470, frame, address, state, now, now);
    }
    pthread_mutex_unlock(&lock);
}

void bces_half_depth_reference(uint32_t state)
{
    if (!active_trace_time()) return;
    pthread_mutex_lock(&lock);
    const uint32_t address = __atomic_load_n(&guest_address, __ATOMIC_ACQUIRE);
    const uint64_t current = g_ps3_ft.start;
    if (admission_trace == current && state == admitted_state && address && vm_base && !queued_frame &&
        finished_trace != current &&
        (trace_id != current || reference_frame != admitted_frame)) {
        // The atomic iterator has moved past pass 0, including its tile writes.
        memcpy(reference, vm_base + address, sizeof reference);
        reference_frame = admitted_frame;
        reference_address = address;
        trace_id = current;
        uint64_t now = ps3_ft_now();
        ps3_ft_span(471, reference_frame, address, state, now, now);
    }
    pthread_mutex_unlock(&lock);
}

void bces_half_depth_select(uint32_t frame) { selected_frame = frame; }

uint32_t bces_half_depth_claim(void)
{
    if (!selected_frame || !directory[0] || !active_trace_time()) return 0;
    pthread_mutex_lock(&lock);
    uint32_t frame = 0;
    if (!queued_frame && reference_frame == selected_frame &&
        trace_id == g_ps3_ft.start && finished_trace != trace_id)
        frame = queued_frame = selected_frame;
    pthread_mutex_unlock(&lock);
    return frame;
}

void bces_half_depth_complete(uint32_t frame, const void* pixels)
{
    if (!frame) return;
    pthread_mutex_lock(&lock);
    if (frame == queued_frame) {
        if (pixels) {
            char path[1100], temporary[1100];
            snprintf(path, sizeof path, "%s/ssao-half-depth.bin", directory);
            snprintf(temporary, sizeof temporary, "%s/ssao-half-depth.tmp", directory);
            FILE* file = fopen(temporary, "wb");
            const uint64_t header[] = {trace_id, frame, reference_address};
            if (file) {
                int ok = fwrite(header, sizeof header, 1, file) == 1 &&
                    fwrite(reference, sizeof reference, 1, file) == 1 &&
                    fwrite(pixels, sizeof reference, 1, file) == 1;
                if (fclose(file) == 0 && ok && rename(temporary, path) == 0)
                    finished_trace = trace_id;
            }
        }
        queued_frame = 0;
    }
    pthread_mutex_unlock(&lock);
}

void bces_half_depth_read(uint64_t address, uint32_t bytes, unsigned kind,
                          uint32_t actor, uint32_t pc)
{
    const uint32_t base = __atomic_load_n(&guest_address, __ATOMIC_ACQUIRE);
    if (!base || !bytes || address > UINT32_MAX ||
        address >= (uint64_t)base + BCES_HALF_DEPTH_BYTES || address + bytes <= base) return;
    // Record each intersecting request. The trace ring detects overflow.
    const uint64_t now = ps3_ft_now();
    ps3_ft_span((int)kind, actor, (uint32_t)address, pc, now, now);
}
