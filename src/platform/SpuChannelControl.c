#include "SpuChannelControl.h"
#include <stdlib.h>
unsigned bces_channel_mode,bces_channel_compiled;
static unsigned forced;
static uint64_t counts[11];
void bces_channel_configure(void){forced=getenv("SPU_CHHIST")||getenv("SPU_POLLTRACE")||getenv("SPU_TAGPROBE");bces_channel_set(0);}
void bces_channel_set(unsigned mode){if(mode<=2 && (!mode||bces_channel_compiled))__atomic_store_n(&bces_channel_mode,forced?0:mode,__ATOMIC_RELEASE);}
unsigned bces_channel_get(void){return __atomic_load_n(&bces_channel_mode,__ATOMIC_ACQUIRE);}
unsigned bces_channel_forced(void){return forced;}
void bces_channel_record(unsigned channel,int checked,int mismatch){
 if(channel<9)__atomic_fetch_add(&counts[channel],1,__ATOMIC_RELAXED);
 if(checked)__atomic_fetch_add(&counts[9],1,__ATOMIC_RELAXED);
 if(mismatch){__atomic_fetch_add(&counts[10],1,__ATOMIC_RELAXED);bces_channel_set(0);}
}
void bces_channel_stats(uint64_t out[11]){for(unsigned i=0;i<11;i++)out[i]=__atomic_load_n(&counts[i],__ATOMIC_RELAXED);}
