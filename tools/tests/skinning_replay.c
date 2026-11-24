#include "SkinningSnapshot.h"
#include "SkinningReplay.h"
#include "spu_recomp.h"
#include <assert.h>
int g_spu_ls_dbg=0,g_spu_ls_watch_n=0;
void spu_ls_watch_slow(const spu_context*c,uint32_t a,int w,const uint8_t*p,uint32_t pc,uint32_t lr){(void)c;(void)a;(void)w;(void)p;(void)pc;(void)lr;}
static uint64_t count[65536],reads[65536],writes[65536],steps;
static u128* first[65536];static uint32_t current;
void skin_visit(spu_context*c,uint32_t pc){
    current=pc;count[pc]++;if(++steps>10000000){fprintf(stderr,"skin step limit\n");abort();}
    if(!first[pc]){first[pc]=malloc(sizeof c->gpr);assert(first[pc]);memcpy(first[pc],c->gpr,sizeof c->gpr);}
}
void skin_assert(spu_context*c){fprintf(stderr,"skin assertion pc=%x message=%x\n",c->pc,c->gpr[4]._u32[0]);abort();}
u128 skin_read(const spu_context*c,uint32_t address){reads[current]++;return spu_ls_read128(c,address);}
void skin_write(spu_context*c,uint32_t address,u128 value){writes[current]++;spu_ls_write128(c,address,value);}
void spu_img_restore(spu_context*c,int32_t image){c->image_id=image;}
void spu_indirect_branch(spu_context*c){skin_dispatch(c);}
void spu_drain_call(spu_context*c,uint32_t pc){
    while(c->pc!=pc){void(*fn)(spu_context*)=c->tramp_fn;c->tramp_fn=NULL;if(fn)fn(c);else skin_dispatch(c);}
}
int main(int argc,char**argv){
    assert(argc==3);FILE*f=fopen(argv[1],"rb");assert(f);SkinningSnapshot*s=malloc(sizeof *s);assert(s&&fread(s,sizeof *s,1,f)==1);fclose(f);
    assert(s->magic==0x534b494e&&s->version==1&&s->context_size==sizeof(spu_context));
    spu_context*c=malloc(sizeof *c);uint8_t*ls=malloc(SPU_LS_SIZE);assert(c&&ls);memcpy(c,&s->input,sizeof *c);c->ls=ls;memcpy(ls,s->input_ls,SPU_LS_SIZE);c->tramp_fn=NULL;
    uint32_t base=c->gpr[3]._u32[0]&SPU_LS_MASK;
    printf("input context=%x stream=%x count=%u weights=%x header=",base,c->gpr[4]._u32[0],c->gpr[5]._u32[0],c->gpr[6]._u32[0]);for(unsigned i=0;i<16;++i)printf("%02x",ls[base+i]);puts("");
    jobmod_d0d15ec83992_ea2a0_spu_func_0000D0A8(c);spu_drain_call(c,0x5980);
    int okay=!memcmp(c->gpr,s->output.gpr,sizeof c->gpr)&&!memcmp(ls,s->output_ls,SPU_LS_SIZE)&&c->pc==s->output.pc;
    if(!okay){
        for(unsigned r=0;r<128;++r)if(memcmp(&c->gpr[r],&s->output.gpr[r],16))fprintf(stderr,"GPR diff r%u got=%08x expected=%08x\n",r,c->gpr[r]._u32[0],s->output.gpr[r]._u32[0]);
        unsigned n=0;for(unsigned a=0;a<SPU_LS_SIZE;++a)if(ls[a]!=s->output_ls[a]){if(n++<10)fprintf(stderr,"LS diff %x got=%02x expected=%02x\n",a,ls[a],s->output_ls[a]);}fprintf(stderr,"LS difference bytes=%u pc=%x expected=%x\n",n,c->pc,s->output.pc);
    }
    FILE*states=fopen(argv[2],"wb");assert(states);
    for(unsigned pc=0;pc<65536;++pc)if(count[pc]){printf("block %04x count=%llu reads=%llu writes=%llu\n",pc,count[pc],reads[pc],writes[pc]);fwrite(&pc,4,1,states);fwrite(first[pc],2048,1,states);free(first[pc]);}fclose(states);
    printf("%s full logical skinning: GPR/PC/entire LS; steps=%llu\n",okay?"PASS":"FAIL",steps);free(c);free(ls);free(s);return okay?0:1;
}
