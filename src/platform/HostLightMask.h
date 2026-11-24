#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {unsigned enabled;uint64_t reference,fast,faults,validations,mismatches,compared_tiles;} BCESMaskStats;
void bces_mask_set(unsigned);
unsigned bces_mask_enabled(void);
void bces_mask_pass(int);
void bces_mask_fault(void);
void bces_mask_validation(unsigned,unsigned);
BCESMaskStats bces_mask_stats(void);
#ifdef __cplusplus
}
#endif
