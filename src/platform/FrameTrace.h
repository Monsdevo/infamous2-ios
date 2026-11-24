#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_frame_trace_configure(const char* directory);
void bces_frame_trace_poll(void);
void bces_frame_trace_register_ppu(uint32_t logical_id);
int bces_frame_trace_state(void);
#ifdef __cplusplus
}
#endif
