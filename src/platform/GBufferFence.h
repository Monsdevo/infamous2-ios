#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_gbuffer_fence_set(unsigned enabled);
unsigned bces_gbuffer_fence_mode(void);
uint64_t bces_gbuffer_fence_reused(void);
uint64_t bces_gbuffer_fence_rejected(void);
uint64_t bces_gbuffer_fence_validated(void);
uint64_t bces_gbuffer_fence_mismatches(void);
#ifdef __cplusplus
}
#endif
