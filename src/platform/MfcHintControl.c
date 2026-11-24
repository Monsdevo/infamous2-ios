#include "MfcHintControl.h"
unsigned bces_mfc_hint_mode;
uint64_t bces_mfc_hint_checks,bces_mfc_hint_hits,bces_mfc_hint_mismatches;
void bces_mfc_hint_set(unsigned mode){if(mode<=2)__atomic_store_n(&bces_mfc_hint_mode,mode,__ATOMIC_RELEASE);}
unsigned bces_mfc_hint_get(void){return __atomic_load_n(&bces_mfc_hint_mode,__ATOMIC_ACQUIRE);}
void bces_mfc_hint_stats(uint64_t out[3]){
 out[0]=__atomic_load_n(&bces_mfc_hint_checks,__ATOMIC_RELAXED);
 out[1]=__atomic_load_n(&bces_mfc_hint_hits,__ATOMIC_RELAXED);
 out[2]=__atomic_load_n(&bces_mfc_hint_mismatches,__ATOMIC_RELAXED);
}
