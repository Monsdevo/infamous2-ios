#!/usr/bin/env python3
"""Actual source-walk state oracle + randomized rejection tests under sanitizers."""
import hashlib,json,os,subprocess
from pathlib import Path
from prepare_overlay_filter import patch,function_span
R=Path(__file__).resolve().parents[1];S=R/'upstream/infamous2-recomp/ps3recomp-fork';O=R/'build/bces01229/overlay-filter-test';O.mkdir(exist_ok=True)
raw=(S/'runtime/spu/spu_channels.c').read_text();new=patch(raw)
def fn(s,name):
 a,_,b=function_span(s,name);return s[a:b]
start=new.index('typedef struct { uint32_t src_ea;');end=new.index('/* Register one-way runtime entries',start)
registry=new[start:end]
sig=fn(new,'spu_overlay_register_sig_impl')+'\n'+fn(new,'spu_overlay_register_sig')
start=new.index('static uint64_t s_ovl_ea_bits[64];');end=new.index('void spu_overlay_note_get(',start)
summary=new[start:end]
reference=fn(raw,'spu_overlay_note_get').replace('void spu_overlay_note_get(','static void reference_note_get(',1).replace('    if (ovl_cannot_match(ea, lsa, size)) return;','',1)
fixture=r'''
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "spu_context.h"
#include "win32_compat.h"
#include "OverlayFilterControl.h"
static uint8_t* vm_base;
static uint8_t s_reloc_img[4096];
static int gm_equal(const void*a,const void*b,size_t n){return !memcmp(a,b,n);}
static void spu_ovl_dump(spu_context*c,uint32_t e,uint32_t l,const uint8_t*p,uint32_t n){(void)c;(void)e;(void)l;(void)p;(void)n;}
static void bces_overlay_registration_enter(void);
static void bces_overlay_registration_leave(void);
'''+registry+'\n'+sig+'\n'+summary+'\n'+reference+'\n'+fn(new,'spu_overlay_note_get')+r'''
static uint32_t rng(uint32_t*state){*state=*state*1664525u+1013904223u;return *state;}
static void* reader(void*arg){
 uint32_t seed=12+(unsigned)(uintptr_t)arg;spu_context*c=calloc(1,sizeof*c);assert(c);spu_context_init(c,0);
 for(unsigned i=0;i<30000;i++){
  uint32_t size=rng(&seed)%16385,lsa=rng(&seed)%(SPU_LS_SIZE-size+1),ea=rng(&seed)%0x700000;
  memset(c->ls+lsa,(int)seed,size);
  uint64_t before=__atomic_load_n(&bces_overlay_generation,__ATOMIC_ACQUIRE);
  int reject=bces_overlay_candidate(ea,c->ls+lsa,lsa,size);
  AcquireSRWLockShared(&bces_overlay_registry_lock);
  int match=bces_overlay_exact_match(ea,c->ls+lsa,lsa,size);
  uint64_t after=__atomic_load_n(&bces_overlay_generation,__ATOMIC_ACQUIRE);
  ReleaseSRWLockShared(&bces_overlay_registry_lock);
  if(before==after && !(before&1u))assert(!reject||!match);
 }
 free(c);return NULL;
}
int main(){
 vm_base=malloc(0x800000);assert(vm_base);for(unsigned i=0;i<0x800000;i++)vm_base[i]=(uint8_t)(i*37+11);
 spu_context*base=calloc(1,sizeof*base);spu_context*oracle=calloc(1,sizeof*oracle);spu_context*c=calloc(1,sizeof*c);assert(base&&oracle&&c);spu_context_init(base,100);spu_context_init(oracle,100);spu_context_init(c,100);
 bces_overlay_filter_set(1);assert(bces_overlay_candidate(0x12345,base->ls+10,10,1));
 /* Populate sparse regions and signatures after an empty cached summary. */
 for(unsigned i=0;i<30;i++)spu_overlay_register_source(0x10000+i*0x10000,200+i);
 for(unsigned i=0;i<30;i++){uint8_t sig[16];for(unsigned k=0;k<16;k++)sig[k]=(uint8_t)(i*7+k*3+1);spu_overlay_register_sig(sig,300+i);}
 for(unsigned i=0;i<35;i++)spu_overlay_register_region_at(0x400000+i*0x1000,0x400+i*0x1800,((i%3)+1)*513,400+i);
 assert(s_ovl_src_count==95);
 /* Metadata publication without a count change invalidates every TLS summary. */
 (void)bces_overlay_candidate(1,base->ls+0x3e001,0x3e001,1);
 int count=s_ovl_src_count;bces_overlay_registration_enter();s_ovl_src[60].lift_lsa=0x3e001;s_ovl_src[60].span=1500;bces_overlay_registration_leave();assert(count==s_ovl_src_count);
 memcpy(base->ls+0x3e001,vm_base+s_ovl_src[60].src_ea,1500);assert(!bces_overlay_candidate(0x12345,base->ls+0x3e001,0x3e001,1500));
 uint32_t state=42;unsigned rejects=0,full=0;
 const unsigned sizes[]={0,1,3,4,127,128,511,512,513,1023,1024,16384};
 for(unsigned i=0;i<12000;i++){
  spu_context_init(base,100);base->image_id=100;base->resident_ovl=77;
  unsigned size=sizes[i%12],lsa=rng(&state)%(SPU_LS_SIZE-size+1),ea=rng(&state)%0x700000;
  memset(base->ls+lsa,(int)(state>>16),size);
  unsigned index=rng(&state)%95;spu_ovl_src*o=&s_ovl_src[index];
  if(i%6==1){index=30+rng(&state)%30;o=&s_ovl_src[index];size=512;lsa=(rng(&state)%(SPU_LS_SIZE-size))&~15u;memset(base->ls+lsa,0x21,size);memcpy(base->ls+lsa,o->sig,16);}
  if(i%6==2){index=rng(&state)%30;ea=s_ovl_src[index].src_ea;}
  if(i%6==3){index=60+rng(&state)%35;o=&s_ovl_src[index];lsa=o->lift_lsa;size=o->span;ea=o->src_ea+0x200000;memcpy(base->ls+lsa,vm_base+o->src_ea,size);}
  if(i%6==4){index=30+rng(&state)%30;o=&s_ovl_src[index];size=512;lsa=0x2000;memcpy(base->ls+lsa,o->sig,16);base->ls[lsa+15]^=1;}
  if(i%6==5){base->resident_code[0].image_id=500;base->resident_code[0].lsa=lsa;base->resident_code[0].size=size;base->resident_code[0].source_ea=0x700000;}
  int reject=bces_overlay_candidate(ea,base->ls+lsa,lsa,size);assert(!reject||!bces_overlay_exact_match(ea,base->ls+lsa,lsa,size));rejects+=reject;
  memcpy(oracle,base,sizeof*base);oracle->ls=oracle->ls_store;reference_note_get(oracle,ea,oracle->ls+lsa,size);
  for(unsigned mode=0;mode<=2;mode++){
   memcpy(c,base,sizeof*base);c->ls=c->ls_store;bces_overlay_filter_set(mode);spu_overlay_note_get(c,ea,c->ls+lsa,size);
   assert(c->resident_ovl==oracle->resident_ovl);assert(!memcmp(c->resident_code,oracle->resident_code,sizeof c->resident_code));full++;
  }
 }
 /* Actual parallel cache rebuild/read while new registrations publish. */
 pthread_t threads[4];for(unsigned i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,reader,(void*)(uintptr_t)i));
 for(unsigned i=0;i<30;i++)spu_overlay_register_region_at(0x780000+i*128,0x3f000+i*16,128,600+i);
 for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
 uint64_t stats[4];bces_overlay_filter_stats(stats);assert(rejects>1000 && stats[0]>=12000 && stats[1]>1000 && stats[2]>100 && !stats[3]);
 printf("PASS full-state comparisons=%u; parallel predicates=120000; rejects=%u; extra-rejects=%llu; mismatches=%llu\n",full,rejects,(unsigned long long)stats[2],(unsigned long long)stats[3]);
 free(base);free(oracle);free(c);free(vm_base);return 0;
}
'''
(O/'test.c').write_text(fixture)
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
cmd=['xcrun','clang','-std=c17','-O1','-g','-fsanitize=address,undefined','-pthread']
for p in (R/'src/platform',S/'runtime/spu',S/'runtime/platform',S/'include'):cmd+=['-I',str(p)]
cmd += [str(O/'test.c'),str(R/'src/platform/OverlayFilterControl.c'),'-o',str(O/'test')]
r=subprocess.run(cmd,env=env,text=True,capture_output=True)
if r.returncode:raise RuntimeError(r.stderr)
r=subprocess.run([str(O/'test')],env=env,text=True,capture_output=True)
if r.returncode:raise RuntimeError(r.stderr[-6000:])
(R/'out/overlay54-native.json').write_text(json.dumps(dict(valid=True,stdout=r.stdout,stderr=r.stderr,fixture_sha256=hashlib.sha256(fixture.encode()).hexdigest(),scope='Actual note_get context effects versus original full walk with all early rejection bypassed. Real context layout; stable-memory gm_equal and dump stubs. ASan/UBSan; no performance claim.'),indent=2)+'\n');print(r.stdout)
