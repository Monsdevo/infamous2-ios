/* Exercise production guard + BCES decoder, without running the scheduler. */
#include "MetalSSAO.h"
#include "spu_context.h"
#include "ssao_gpu.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
uint8_t* vm_base;static int ready=1;
int g_spu_ls_dbg,g_spu_ls_watch_n;
void spu_ls_watch_slow(const spu_context* c,uint32_t a,int w,const uint8_t* p,uint32_t pc,uint32_t lr){abort();}
uint32_t bces_gcm_io_ea(uint32_t io){return 0x40500000u+io;}
int bces_ssao_publish(const void* p,uint32_t n,uint32_t out,uint32_t state,uint32_t half_depth){(void)state;(void)half_depth;assert(n==320 && out==0xf800000);return ready;}
static void be(uint8_t* p,uint32_t v){p[0]=v>>24;p[1]=v>>16;p[2]=v>>8;p[3]=v;}
static void fl(uint8_t* p,float f){uint32_t b;memcpy(&b,&f,4);be(p,b);}
static void st(uint8_t* p,unsigned i,uint32_t ea,uint32_t pitch,unsigned w,unsigned h,unsigned bpp,unsigned type){
 p+=64+16*i;be(p,ea);be(p+4,pitch);p[8]=w>>8;p[9]=w;p[10]=h>>8;p[11]=h;p[14]=bpp;p[15]=4|type;
}
int main(){
 vm_base=calloc(1,0x20000);assert(vm_base);spu_context* c=calloc(1,sizeof *c);c->ls=c->ls_store;c->gpr[83]._u32[0]=0x1000;be(c->ls+0x1000,0x10000);
 uint8_t* h=vm_base+0x10000;h[9]=5;be(h+12,0x11000);
 uint32_t modules[]={SSAO_DM_DEPTH,SSAO_DM_AO,SSAO_DM_BLUR_H,SSAO_DM_BLUR_V,SSAO_DM_UPSAMPLE};
 uint8_t* p[5];for(int i=0;i<5;i++){p[i]=vm_base+0x11000+128*i;p[i][0]=p[i][1]=1;be(p[i]+12,modules[i]);be(p[i]+24,0x12000+256*i);be(p[i]+28,i==1?256:16);}
 p[0][3]=p[4][3]=1;be(p[0]+4,0x20000880);be(p[4]+4,0x20000890);be(p[0]+8,123);be(p[4]+8,123);
 const uint32_t z=0x47877b80,n=0x474f3b80,hd=0x47bfbb80,ao=0x47cdcb80;
 st(p[0],0,z,5120,1280,720,4,1);st(p[0],1,hd,2560,640,360,4,2);
 st(p[1],0,hd,2560,640,360,4,1);st(p[1],1,n,5120,1280,720,4,1);st(p[1],2,ao,640,640,360,1,2);
 for(int i=2;i<4;i++){st(p[i],0,ao,640,640,360,1,1);st(p[i],1,hd,2560,640,360,4,1);st(p[i],2,ao,640,640,360,1,2);}
 st(p[4],0,ao,640,640,360,1,1);st(p[4],1,hd,2560,640,360,4,1);st(p[4],2,z,5120,1280,720,4,1);st(p[4],3,0xcf800000,1280,1280,720,1,2);
 fl(vm_base+0x12100+0xd0,6);fl(vm_base+0x12100+0xe8,10);fl(vm_base+0x12100+0xec,1000);
 uint8_t* before=malloc(SPU_LS_SIZE);memcpy(before,c->ls,SPU_LS_SIZE);
 assert(bces_ssao_allow_job(c));ready=0;assert(!bces_ssao_allow_job(c));ready=1;
 be(p[1]+12,0x0087f880);assert(!bces_ssao_allow_job(c));be(p[1]+12,SSAO_DM_AO);
 be(p[4]+0x74,1279);assert(!bces_ssao_allow_job(c));be(p[4]+0x74,1280);
 fl(vm_base+0x12300,1);assert(!bces_ssao_allow_job(c));fl(vm_base+0x12300,0);
 be(vm_base+0x12100+0xd0,0x7fc00000);assert(!bces_ssao_allow_job(c));fl(vm_base+0x12100+0xd0,6);
 assert(bces_ssao_allow_job(c));assert(!memcmp(before,c->ls,SPU_LS_SIZE));assert(c->gpr[83]._u32[0]==0x1000);
 puts("PASS: BCES SSAO layout, readiness fallback, wrong-version module, pitch, blur mismatch, NaN and unchanged LS/registers");
 free(before);free(c);free(vm_base);
}
