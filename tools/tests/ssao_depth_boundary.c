#include "SSAODepthBoundary.h"
#include "spu_recomp.h"
#include "spu_helpers.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#define F(a) jobmod_e6fe749031f8_e2060_spu_func_##a
int g_spu_ls_dbg,g_spu_ls_watch_n;
void spu_ls_watch_slow(const spu_context* c,uint32_t a,int w,const uint8_t* p,uint32_t pc,uint32_t lr){abort();}
static uint8_t shared[128];static uint32_t state_ea,version,reservation,lsa,eal,cmd_status;static unsigned writes,atomic_reads,race;
static void be16(uint8_t* p,unsigned v){p[0]=v>>8;p[1]=v;}
static void be32(uint8_t* p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static unsigned half(unsigned off){return (unsigned)shared[(state_ea&127)+off]<<8|shared[(state_ea&127)+off+1];}
void spu_img_restore(spu_context* c,int32_t image){c->image_id=image;}
void spu_drain_call(spu_context* c,uint32_t ret){
 unsigned steps=0;while(c->tramp_fn){if(c->pc==ret){c->tramp_fn=0;break;}assert(++steps<10000);void(*f)(spu_context*)=c->tramp_fn;c->tramp_fn=0;f(c);}assert(c->pc==ret);
}
void spu_indirect_branch(spu_context* c){
 switch(c->pc){case 0x4a70:F(00004A70)(c);break;case 0x4bd0:F(00004BD0)(c);break;case 0x4be8:F(00004BE8)(c);break;default:fprintf(stderr,"unexpected branch %x\n",c->pc);abort();}
}
void spu_halt(spu_context* c){abort();}void spu_stop(spu_context* c){abort();}
u128 spu_rdch(spu_context* c,uint32_t ch){
 if(ch==SPU_RdMachStat)return spu_splat_u32(c->int_enable);
 assert(ch==MFC_RdAtomicStat);return spu_splat_u32(cmd_status);
}
void spu_wrch(spu_context* c,uint32_t ch,u128 v){
 uint32_t x=v._u32[0];switch(ch){
 case MFC_LSA:lsa=x;return;case MFC_EAL:eal=x;return;case MFC_EAH:assert(!x);return;case MFC_Size:assert(x==128);return;case MFC_TagID:assert(!x);return;
 case MFC_Cmd:
  assert(eal==(state_ea&~127u) && lsa==0x6480);
  if(x==0xd0){atomic_reads++;memcpy(c->ls+lsa,shared,128);reservation=version;cmd_status=0;return;}
  assert(x==0xb4);
  if(race){race=0;be16(shared+(state_ea&127),1);version++;}
  if(reservation!=version){cmd_status=1;return;}
  memcpy(shared,c->ls+lsa,128);version++;writes++;cmd_status=0;return;
 default:fprintf(stderr,"unexpected channel %u\n",ch);abort();
 }
}
static void init(spu_context* c,unsigned pass,unsigned taken,unsigned total,unsigned irq,unsigned offset){
 memset(c,0,sizeof *c);c->ls=c->ls_store;c->gpr[1]=spu_splat_u32(0x3d000);c->gpr[0]=spu_link(0x3fffc);c->int_enable=irq;c->host_depth=1;
 state_ea=0x10000+offset;memset(shared,0,sizeof shared);be16(shared+offset,pass);be16(shared+offset+2,taken);be16(shared+offset+4,0);be16(shared+offset+6,total);
 be32(c->ls+0x6420,state_ea);spu_ls_write128(c,0x6260,spu_splat_u32(0xffffff80u));
 version=1;writes=atomic_reads=race=0;
}
static unsigned run(spu_context* c,int on,int scoped){
 bces_ssao_depth_cleanup_set_enabled(on);BCESSSAODepthScope previous={0};if(scoped)previous=bces_ssao_depth_enter(c,state_ea);
 F(00004A50)(c);spu_drain_call(c,0x3fffc);if(scoped)bces_ssao_depth_leave(previous);
 assert(c->gpr[1]._u32[0]==0x3d000);return c->gpr[3]._u32[0]&65535;
}
static void* isolated(void* opaque){spu_context* c=opaque;assert(!bces_ssao_depth_claim_guard(c));return 0;}
int main(){
 spu_context* c=calloc(1,sizeof *c),*gold=malloc(sizeof *c);assert(c && gold);unsigned cases=0;
 for(unsigned offset=0;offset<=120;offset+=8)for(unsigned irq=0;irq<2;irq++){
  // Depth success, depth barrier and terminal: full context matches disabled path.
  for(unsigned kind=0;kind<3;kind++){
   unsigned pass=kind==2?65535:0,taken=kind==1?2:0;
   init(c,pass,taken,2,irq,offset);unsigned expected=run(c,0,1);memcpy(gold,c,sizeof *c);uint8_t mem[128];memcpy(mem,shared,128);
   init(c,pass,taken,2,irq,offset);assert(run(c,1,1)==expected);assert(!memcmp(c,gold,sizeof *c));assert(!memcmp(mem,shared,128));cases++;
  }
  for(unsigned pass=1;pass<=4;pass++){
   init(c,pass,0,2,irq,offset);uint8_t mem[128];memcpy(mem,shared,128);assert(run(c,1,1)==65534);assert(!writes && atomic_reads==1);assert(!memcmp(mem,shared,128));assert(c->int_enable==irq);cases++;
   // Full original fallback has no depth scope and still claims the same tile.
   init(c,pass,0,2,irq,offset);unsigned expected=run(c,0,0);memcpy(gold,c,sizeof *c);memcpy(mem,shared,128);
   init(c,pass,0,2,irq,offset);assert(run(c,1,0)==expected);assert(!memcmp(c,gold,sizeof *c));assert(!memcmp(mem,shared,128));cases++;
  }
  // Last depth pass advances after GETLLAR: old reservation must fail, then guard retries.
  init(c,0,0,2,irq,offset);race=1;assert(run(c,1,1)==65534);assert(atomic_reads==2 && !writes && half(0)==1 && half(2)==0);cases++;
  init(c,0,0,2,irq,offset);race=1;assert(run(c,0,1)==0);assert(atomic_reads==2 && writes==1 && half(2)==1);cases++;
 }
 // Scope nesting, thread isolation, state binding and stale-scope reset.
 init(c,1,0,2,0,0);memcpy(c->ls+0x6480,shared,128);bces_ssao_depth_cleanup_set_enabled(1);
 BCESSSAODepthScope previous=bces_ssao_depth_enter(c,state_ea);assert(bces_ssao_depth_claim_guard(c));
 pthread_t t;assert(!pthread_create(&t,0,isolated,c));assert(!pthread_join(t,0));
 BCESSSAODepthScope nested=bces_ssao_depth_enter(gold,state_ea);assert(!bces_ssao_depth_claim_guard(c));bces_ssao_depth_leave(nested);assert(bces_ssao_depth_claim_guard(c));
 be32(c->ls+0x6420,state_ea+8);assert(!bces_ssao_depth_claim_guard(c));be32(c->ls+0x6420,state_ea);
 bces_ssao_depth_reset_scope(c);assert(!bces_ssao_depth_claim_guard(c));bces_ssao_depth_leave(previous);
 char directory[]="/tmp/ssao-depth-control-XXXXXX";assert(mkdtemp(directory));
 char path[256];snprintf(path,sizeof path,"%s/ssao-depth-control.txt",directory);
 bces_ssao_depth_control_configure(directory);FILE* f=fopen(path,"w");assert(f);fputs("off comparison_a\n",f);fclose(f);
 bces_ssao_depth_control_poll();assert(!bces_ssao_depth_cleanup_enabled());
 bces_ssao_depth_cleanup_set_enabled(1);bces_ssao_depth_control_poll();assert(bces_ssao_depth_cleanup_enabled()); // token replay ignored
 f=fopen(path,"w");assert(f);fputs("off comparison_b\n",f);fclose(f);bces_ssao_depth_control_poll();assert(!bces_ssao_depth_cleanup_enabled());
 f=fopen(path,"w");assert(f);fputs("on comparison_c\n",f);fclose(f);bces_ssao_depth_control_poll();assert(bces_ssao_depth_cleanup_enabled());
 remove(path);rmdir(directory);
 printf("PASS: %u lifted atomic-claim cases; IRQ/stack restoration; deterministic pass-advance race; unchanged depth/terminal/fallback; TLS isolation\n",cases);
 free(c);free(gold);return 0;
}
