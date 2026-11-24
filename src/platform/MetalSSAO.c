/* BCES-only, side-effect-free eligibility before the walk replacement.
 * Input copies and original SPU depth pass remain enabled. */
#include "MetalSSAO.h"
#include "MetalLighting.h"
#include "spu_context.h"
#include "spu_helpers.h"
#include "ssao_gpu.h"
#include <math.h>
#include <stddef.h>
#include <stdio.h>
extern uint8_t* vm_base;
static uint64_t fallbacks;
static uint32_t last_rejection,capture_state;
static uint8_t captured[16+640+5*256];
uint32_t bces_ssao_rejection(void){return __atomic_load_n(&last_rejection,__ATOMIC_RELAXED);}
void bces_ssao_flush_capture(const char* directory){
 if(__atomic_load_n(&capture_state,__ATOMIC_ACQUIRE)!=2)return;
 char path[1200];snprintf(path,sizeof path,"%s/ssao-pass-capture.bin",directory);
 FILE* f=fopen(path,"wb");if(!f)return;size_t n=fwrite(captured,1,sizeof captured,f);int e=fclose(f);
 if(n==sizeof captured && !e)__atomic_store_n(&capture_state,3,__ATOMIC_RELEASE);
}
uint64_t bces_ssao_fallbacks(void){return __atomic_load_n(&fallbacks,__ATOMIC_RELAXED);}
static uint32_t be32(const uint8_t* p){return (uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];}
static uint32_t be16(const uint8_t* p){return (uint32_t)p[0]<<8|p[1];}
static const uint8_t* guest(uint32_t ea,uint32_t size,void* unused){
 (void)unused;if(!vm_base || ea<0x10000u || !size || (uint64_t)ea+size>0x10000000ull)return 0;
 return vm_base+ea;
}
static int stream(const uint8_t* p,unsigned index,uint32_t ea,uint32_t pitch,unsigned w,unsigned h,unsigned bpp,unsigned type){
 const uint8_t* s=p+0x40+16*index;
 return be32(s)==ea && be32(s+4)==pitch && be16(s+8)*p[0]==w && be16(s+10)*p[1]==h && s[14]==bpp && (s[15]&3)==type;
}
int bces_ssao_allow_job(void* opaque){
 const spu_context* c=opaque;uint32_t reason=1;
 uint32_t q=c->gpr[83]._u32[0];
 if(q>0x3fff0u)goto fallback;
 u128 v=spu_rotqby(spu_ls_read128(c,q),c->gpr[83]);
 const uint8_t* h=guest(v._u32[0],16,0);if(!h || be16(h+8)!=5)goto fallback;
 uint32_t table=be32(h+12);const uint8_t* base=guest(table,5*128,0);if(!base)goto fallback;
 const uint32_t modules[5]={SSAO_DM_DEPTH,SSAO_DM_AO,SSAO_DM_BLUR_H,SSAO_DM_BLUR_V,SSAO_DM_UPSAMPLE};
 const uint8_t* pass[5];
 for(unsigned i=0;i<5;i++){
  pass[i]=base+128*i;if(!pass[i][0] || !pass[i][1] || be32(pass[i]+12)!=modules[i])goto fallback;
  uint32_t bytes=be32(pass[i]+28);if(bytes!=(i==1?256:16) || !guest(be32(pass[i]+24),bytes,0))goto fallback;
 }
 uint32_t expected=0;
 if(__atomic_compare_exchange_n(&capture_state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
  memcpy(captured,h,16);memcpy(captured+16,base,640);
  for(unsigned i=0;i<5;i++)memcpy(captured+656+256*i,guest(be32(pass[i]+24),be32(pass[i]+28),0),be32(pass[i]+28));
  __atomic_store_n(&capture_state,2,__ATOMIC_RELEASE);
 }
 reason=2;SsaoGpuConsts p;SsaoJobInfo info;
 if(ssao_consts_from_passes(pass,5,0,guest,0,&p,&info))goto fallback;
 reason=3;
 if(p.dims[0]!=1280 || p.dims[1]!=720 || p.dims[2]!=640 || p.dims[3]!=360 ||
    info.depth_ea!=bces_gcm_io_ea(0x07377b80u) || info.normals_ea!=bces_gcm_io_ea(0x06ff3b80u) ||
    info.out_ea<0xc0000000u || info.out_ea>0xcff00000u || info.out_pitch!=1280 ||
    info.label_ea[0]!=0x20000880u || info.label_ea[1]!=0x20000890u || info.label_value[0]!=info.label_value[1])goto fallback;
 reason=4;
 if(info.half_depth_ea<0x40000000u || (uint64_t)info.half_depth_ea+640*360*4>0x50000000ull ||
    info.half_ao_ea<0x40000000u || (uint64_t)info.half_ao_ea+640*360>0x50000000ull)goto fallback;
 // Every stream must describe the exact shared pipeline, including formats.
 reason=5;
 if(!stream(pass[0],0,info.depth_ea,5120,1280,720,4,1) || !stream(pass[0],1,info.half_depth_ea,2560,640,360,4,2) ||
    !stream(pass[1],0,info.half_depth_ea,2560,640,360,4,1) || !stream(pass[1],1,info.normals_ea,5120,1280,720,4,1) ||
    !stream(pass[1],2,info.half_ao_ea,640,640,360,1,2) ||
    !stream(pass[4],0,info.half_ao_ea,640,640,360,1,1) || !stream(pass[4],1,info.half_depth_ea,2560,640,360,4,1) ||
    !stream(pass[4],2,info.depth_ea,5120,1280,720,4,1) || !stream(pass[4],3,info.out_ea,1280,1280,720,1,2))goto fallback;
 reason=6;
 for(unsigned i=2;i<4;i++){
  if(!stream(pass[i],0,info.half_ao_ea,640,640,360,1,1) || !stream(pass[i],1,info.half_depth_ea,2560,640,360,4,1) ||
     !stream(pass[i],2,info.half_ao_ea,640,640,360,1,2))goto fallback;
 }
 // A single GPU blur parameter block represents both directions.
 reason=7;
 const uint8_t* hp=guest(be32(pass[2]+24),16,0),*vp=guest(be32(pass[3]+24),16,0);
 if(memcmp(hp,vp,12))goto fallback;
 const float* f=(const float*)&p;for(unsigned i=0;i<offsetof(SsaoGpuConsts,dims)/4;i++)if(!isfinite(f[i]))goto fallback;
 if(!(p.D0[0]>0 && p.E0[2]>0 && p.E0[3]>=p.E0[2]))goto fallback;
 reason=8;
 if(bces_ssao_publish(&p,sizeof p,info.out_ea-0xc0000000u,v._u32[0],info.half_depth_ea))return 1;
fallback:
 __atomic_store_n(&last_rejection,reason,__ATOMIC_RELAXED);
 __atomic_add_fetch(&fallbacks,1,__ATOMIC_RELAXED);return 0;
}
