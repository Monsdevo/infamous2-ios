#pragma once
#include "spu_helpers.h"
#include <string.h>
#include "SpuChannelControl.h"
void spu_wrch(spu_context*,uint32_t,u128);
u128 spu_rdch(spu_context*,uint32_t);
/* Included after generated declarations in lifted SPU units. Runtime implementations
 * keep their public names and are never compiled through these macros. */
void bces_channel_mfc_cmd(spu_context*,uint32_t);
void bces_channel_tag_update(spu_context*,uint32_t);
__attribute__((constructor)) static void bces_channel_inline_available(void){bces_channel_compiled=1;}
static inline __attribute__((always_inline)) void bces_channel_wrch_inline(spu_context*ctx,uint32_t ch,u128 v){
 if(__builtin_constant_p(ch) && (ch==MFC_LSA||ch==MFC_EAH||ch==MFC_EAL||ch==MFC_Size||ch==MFC_TagID||ch==MFC_WrTagMask||ch==MFC_Cmd||ch==MFC_WrTagUpdate)){
  unsigned mode=__atomic_load_n(&bces_channel_mode,__ATOMIC_RELAXED);
  if(mode){
   uint32_t x=v._u32[0];unsigned index=0;uint32_t*field=0;
   if(ch==MFC_LSA){field=&ctx->mfc_lsa;index=0;}
   else if(ch==MFC_EAH){field=&ctx->mfc_eah;index=1;}
   else if(ch==MFC_EAL){field=&ctx->mfc_eal;index=2;}
   else if(ch==MFC_Size){field=&ctx->mfc_size;index=3;}
   else if(ch==MFC_TagID){field=&ctx->mfc_tag;index=4;x&=31;}
   else if(ch==MFC_WrTagMask){field=&ctx->mfc_tag_mask;index=5;}
   if(field){
    *field=x;
    if(mode==2){spu_wrch(ctx,ch,v);bces_channel_record(index,1,*field!=x);}
   }else{
    if(ch==MFC_Cmd){bces_channel_mfc_cmd(ctx,x);index=6;}
    else {bces_channel_tag_update(ctx,x);index=7;}
    /* Side-effectful commands execute once. Differential checking is native. */
    if(mode==2)bces_channel_record(index,0,0);
   }
   return;
  }
 }
 spu_wrch(ctx,ch,v);
}
static inline __attribute__((always_inline)) u128 bces_channel_rdch_inline(spu_context*ctx,uint32_t ch){
 if(__builtin_constant_p(ch) && ch==MFC_RdTagStat){
  unsigned mode=__atomic_load_n(&bces_channel_mode,__ATOMIC_RELAXED);
  if(mode){u128 v=spu_make_preferred_u32(ctx->mfc_tag_status);
   if(mode==2){u128 ref=spu_rdch(ctx,ch);bces_channel_record(8,1,memcmp(&v,&ref,sizeof v)!=0);}
   return v;
  }
 }
 return spu_rdch(ctx,ch);
}
#ifndef BCES_CHANNEL_PLAIN
#define spu_wrch(ctx,ch,v) bces_channel_wrch_inline((ctx),(ch),(v))
#define spu_rdch(ctx,ch) bces_channel_rdch_inline((ctx),(ch))
#endif
