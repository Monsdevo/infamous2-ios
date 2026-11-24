#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned bces_ib_mode;
typedef struct __attribute__((aligned(128))) {uint64_t hit,miss,validated,fault;unsigned char pad[96];} BCESIBCounts;
extern BCESIBCounts bces_ib_counts[16];
void bces_ib_set(unsigned mode);
void bces_ib_totals(uint64_t out[4]);
#ifdef __cplusplus
}
#endif
