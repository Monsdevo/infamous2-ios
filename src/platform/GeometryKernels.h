#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct spu_context;
typedef void (*BCESGeometryReference)(struct spu_context*);
// kind: 0 skinning, 1 culling. route: 0 original SPU, 1 static ARM64, 2 Metal.
void bces_geometry_set_route(unsigned kind,unsigned route);
unsigned bces_geometry_route(unsigned kind);
void bces_geometry_set_routes(unsigned skin,unsigned cull);
unsigned bces_geometry_revision(void);
int bces_geometry_validation_enabled(void);
void bces_geometry_set_validation(int enabled);
// 0 idle, 1 compiling asynchronously, 2 ready, 3 unavailable.
unsigned bces_geometry_metal_state(void);
void bces_geometry_execute(struct spu_context*,unsigned kind,BCESGeometryReference,uint32_t return_pc);
typedef struct BCESGeometryStats {
    unsigned requested_route,blocked_mask;
    uint64_t calls[3],fallbacks,validations,mismatches,failures,trial_ns,gpu_ns,reference_ns;
    uint64_t entries[3],total_ns[3];
    uint64_t sampled_calls,copy_ns,execute_ns,commit_ns;
    uint64_t batch_candidates,gpu_batches,calibration_batches,cpu_small_batches,cpu_busy_batches,cpu_dependency_batches,cpu_cost_rejected_batches,cpu_only_calls;
    uint64_t input_ns,submit_ns,wait_ns,output_ns,input_bytes,output_bytes;
    unsigned admitted_mask,rejected_mask,calibrating;
    uint64_t unsupported_calls;
} BCESGeometryStats;
BCESGeometryStats bces_geometry_stats(unsigned kind);
typedef struct BCESGeometryGateStats {unsigned pc,bucket,state,samples;uint64_t cpu_ns,gpu_ns;} BCESGeometryGateStats;
BCESGeometryGateStats bces_geometry_gate_stats(unsigned kind,unsigned index);
#ifdef __cplusplus
}
#endif
