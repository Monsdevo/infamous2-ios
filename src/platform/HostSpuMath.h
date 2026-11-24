#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {unsigned mode;uint64_t reference,fast,validated,mismatches,fallback;uint64_t seen;} BCESHostSpuMathStats;
void bces_host_math_set(unsigned mode);
unsigned bces_host_math_mode(void);
// tag = counter kind | ((SPU id & 15) << 8).
void bces_host_math_note(unsigned tag);
void bces_host_math_result(unsigned block,int equal);
BCESHostSpuMathStats bces_host_math_stats(void);
#ifdef __cplusplus
}
#endif
