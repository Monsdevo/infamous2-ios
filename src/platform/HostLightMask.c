#include "HostLightMask.h"
static unsigned enabled;
static uint64_t passes[2],faults,validations,mismatches,compared_tiles;
void bces_mask_set(unsigned m){__atomic_store_n(&enabled,m<=2&&!__atomic_load_n(&faults,__ATOMIC_RELAXED)?m:0,__ATOMIC_RELEASE);}
unsigned bces_mask_enabled(void){return __atomic_load_n(&enabled,__ATOMIC_ACQUIRE);}
void bces_mask_pass(int f){__atomic_fetch_add(&passes[!!f],1,__ATOMIC_RELAXED);}
void bces_mask_fault(void){__atomic_fetch_add(&faults,1,__ATOMIC_RELAXED);bces_mask_set(0);}
void bces_mask_validation(unsigned errors,unsigned count){__atomic_fetch_add(&validations,1,__ATOMIC_RELAXED);__atomic_fetch_add(&compared_tiles,count,__ATOMIC_RELAXED);if(errors){__atomic_fetch_add(&mismatches,errors,__ATOMIC_RELAXED);bces_mask_fault();}}
BCESMaskStats bces_mask_stats(void){return (BCESMaskStats){bces_mask_enabled(),__atomic_load_n(&passes[0],__ATOMIC_RELAXED),__atomic_load_n(&passes[1],__ATOMIC_RELAXED),__atomic_load_n(&faults,__ATOMIC_RELAXED),__atomic_load_n(&validations,__ATOMIC_RELAXED),__atomic_load_n(&mismatches,__ATOMIC_RELAXED),__atomic_load_n(&compared_tiles,__ATOMIC_RELAXED)};}
