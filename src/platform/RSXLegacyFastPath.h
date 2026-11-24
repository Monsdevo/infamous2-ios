#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct rsx_state;
// Configure once before the title/FIFO starts. Comparison changes take effect
// on the next application launch; this does not support backend hot swapping.
void bces_rsx_legacy_configure(int enabled);
// Private GCM adapter: the original return value was not consumed here.
// Dispatch still receives the unmodified method first, exactly once.
void bces_rsx_legacy_method(struct rsx_state*,uint32_t method,uint32_t data,
                            int dispatch_active);
// Both method and publish run under cellGcm's existing exclusive FIFO lock.
// Publish once per drain: no atomic counter RMW on the per-method hot path.
void bces_rsx_legacy_publish(void);
typedef struct BCESRSXLegacyStats {
    unsigned configured,requested,enabled,debug_fallback;
    uint64_t methods,state_skipped,legacy_forwarded,sync_forwarded,draw_forwarded;
} BCESRSXLegacyStats;
BCESRSXLegacyStats bces_rsx_legacy_stats(void);
#ifdef __cplusplus
}
#endif
