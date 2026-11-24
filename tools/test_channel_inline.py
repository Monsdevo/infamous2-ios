#!/usr/bin/env python3
"""Actual MFC header/dispatcher branch versus inline constant channel calls."""
import json,os,subprocess
from pathlib import Path
from prepare_channel_inline import HELPERS
R=Path(__file__).resolve().parents[1];S=R/'upstream/infamous2-recomp/ps3recomp-fork';O=R/'build/bces01229/channel-inline-test';O.mkdir(exist_ok=True)
raw=(S/'runtime/spu/spu_channels.c').read_text()
def block(s,start):
 b=s.index('{',start);depth=1;i=b+1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[start:i]
channel=block(raw,raw.index('static int channel_is_mfc('))
wr=block(raw,raw.index('    if (channel_is_mfc(channel))',raw.index('void spu_wrch(')))
prefix=(R/'tools/tests/dma_poison_transfer.c').read_text().split('int main(')[0]
prefix=prefix.replace('void spu_ch_wake(spu_context*c){(void)c;}','static unsigned wakes;void spu_ch_wake(spu_context*c){(void)c;wakes++;}')
fixture=prefix+r'''
#define BCES_CHANNEL_PLAIN
#include "SpuChannelInline.h"
static mfc_engine engine;
static unsigned lookups,atomic_calls,original_writes,original_reads;
static mfc_engine* mfc_for(spu_context*c){(void)c;lookups++;return &engine;}
static int spu_mfc_atomic(spu_context*c,uint32_t cmd){atomic_calls++;if(cmd==0xD0){c->atomic_stat=17;return 1;}return 0;}
'''+channel+r'''
void spu_wrch(spu_context*ctx,uint32_t channel,u128 value){
 original_writes++;uint32_t v=value._u32[0];
'''+wr+r'''
 abort();
}
u128 spu_rdch(spu_context*ctx,uint32_t channel){original_reads++;return spu_make_preferred_u32(mfc_channel_read(mfc_for(ctx),ctx,channel));}
'''+HELPERS+r'''
static uint64_t run(spu_context*c,unsigned i,int candidate){
 spu_context_init(c,100);c->event_mask=1;
 for(unsigned k=0;k<SPU_LS_SIZE;k++)c->ls[k]=(uint8_t)(k*17+i);
 for(unsigned k=0;k<sizeof memory;k++)memory[k]=(uint8_t)(k*13+i);
 mfc_engine_init(&engine);wakes=atomic_calls=lookups=original_writes=original_reads=notifications=0;reserved=i%4==0;
 unsigned sizes[]={0,1,2,4,8,16,128,1024,16384};unsigned n=sizes[i%9],tag=i%32;
 u128 v=spu_make_preferred_u32(0x1000);v._u32[1]=0xFFFFFFFF;v._u32[2]=0x12345678;v._u32[3]=0x87654321;
 #define WRITE(ch,x) do{v._u32[0]=(x);if(candidate)bces_channel_wrch_inline(c,(ch),v);else spu_wrch(c,(ch),v);}while(0)
 WRITE(MFC_LSA,0x1000);WRITE(MFC_EAH,0);WRITE(MFC_EAL,0x10000+(i%64)*0x4000);WRITE(MFC_Size,n);WRITE(MFC_TagID,0xFFFF0000u|tag);WRITE(MFC_WrTagMask,1u<<tag);
 unsigned cmd=i%11==0?0xD0:(i&1?0x40:0x20)|(i%3==1?1:i%3==2?2:0);
 WRITE(MFC_Cmd,cmd);WRITE(MFC_WrTagUpdate,i%3);
 u128 result=candidate?bces_channel_rdch_inline(c,MFC_RdTagStat):spu_rdch(c,MFC_RdTagStat);
 volatile uint32_t dynamic_channel=MFC_LSA;
 WRITE(dynamic_channel,0x2000);WRITE(MFC_WrListStallAck,0);
 u128 fallback=candidate?bces_channel_rdch_inline(c,MFC_RdAtomicStat):spu_rdch(c,MFC_RdAtomicStat);
 #undef WRITE
 fingerprint=1469598103934665603ull;digest(c,sizeof*c);digest(&engine,sizeof engine);digest(memory,sizeof memory);digest(&result,sizeof result);digest(&fallback,sizeof fallback);digest(&wakes,sizeof wakes);digest(&atomic_calls,sizeof atomic_calls);digest(&notifications,sizeof notifications);assert(!locks);return fingerprint;
}
int main(){
 memset(g_vm_page_bitmap,255,sizeof g_vm_page_bitmap);bces_channel_configure();spu_context*c=calloc(1,sizeof*c);assert(c);
 unsigned actual_fast=0;
 for(unsigned mode=0;mode<3;mode++){
  bces_channel_set(mode);
  for(unsigned i=0;i<256;i++){
   uint64_t ref=run(c,i,0);unsigned reference_lookups=lookups;
   uint64_t fast=run(c,i,1);assert(ref==fast);
   if(mode==1&&!bces_channel_forced()){assert(lookups<reference_lookups);actual_fast++;}
  }
 }
 uint64_t stats[11];bces_channel_stats(stats);assert(!stats[10]);
 if(!bces_channel_forced()){for(unsigned k=0;k<9;k++)assert(stats[k]);assert(stats[9]);assert(actual_fast==256);}
 else {assert(bces_channel_get()==0);for(unsigned k=0;k<11;k++)assert(!stats[k]);}
 printf("PASS 768 reference/inline state+VM+tag+event comparisons; forced=%u; actual_fast_cases=%u\n",bces_channel_forced(),actual_fast);free(c);return 0;
}
'''
(O/'test.c').write_text(fixture)
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer');cmd=['xcrun','clang','-std=c17','-O2','-g','-fsanitize=address,undefined','-DBCES_DMA_ORIGINAL_SCAN=1']
for p in (R/'src/platform',R/'build/bces01229/ios-prepared/trace-include',R/'build/bces01229/ios-prepared',S/'runtime/spu',S/'include'):cmd+=['-I',str(p)]
cmd += [str(O/'test.c'),str(R/'src/platform/SpuChannelControl.c'),str(R/'src/platform/DmaPoisonControl.c'),'-o',str(O/'test')]
r=subprocess.run(cmd,env=env,capture_output=True,text=True)
if r.returncode:raise RuntimeError(r.stderr)
results=[]
for diagnostic in (None,'SPU_CHHIST','SPU_POLLTRACE','SPU_TAGPROBE'):
 e=dict(env)
 for k in ('SPU_CHHIST','SPU_POLLTRACE','SPU_TAGPROBE'):e.pop(k,None)
 if diagnostic:e[diagnostic]='1'
 r=subprocess.run([str(O/'test')],env=e,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-5000:])
 results.append(dict(diagnostic=diagnostic,stdout=r.stdout));print(r.stdout.strip())
(R/'out/channel55-native.json').write_text(json.dumps(dict(valid=True,results=results,scope='Actual DMA engine/header and original MFC dispatch branch. Full context/VM/engine/event fingerprint. Atomic handler and non-MFC services stubbed; unchanged atomic call routing checked. ASan/UBSan; no performance claim.'),indent=2)+'\n')
