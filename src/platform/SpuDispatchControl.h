#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned bces_spu_dispatch_fast;
extern unsigned bces_spu_dispatch_instrument;
/* One conservative byte per256-byte LS page; positive pages retain exact checks. */
extern uint8_t bces_spu_reset_pages[1024];
typedef struct __attribute__((aligned(128))) {
    uint64_t eligible,fast,fallback,reset_checks,reset_bypasses;
    uint8_t padding[88];
} BCESDispatchCounters;
extern BCESDispatchCounters bces_spu_dispatch_counters[16];
typedef struct {unsigned enabled;uint64_t eligible,fast,fallback,reset_checks,reset_bypasses;} BCESDispatchStats;
void bces_spu_dispatch_set(unsigned enabled,unsigned instrument);
BCESDispatchStats bces_spu_dispatch_stats(void);
#ifdef __cplusplus
}
#endif
