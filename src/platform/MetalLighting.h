#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct spu_context;
void light_skip_4578(struct spu_context* context);
int bces_metal_light_prepare(uint32_t width,uint32_t height);
uint32_t bces_gcm_io_ea(uint32_t io);
int bces_light_allow_job(void* context);
void bces_light_reference_tap(void* context,uint32_t target);
uint64_t bces_light_fault_count(void);
uint64_t bces_light_skipped_tiles(void);
uint64_t bces_light_fallback_jobs(void);
uint64_t bces_light_rendered_passes(void);
uint64_t bces_light_bindings(void);
#ifdef __cplusplus
}
#endif
