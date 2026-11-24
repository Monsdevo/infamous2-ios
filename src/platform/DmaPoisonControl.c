#include "DmaPoisonControl.h"
#include <stdlib.h>
unsigned bces_dma_skip_poison;
BCESDmaPoisonCounts bces_dma_poison_counts[16];
static unsigned forced;
void bces_dma_poison_configure(void){const char* p=getenv("SPU_POISON_DMA");forced=p&&*p&&*p!='0';bces_dma_poison_set(0);}
void bces_dma_poison_set(unsigned value){if(value<=1)__atomic_store_n(&bces_dma_skip_poison,value&&!forced&&!BCES_DMA_ORIGINAL_SCAN,__ATOMIC_RELEASE);}
unsigned bces_dma_poison_enabled(void){return __atomic_load_n(&bces_dma_skip_poison,__ATOMIC_ACQUIRE);}
unsigned bces_dma_poison_forced(void){return forced;}
void bces_dma_poison_totals(uint64_t out[4]){
 for(unsigned j=0;j<4;j++)out[j]=0;
 for(unsigned i=0;i<16;i++){
  out[0]+=__atomic_load_n(&bces_dma_poison_counts[i].scanned,__ATOMIC_RELAXED);
  out[1]+=__atomic_load_n(&bces_dma_poison_counts[i].skipped,__ATOMIC_RELAXED);
  out[2]+=__atomic_load_n(&bces_dma_poison_counts[i].bytes_scanned,__ATOMIC_RELAXED);
  out[3]+=__atomic_load_n(&bces_dma_poison_counts[i].bytes_skipped,__ATOMIC_RELAXED);
 }
}
