#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { BCES_HALF_DEPTH_BYTES = 640 * 360 * 4 };
void bces_half_depth_configure(const char* directory);
void bces_half_depth_admit(uint32_t frame, uint32_t state, uint32_t address);
void bces_half_depth_reference(uint32_t state);
void bces_half_depth_select(uint32_t frame);
uint32_t bces_half_depth_claim(void);
void bces_half_depth_complete(uint32_t frame, const void* pixels);
void bces_half_depth_read(uint64_t address, uint32_t bytes, unsigned kind,
                          uint32_t actor, uint32_t pc);
#ifdef __cplusplus
}
#endif
