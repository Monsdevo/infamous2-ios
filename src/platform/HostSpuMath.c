#include "HostSpuMath.h"
// Six SPU workers must not contend on one instrumentation cache line at every
// pure block. Low byte selects the counter, next four bits select the SPU slot.
// Atomics retain correct totals even if two logical contexts share a slot.
typedef struct __attribute__((aligned(128))) {uint64_t counts[5],seen;} Bucket;
_Static_assert(sizeof(Bucket)==128,"one independently aligned counter bucket");
static Bucket buckets[16];
static unsigned mode;
static uint64_t faults;
unsigned bces_host_math_mode(void){return __atomic_load_n(&faults,__ATOMIC_RELAXED)?0:__atomic_load_n(&mode,__ATOMIC_ACQUIRE);}
void bces_host_math_set(unsigned m){__atomic_store_n(&mode,m<=2&&!__atomic_load_n(&faults,__ATOMIC_RELAXED)?m:0,__ATOMIC_RELEASE);}
void bces_host_math_note(unsigned tag){unsigned k=tag&255u;if(k<5)__atomic_fetch_add(&buckets[(tag>>8)&15u].counts[k],1,__ATOMIC_RELAXED);}
void bces_host_math_result(unsigned block,int equal){
 bces_host_math_note(2);
 if(equal&&block<64)__atomic_fetch_or(&buckets[0].seen,1ull<<block,__ATOMIC_RELAXED);
 else{bces_host_math_note(3);__atomic_fetch_add(&faults,1,__ATOMIC_RELEASE);bces_host_math_set(0);}
}
BCESHostSpuMathStats bces_host_math_stats(void){
 BCESHostSpuMathStats s={.mode=bces_host_math_mode()};
 for(unsigned i=0;i<16;i++){
  s.reference+=__atomic_load_n(&buckets[i].counts[0],__ATOMIC_RELAXED);
  s.fast+=__atomic_load_n(&buckets[i].counts[1],__ATOMIC_RELAXED);
  s.validated+=__atomic_load_n(&buckets[i].counts[2],__ATOMIC_RELAXED);
  s.mismatches+=__atomic_load_n(&buckets[i].counts[3],__ATOMIC_RELAXED);
  s.fallback+=__atomic_load_n(&buckets[i].counts[4],__ATOMIC_RELAXED);
  s.seen|=__atomic_load_n(&buckets[i].seen,__ATOMIC_RELAXED);
 }
 return s;
}
