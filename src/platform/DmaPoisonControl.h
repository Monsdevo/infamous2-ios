#pragma once
#include <stdint.h>
#ifndef BCES_DMA_ORIGINAL_SCAN
#define BCES_DMA_ORIGINAL_SCAN 0
#endif
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned bces_dma_skip_poison;
typedef struct __attribute__((aligned(128))) {uint64_t scanned,skipped,bytes_scanned,bytes_skipped;unsigned char pad[96];} BCESDmaPoisonCounts;
extern BCESDmaPoisonCounts bces_dma_poison_counts[16];
void bces_dma_poison_configure(void);
void bces_dma_poison_set(unsigned enabled);
unsigned bces_dma_poison_enabled(void);
unsigned bces_dma_poison_forced(void);
void bces_dma_poison_totals(uint64_t out[4]);
static inline int bces_dma_poison_scan(uint32_t spu,uint32_t bytes){
#if BCES_DMA_ORIGINAL_SCAN
 (void)spu;(void)bytes;return 1;
#else
 unsigned skip=__atomic_load_n(&bces_dma_skip_poison,__ATOMIC_RELAXED);
 /* Sample path coverage: avoid shared atomic traffic on every DMA PUT. */
 static _Thread_local uint32_t serial;
 if((++serial&255u)==0){
  BCESDmaPoisonCounts* s=&bces_dma_poison_counts[spu&15u];
  __atomic_fetch_add(skip?&s->skipped:&s->scanned,1,__ATOMIC_RELAXED);
  __atomic_fetch_add(skip?&s->bytes_skipped:&s->bytes_scanned,bytes,__ATOMIC_RELAXED);
 }
 return !skip;
#endif
}
#ifdef __cplusplus
}
#endif
