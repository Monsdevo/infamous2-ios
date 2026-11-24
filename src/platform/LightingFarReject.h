#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_light_far_set(unsigned);
unsigned bces_light_far_enabled(void);
void bces_light_far_pass(int);
void bces_light_far_fault(void);
typedef struct {unsigned enabled;uint64_t reference,fast,faults;} BCESLightFarStats;
BCESLightFarStats bces_light_far_stats(void);
#ifdef __cplusplus
}
#endif
