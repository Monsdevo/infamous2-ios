#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_light_validation_replay(const char* documents);
void bces_light_validation_configure(const char* documents, int enabled);
unsigned bces_light_validation_begin(void* context, uint32_t target);
void bces_light_validation_end(void* context, unsigned token);
unsigned bces_light_validation_completed(void);
unsigned bces_light_validation_rejected_zero_output(void);
#ifdef __cplusplus
}
#endif
