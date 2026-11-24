#include "SpuDispatchControl.h"
unsigned bces_spu_dispatch_fast;
unsigned bces_spu_dispatch_instrument;
uint8_t bces_spu_reset_pages[1024];
BCESDispatchCounters bces_spu_dispatch_counters[16];
void bces_spu_dispatch_set(unsigned enabled,unsigned instrument){
    __atomic_store_n(&bces_spu_dispatch_instrument,!!instrument,__ATOMIC_RELEASE);
    __atomic_store_n(&bces_spu_dispatch_fast,!!enabled,__ATOMIC_RELEASE);
}
BCESDispatchStats bces_spu_dispatch_stats(void){
    BCESDispatchStats s={.enabled=__atomic_load_n(&bces_spu_dispatch_fast,__ATOMIC_ACQUIRE)};
    for(unsigned i=0;i<16;i++){
        s.eligible+=__atomic_load_n(&bces_spu_dispatch_counters[i].eligible,__ATOMIC_RELAXED);
        s.fast+=__atomic_load_n(&bces_spu_dispatch_counters[i].fast,__ATOMIC_RELAXED);
        s.fallback+=__atomic_load_n(&bces_spu_dispatch_counters[i].fallback,__ATOMIC_RELAXED);
        s.reset_checks+=__atomic_load_n(&bces_spu_dispatch_counters[i].reset_checks,__ATOMIC_RELAXED);
        s.reset_bypasses+=__atomic_load_n(&bces_spu_dispatch_counters[i].reset_bypasses,__ATOMIC_RELAXED);
    }
    return s;
}
