#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* 0: original lookup, 1: hint, 2: hint + original oracle (diagnosis only). */
extern unsigned bces_mfc_hint_mode;
extern uint64_t bces_mfc_hint_checks,bces_mfc_hint_hits,bces_mfc_hint_mismatches;
void bces_mfc_hint_set(unsigned mode);
unsigned bces_mfc_hint_get(void);
void bces_mfc_hint_stats(uint64_t out[3]);
#ifdef __cplusplus
}
#endif
