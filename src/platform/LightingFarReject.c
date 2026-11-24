#include "LightingFarReject.h"
static unsigned enabled;
static uint64_t passes[2],faults;
void bces_light_far_set(unsigned mode){__atomic_store_n(&enabled,!!mode,__ATOMIC_RELEASE);}
unsigned bces_light_far_enabled(void){return __atomic_load_n(&enabled,__ATOMIC_ACQUIRE);}
void bces_light_far_pass(int fast){__atomic_fetch_add(&passes[!!fast],1,__ATOMIC_RELAXED);}
void bces_light_far_fault(void){__atomic_fetch_add(&faults,1,__ATOMIC_RELAXED);bces_light_far_set(0);}
BCESLightFarStats bces_light_far_stats(void){return (BCESLightFarStats){bces_light_far_enabled(),__atomic_load_n(&passes[0],__ATOMIC_RELAXED),__atomic_load_n(&passes[1],__ATOMIC_RELAXED),__atomic_load_n(&faults,__ATOMIC_RELAXED)};}
