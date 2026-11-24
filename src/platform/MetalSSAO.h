#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int bces_metal_ssao_prepare(uint32_t fw,uint32_t fh,uint32_t hw,uint32_t hh,uint32_t bytes);
uint32_t bces_ssao_rejection(void);
void bces_ssao_flush_capture(const char* directory);
int bces_ssao_allow_job(void* context);
int bces_ssao_publish(const void* constants,uint32_t bytes,uint32_t output_offset,uint32_t state,uint32_t half_depth);
uint64_t bces_ssao_passes(void);
uint64_t bces_ssao_bindings(void);
uint64_t bces_ssao_faults(void);
uint64_t bces_ssao_fallbacks(void);
uint64_t bces_ssao_skipped_tiles(void);
#ifdef __cplusplus
}
#endif
