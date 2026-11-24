#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned bces_critical_job_enabled;
typedef struct {
    uint64_t epoch, start, cpu, native, context;
    uint32_t id, target, return_pc, depth, spu, r3, r4, weight, ovl, image, task;
} BCESCriticalSpan;
void bces_critical_job_enable(int enabled);
BCESCriticalSpan bces_critical_begin(void* context, uint32_t target, uint32_t return_pc);
void bces_critical_end(BCESCriticalSpan span, void* context);
void bces_critical_logical_begin(void* context, uint32_t entry);
void bces_critical_logical_end(void* context);
#ifdef __cplusplus
}
#endif
