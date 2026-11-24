#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct BCESSSAODepthScope {void* context;uint32_t state_ea;} BCESSSAODepthScope;
void bces_ssao_depth_cleanup_set_enabled(int enabled);
int bces_ssao_depth_cleanup_enabled(void);
BCESSSAODepthScope bces_ssao_depth_enter(void* context,uint32_t state_ea);
void bces_ssao_depth_leave(BCESSSAODepthScope previous);
void bces_ssao_depth_reset_scope(void* context);
unsigned bces_ssao_depth_trace_active(const void* context);
int bces_ssao_depth_claim_guard(void* context);
uint64_t bces_ssao_depth_calls(void);
uint64_t bces_ssao_depth_boundaries(void);
void bces_ssao_depth_control_configure(const char* directory);
void bces_ssao_depth_control_poll(void);
#ifdef __cplusplus
}
#endif
