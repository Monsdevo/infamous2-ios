#include "OverlayFilterControl.h"
unsigned bces_overlay_filter_mode;
unsigned bces_overlay_filter_compiled;
uint64_t bces_overlay_checks,bces_overlay_rejects,bces_overlay_extra_rejects,bces_overlay_mismatches;
void bces_overlay_filter_set(unsigned mode){if(mode<=2 && (!mode||bces_overlay_filter_compiled))__atomic_store_n(&bces_overlay_filter_mode,mode,__ATOMIC_RELEASE);}
unsigned bces_overlay_filter_get(void){return __atomic_load_n(&bces_overlay_filter_mode,__ATOMIC_ACQUIRE);}
void bces_overlay_filter_stats(uint64_t out[4]){
 out[0]=__atomic_load_n(&bces_overlay_checks,__ATOMIC_RELAXED);
 out[1]=__atomic_load_n(&bces_overlay_rejects,__ATOMIC_RELAXED);
 out[2]=__atomic_load_n(&bces_overlay_extra_rejects,__ATOMIC_RELAXED);
 out[3]=__atomic_load_n(&bces_overlay_mismatches,__ATOMIC_RELAXED);
}
