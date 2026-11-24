#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* enabled, sizeof slot, alignment, base mod128, stride, engine offset,
 * table bytes, engine bytes. This reports a compile-time layout, not a switch. */
void bces_mfc_layout(uint64_t out[8]);
#ifdef __cplusplus
}
#endif
