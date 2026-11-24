/* Mac research only. A fallback after omission invalidates the experiment;
 * never continue an original SPU job with an unmaterialized normals input. */
#include "HostNormalsWriteback.h"
#include <stdlib.h>
#include <stdio.h>
static unsigned enabled,missing;
static uint64_t skipped;
void bces_host_normals_set(unsigned value){__atomic_store_n(&enabled,!!value,__ATOMIC_RELEASE);}
unsigned bces_host_normals_enabled(void){return __atomic_load_n(&enabled,__ATOMIC_ACQUIRE);}
void bces_host_normals_begin(void){__atomic_store_n(&missing,0,__ATOMIC_RELEASE);}
int bces_host_normals_skip(int eligible){
 if(!eligible || !bces_host_normals_enabled())return 0;
 __atomic_store_n(&missing,1,__ATOMIC_RELEASE);
 __atomic_add_fetch(&skipped,1,__ATOMIC_RELAXED);return 1;
}
void bces_host_normals_require(void){
 if(__atomic_load_n(&missing,__ATOMIC_ACQUIRE)){
  fputs("[host-normals] unsupported SPU fallback after omitted writeback; experiment invalid\n",stderr);
  fflush(stderr);abort();
 }
}
uint64_t bces_host_normals_skipped(void){return __atomic_load_n(&skipped,__ATOMIC_RELAXED);}
