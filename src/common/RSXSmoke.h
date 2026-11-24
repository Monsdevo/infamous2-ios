#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Synthetic NV4097 clear/present fixture. No PPU, SPU or game is booted.
int rsx_smoke_init(void);
uint32_t rsx_smoke_present(uint32_t argb, int readback);
typedef struct { uint32_t pixel, translated_draws; } RSXShaderSample;
int rsx_smoke_shader_available(void);
RSXShaderSample rsx_smoke_present_shader(uint32_t vertex_argb, int readback);
void rsx_smoke_shutdown(void);
#ifdef __cplusplus
}
#endif
