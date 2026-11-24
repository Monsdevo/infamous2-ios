#include "Skinning.h"
#include "SkinningSnapshot.h"
#include "GeometryKernels.h"
#include "spu_helpers.h"
#include <stdatomic.h>
#include <stdio.h>
#include <unistd.h>
static _Atomic int enabled;
static _Atomic unsigned claimed[64];
static _Atomic uint64_t completed[2];
static _Atomic unsigned active;
static uint64_t capture_fpcr[64];
static _Atomic(SkinningSnapshot*) pending[64];
int bces_geometry_capture_enabled(void){return atomic_load(&enabled);}
unsigned bces_geometry_capture_pending_count(void){unsigned n=atomic_load(&active);for(unsigned i=0;i<64;i++)if(atomic_load_explicit(&pending[i],memory_order_acquire))n++;return n;}
static void local_state(spu_context*out,const spu_context*in){
 // Only fields used by the pure call graph: do not memcpy asynchronous
 // mailbox/reservation/stop state or duplicate the inline LS backing store.
 memcpy(out->gpr,in->gpr,sizeof out->gpr);out->pc=in->pc;out->image_id=in->image_id;out->host_depth=in->host_depth;
}
void bces_skinning_capture_enable(int value){atomic_store(&enabled,!!value);}
void* bces_geometry_capture_begin(void*opaque,unsigned kind){
 if(kind>1||!atomic_load_explicit(&enabled,memory_order_relaxed)||bces_geometry_route(kind)!=0)return NULL;
 spu_context*c=opaque;if(!c->ls||c->ls!=c->ls_store)return NULL;
 u128 h=spu_ls_read128(c,c->gpr[3]._u32[0]);
 unsigned uniform=spu_andi(spu_rotqbyi(h,3),15)._u32[0],flags=spu_rotqbyi(h,13)._u32[0];
 unsigned count=spu_andi(spu_rotqbyi(h,6),0xffff)._u32[0],size=count<32?0:count<128?1:count<512?2:3;
 unsigned mode=kind?(c->gpr[4]._u32[0]&3):(uniform&3);
 unsigned work=kind?c->gpr[4]._u32[0]!=0:!(flags&16)&&c->gpr[5]._u32[0]!=0&&uniform!=0;
 unsigned index=kind*32+work*16+mode*4+size,expected=0;
 if(!atomic_compare_exchange_strong(&claimed[index],&expected,1))return NULL;
 SkinningSnapshot*s=calloc(1,sizeof *s);if(!s){atomic_store(&claimed[index],0);return NULL;}
 s->magic=0x534b494e;s->version=kind?2:1;s->context_size=sizeof *c;s->index=index;
 atomic_fetch_add(&active,1);__asm__ volatile("mrs %0, fpcr":"=r"(capture_fpcr[index]));local_state(&s->input,c);memcpy(s->input_ls,c->ls,SPU_LS_SIZE);return s;
}
void* bces_skinning_capture_begin(void*opaque){return bces_geometry_capture_begin(opaque,0);}
void bces_skinning_capture_end(void*capture,void*opaque){
 SkinningSnapshot*s=capture;if(!s)return;spu_context*c=opaque;
 local_state(&s->output,c);memcpy(s->output_ls,c->ls,SPU_LS_SIZE);
 atomic_store_explicit(&pending[s->index],s,memory_order_release);atomic_fetch_add(&completed[s->version==2],1);atomic_fetch_sub(&active,1);
}
uint64_t bces_skinning_capture_count(void){return atomic_load(&completed[0]);}
uint64_t bces_geometry_capture_count(unsigned kind){return kind<2?atomic_load(&completed[kind]):0;}
void bces_skinning_capture_flush(const char*directory){
 for(unsigned i=0;i<64;i++){
  SkinningSnapshot*s=atomic_exchange_explicit(&pending[i],NULL,memory_order_acquire);if(!s)continue;
  char path[1200],name[80];snprintf(name,sizeof name,"geometry-%d-%s-%02u.bin",getpid(),s->version==2?"cull":"skin",i);
  snprintf(path,sizeof path,"%s/%s",directory,name);FILE*f=fopen(path,"wb");
  int okay=f&&fwrite(s,sizeof *s,1,f)==1;if(f)fclose(f);
  if(okay){snprintf(path,sizeof path,"%s/geometry-captures.csv",directory);f=fopen(path,"a");if(f){fprintf(f,"%s,%u,%u,%u,%u,%llu\n",name,s->version==2,s->index,s->input.image_id,s->input.gpr[3]._u32[0],(unsigned long long)capture_fpcr[i]);fclose(f);}}
  free(s);
 }
}
