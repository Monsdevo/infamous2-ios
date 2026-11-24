#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_skinning_capture_enable(int enabled);
int bces_geometry_capture_enabled(void);
unsigned bces_geometry_capture_pending_count(void);
void* bces_skinning_capture_begin(void* context);
void* bces_geometry_capture_begin(void* context,unsigned kind);
uint64_t bces_geometry_capture_count(unsigned kind);
void bces_skinning_capture_end(void* capture,void* context);
void bces_skinning_capture_flush(const char* directory);
uint64_t bces_skinning_capture_count(void);
#ifdef __cplusplus
}
#endif
