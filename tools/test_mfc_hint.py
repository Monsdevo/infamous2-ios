#!/usr/bin/env python3
"""Exercise actual registry + hint wrapper with real context/engine types."""
import hashlib,json,os,subprocess
from pathlib import Path
from prepare_mfc_hint import patch
R=Path(__file__).resolve().parents[1];O=R/'build/bces01229/mfc-hint-test';O.mkdir(exist_ok=True)
sdk=R/'upstream/infamous2-recomp/ps3recomp-fork';raw=(sdk/'runtime/spu/spu_channels.c').read_text();modified=patch(raw)
assert modified.removeprefix('#include "MfcHintControl.h"\n').replace(__import__('prepare_mfc_hint').WRAPPER+'\n','',1).replace('static mfc_engine* mfc_for_scan(spu_context* ctx)\n','static mfc_engine* mfc_for(spu_context* ctx)\n',1)==raw
start=modified.index('#define SPU_MAX_CONTEXTS 128');end=modified.index('/* ===========================================================================\n * Atomic reservation',start)
fixture='''#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include "spu_dma.h"
#include "win32_compat.h"
#include "MfcHintControl.h"
'''+modified[start:end]+'''
static spu_context* contexts;
static unsigned start_workers;
static mfc_engine* worker_engines[32];
static void* worker(void* value){
 unsigned i=(unsigned)(uintptr_t)value;
 while(!__atomic_load_n(&start_workers,__ATOMIC_ACQUIRE))sched_yield();
 for(unsigned j=0;j<500;j++){
  mfc_engine* e=mfc_for(&contexts[i]);
  if(!j)worker_engines[i]=e;
  assert(e==worker_engines[i]);e->tag_completed=i+1;
  assert(mfc_for(&contexts[i])->tag_completed==i+1);
 }
 return NULL;
}
int main(){
 contexts=calloc(132,sizeof *contexts);assert(contexts);
 for(unsigned mode=0;mode<=2;mode++){
  bces_mfc_hint_set(mode);
  for(unsigned i=0;i<128;i++){
   assert(mfc_for(&contexts[i])==&s_mfc_slots[i].mfc);
   mfc_for(&contexts[i])->tag_completed=1234+i;
  }
  for(unsigned repeat=0;repeat<40;repeat++)for(unsigned i=0;i<128;i++){
   assert(mfc_for(&contexts[i])->tag_completed==1234+i);
   assert(mfc_for(&contexts[i])==mfc_for_scan(&contexts[i]));
  }
  mfc_engine* overflow=mfc_for(&contexts[128]);
  assert(overflow==mfc_for_scan(&contexts[128]));
  assert(overflow==mfc_for(&contexts[129]));
  /* Hint points at slot127; release it, then give it to another context. */
  assert(mfc_for(&contexts[127])==&s_mfc_slots[127].mfc);
  spu_mfc_release(&contexts[127]);
  assert(mfc_for(&contexts[130])==&s_mfc_slots[127].mfc);
  assert(mfc_for(&contexts[130])->tag_completed==UINT32_MAX);
  assert(mfc_for(&contexts[127])==overflow);
  spu_mfc_release(&contexts[130]);
  /* Same context pointer after release must receive a reset engine. */
  assert(mfc_for(&contexts[127])==&s_mfc_slots[127].mfc);
  assert(mfc_for(&contexts[127])->tag_completed==UINT32_MAX);
  for(unsigned i=0;i<132;i++)spu_mfc_release(&contexts[i]);
 }
 bces_mfc_hint_set(2);pthread_t threads[32];
 for(unsigned i=0;i<32;i++)assert(!pthread_create(&threads[i],NULL,worker,(void*)(uintptr_t)i));
 __atomic_store_n(&start_workers,1,__ATOMIC_RELEASE);
 for(unsigned i=0;i<32;i++)assert(!pthread_join(threads[i],NULL));
 for(unsigned i=0;i<32;i++)for(unsigned j=0;j<i;j++)assert(worker_engines[i]!=worker_engines[j]);
 for(unsigned i=0;i<32;i++)spu_mfc_release(&contexts[i]);
 uint64_t stats[3];bces_mfc_hint_stats(stats);assert(stats[0]>30000&&stats[1]>10000&&!stats[2]);
 printf("PASS modes0/1/2; 128 slots, context switches, stale/reused slots, overflow, reset, 32 concurrent claimants; checks=%llu hits=%llu mismatch=%llu\\n",(unsigned long long)stats[0],(unsigned long long)stats[1],(unsigned long long)stats[2]);free(contexts);return 0;
}
'''
(O/'test.c').write_text(fixture)
cmd=['xcrun','clang','-std=c17','-O1','-g','-fsanitize=address,undefined','-pthread']
for path in (R/'src/platform',sdk/'runtime/spu',sdk/'runtime/platform',sdk/'include'):cmd+=['-I',str(path)]
cmd+=[str(O/'test.c'),str(R/'src/platform/MfcHintControl.c'),'-o',str(O/'test')]
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
subprocess.run(cmd,env=env,check=True,capture_output=True)
r=subprocess.run([str(O/'test')],env=env,check=True,text=True,capture_output=True)
(R/'out/mfc53-native.json').write_text(json.dumps(dict(valid=True,stdout=r.stdout,stderr=r.stderr,fixture_sha256=hashlib.sha256(fixture.encode()).hexdigest(),scope='Actual registry and wrapper, real context/engine types, ASan/UBSan. Not game performance.'),indent=2)+'\n');print(r.stdout)
