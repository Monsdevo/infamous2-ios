#pragma once
#include "GeometryBatch.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct BCESBatchCost {uint64_t input_ns,submit_ns,wait_ns,output_ns,gpu_ns,cpu_tail_ns,input_bytes,output_bytes;} BCESBatchCost;
void bces_batch_metal_prepare(void);
unsigned bces_batch_metal_state(void);
unsigned bces_batch_metal_compile_stage(void);
int bces_batch_native_math_enabled(void);
// 1 success; 0 preparing/unavailable; -1 command/contract failure; -2 busy.
int bces_batch_metal_run(const BCESBatchPlan*,const u128*,const uint8_t*,BCESBatchWrite*,u128*,BCESBatchCost*);
#ifdef __cplusplus
}
#endif
