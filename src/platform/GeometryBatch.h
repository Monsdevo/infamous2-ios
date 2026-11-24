#pragma once
#include "GeometryExecution.h"
#define BCES_BATCH_MAX_ITERATIONS 2048
#define BCES_BATCH_MAX_WRITES 12
#define BCES_BATCH_LS_QUADS 16384
typedef struct BCESBatchWrite {uint32_t address,pad[3];u128 value;} BCESBatchWrite;
typedef struct BCESBatchPlan {
    uint32_t pc,iterations,writes_per_iteration;
    uint32_t rejection,address,read_stamp,write_stamp;
    uint64_t read_pages;
    uint32_t read_max[BCES_BATCH_LS_QUADS],write_first[BCES_BATCH_LS_QUADS];
    uint32_t addresses[BCES_BATCH_MAX_ITERATIONS*BCES_BATCH_MAX_WRITES];
    uint32_t hashes[BCES_BATCH_MAX_ITERATIONS];
    u128 cull_states[BCES_BATCH_MAX_ITERATIONS*3];
} BCESBatchPlan;
#ifdef __cplusplus
extern "C" {
#endif
unsigned bces_batch_count(uint32_t pc,const u128*r);
int bces_batch_plan(uint32_t pc,const u128*r,const uint8_t*ls,BCESBatchPlan*plan);
uint32_t bces_batch_finish(uint32_t pc,u128*r,const uint8_t*ls);
int bces_batch_tail(const BCESBatchPlan*,const u128*,const uint8_t*,u128*);
int bces_batch_cpu(uint32_t pc,u128*r,uint8_t*ls,uint32_t*next,BCESGeometryExecution*execution);
#ifdef __cplusplus
}
#endif
