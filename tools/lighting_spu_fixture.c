/* Standalone arithmetic replay of a captured tile, not the game's scheduler.
 * Any DMA, stop or unresolved indirect branch is a hard error. */
#include "spu_context.h"
#include "spu_helpers.h"
#include <assert.h>
void jobmod_c6e7383dc013_e5400_spu_func_00004AC8(spu_context*);
int g_spu_ls_dbg=0,g_spu_ls_watch_n=0;
void spu_ls_watch_slow(const spu_context* c,uint32_t a,int w,const uint8_t* p,uint32_t pc,uint32_t lr){abort();}
void spu_img_restore(spu_context* c,int32_t image){c->image_id=image;}
void spu_drain_call(spu_context* c,uint32_t ret) {
 unsigned n=0;
 while(c->tramp_fn) {
  if(c->pc==ret){c->tramp_fn=0;break;}
  assert(++n<1000000);void (*f)(spu_context*)=c->tramp_fn;c->tramp_fn=0;f(c);
 }
 assert(c->pc==ret);
}
void spu_indirect_branch(spu_context* c){fprintf(stderr,"unexpected indirect pc=%x\n",(unsigned)c->pc);abort();}
void spu_stop(spu_context* c){abort();}
void spu_halt(spu_context* c){abort();}
u128 spu_rdch(spu_context* c,uint32_t ch){abort();}
void spu_wrch(spu_context* c,uint32_t ch,u128 v){abort();}
void spu_register_function(uint32_t a,void(*f)(spu_context*)){abort();}
static void load(const char* p,void* b,size_t n){FILE* f=fopen(p,"rb");assert(f);assert(fread(b,1,n,f)==n);assert(fgetc(f)==EOF);fclose(f);}
int main(int argc,char** argv) {
 if(argc!=4)return 2;
 spu_context* c=calloc(1,sizeof *c);assert(c);c->ls=c->ls_store;
 load(argv[1],c->ls,SPU_LS_SIZE);load(argv[2],c->gpr,sizeof c->gpr);
 c->gpr[0]=spu_link(0x3fffc);c->host_depth=1;c->pc=0x4ac8;
 jobmod_c6e7383dc013_e5400_spu_func_00004AC8(c);spu_drain_call(c,0x3fffc);
 FILE* f=fopen(argv[3],"wb");assert(f);assert(fwrite(c->ls,1,SPU_LS_SIZE,f)==SPU_LS_SIZE);assert(!fclose(f));free(c);
}
