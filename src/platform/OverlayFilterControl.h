#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* 0 original summary; 1 signature/page filter; 2 exact rejection oracle. */
extern unsigned bces_overlay_filter_mode;
extern unsigned bces_overlay_filter_compiled;
extern uint64_t bces_overlay_checks,bces_overlay_rejects,bces_overlay_extra_rejects,bces_overlay_mismatches;
void bces_overlay_filter_set(unsigned mode);
unsigned bces_overlay_filter_get(void);
void bces_overlay_filter_stats(uint64_t out[4]);
#ifdef __cplusplus
}
#endif
