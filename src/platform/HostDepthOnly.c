#include "HostDepthOnly.h"
#include <ctype.h>
#include <stddef.h>
static unsigned enabled;
static uint64_t reference,fast,faults,pipelines;
static int contains(const char* s,const char* needle){
 for(;*s;s++){size_t i=0;while(needle[i]&&s[i]&&tolower((unsigned char)s[i])==needle[i])i++;if(!needle[i])return 1;}
 return 0;
}
int bces_depth_only_eligible(const char* s,unsigned color,unsigned alpha){
 if(!s||color||alpha)return 0;
 /* Generated RSX shaders can affect rasterization through discard/depth/
  * coverage, but have no CPU-visible effects. Fail closed for any such
  * syntax (including unused helper definitions) or storage/atomic syntax. */
 const char* banned[]={"clip","discard","sv_depth","sv_coverage","rwtexture","rwbuffer","rwstructuredbuffer","interlocked","globallycoherent","rasterizerordered"};
 for(unsigned i=0;i<sizeof(banned)/sizeof(*banned);i++)if(contains(s,banned[i]))return 0;
 return contains(s,"sv_target");
}
void bces_depth_only_set(unsigned m){__atomic_store_n(&enabled,!!m,__ATOMIC_RELEASE);}
unsigned bces_depth_only_enabled(void){return __atomic_load_n(&enabled,__ATOMIC_ACQUIRE);}
void bces_depth_only_draw(int f){__atomic_fetch_add(f?&fast:&reference,1,__ATOMIC_RELAXED);}
void bces_depth_only_pipeline(void){__atomic_fetch_add(&pipelines,1,__ATOMIC_RELAXED);}
void bces_depth_only_fault(void){__atomic_fetch_add(&faults,1,__ATOMIC_RELAXED);bces_depth_only_set(0);}
BCESDepthOnlyStats bces_depth_only_stats(void){return (BCESDepthOnlyStats){bces_depth_only_enabled(),__atomic_load_n(&reference,__ATOMIC_RELAXED),__atomic_load_n(&fast,__ATOMIC_RELAXED),__atomic_load_n(&faults,__ATOMIC_RELAXED),__atomic_load_n(&pipelines,__ATOMIC_RELAXED)};}
