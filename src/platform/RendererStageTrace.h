#pragma once

#include "ps3emu/ps3_ftrace.h"
#include <pthread.h>
#include <time.h>

typedef struct {
    uint64_t epoch, start, cpu, thread;
    uint32_t stage, detail;
} BCESRendererSpan;

static inline uint64_t bces_renderer_cpu_ns(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != 0) return UINT64_MAX;
    return (uint64_t)value.tv_sec * 1000000000ull + value.tv_nsec;
}

static inline BCESRendererSpan bces_renderer_stage_begin(uint32_t stage, uint32_t detail) {
    BCESRendererSpan span = {0};
    if (!PS3_FT_ON()) return span;
    span.start = ps3_ft_now();
    if (span.start > g_ps3_ft.end) return (BCESRendererSpan){0};
    span.epoch = g_ps3_ft.start;
    span.cpu = bces_renderer_cpu_ns();
    pthread_threadid_np(NULL, &span.thread);
    span.stage = stage;
    span.detail = detail;
    return span;
}

static inline void bces_renderer_stage_end(BCESRendererSpan* span) {
    if (!span->start || !PS3_FT_ON() || span->epoch != g_ps3_ft.start) return;
    const uint64_t cpu = bces_renderer_cpu_ns();
    const uint64_t end = ps3_ft_now();
    if (span->cpu == UINT64_MAX || cpu == UINT64_MAX || cpu < span->cpu) return;
    const uint64_t delta = cpu - span->cpu;
    // The two records are keyed by the thread and the exact span.
    ps3_ft_span(450, (uint32_t)span->thread, span->stage, span->detail, span->start, end);
    ps3_ft_span(451, (uint32_t)span->thread, (uint32_t)delta, (uint32_t)(delta >> 32), span->start, end);
}

#define BCES_RENDERER_STAGE(name, stage, detail) \
    BCESRendererSpan name __attribute__((cleanup(bces_renderer_stage_end))) = bces_renderer_stage_begin(stage, detail)
