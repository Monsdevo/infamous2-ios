#include "HostIBCache.h"
unsigned bces_ib_mode;
BCESIBCounts bces_ib_counts[16];
void bces_ib_set(unsigned mode){if(mode<=2)__atomic_store_n(&bces_ib_mode,mode,__ATOMIC_RELEASE);}
void bces_ib_totals(uint64_t out[4]){
 for(unsigned j=0;j<4;j++)out[j]=0;
 for(unsigned i=0;i<16;i++){
  out[0]+=__atomic_load_n(&bces_ib_counts[i].hit,__ATOMIC_RELAXED);
  out[1]+=__atomic_load_n(&bces_ib_counts[i].miss,__ATOMIC_RELAXED);
  out[2]+=__atomic_load_n(&bces_ib_counts[i].validated,__ATOMIC_RELAXED);
  out[3]+=__atomic_load_n(&bces_ib_counts[i].fault,__ATOMIC_RELAXED);
 }
}
