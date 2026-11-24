#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { unsigned enabled; uint64_t reference,fast,faults,pipelines; } BCESDepthOnlyStats;
int bces_depth_only_eligible(const char* shader,unsigned any_color_write,unsigned alpha_test);
void bces_depth_only_set(unsigned mode);
unsigned bces_depth_only_enabled(void);
void bces_depth_only_draw(int fast);
void bces_depth_only_pipeline(void);
void bces_depth_only_fault(void);
BCESDepthOnlyStats bces_depth_only_stats(void);
#ifdef __cplusplus
}
#endif
