#!/usr/bin/env python3
"""Real slot registry ownership/reset/concurrency, both layouts, ASan/UBSan."""
import hashlib,json,os,subprocess
from pathlib import Path
from prepare_mfc_alignment import patch,SLOT,MARKER
R=Path(__file__).resolve().parents[1];S=R/'upstream/infamous2-recomp/ps3recomp-fork'
O=R/'build/bces01229/mfc-alignment-test';O.mkdir(exist_ok=True)
raw=(S/'runtime/spu/spu_channels.c').read_text();results=[]
body=r'''
static spu_context* contexts;
static unsigned start_workers;
static mfc_engine* worker_engines[32];
static void* worker(void* value) {
 unsigned i=(unsigned)(uintptr_t)value;
 while(!__atomic_load_n(&start_workers,__ATOMIC_ACQUIRE))sched_yield();
 for(unsigned j=0;j<500;j++) {
  mfc_engine* e=mfc_for(&contexts[i]);
  if(!j)worker_engines[i]=e;
  assert(e==worker_engines[i]);e->tag_completed=i+1;
  assert(mfc_for(&contexts[i])->tag_completed==i+1);
 }
 return NULL;
}
int main(void) {
 uint64_t layout[8];bces_mfc_layout(layout);
 assert(layout[0]==ALIGNED && layout[1]==layout[4]);
 if(ALIGNED) {assert(layout[2]==128 && layout[3]==0);for(unsigned i=0;i<128;i++)assert(!((uintptr_t)&s_mfc_slots[i]&127));}
 contexts=calloc(132,sizeof *contexts);assert(contexts);
 for(unsigned cycle=0;cycle<3;cycle++) {
  for(unsigned i=0;i<128;i++) {assert(mfc_for(&contexts[i])==&s_mfc_slots[i].mfc);mfc_for(&contexts[i])->tag_completed=1000+i;}
  for(unsigned k=0;k<40;k++)for(unsigned i=0;i<128;i++)assert(mfc_for(&contexts[i])->tag_completed==1000+i);
  mfc_engine* overflow=mfc_for(&contexts[128]);assert(overflow==mfc_for(&contexts[129]));
  spu_mfc_release(&contexts[127]);assert(mfc_for(&contexts[130])==&s_mfc_slots[127].mfc);
  assert(mfc_for(&contexts[130])->tag_completed==UINT32_MAX);
  assert(mfc_for(&contexts[127])==overflow);spu_mfc_release(&contexts[130]);
  assert(mfc_for(&contexts[127])==&s_mfc_slots[127].mfc);
  assert(mfc_for(&contexts[127])->tag_completed==UINT32_MAX);
  for(unsigned i=0;i<132;i++)spu_mfc_release(&contexts[i]);
 }
 pthread_t threads[32];
 for(unsigned i=0;i<32;i++)assert(!pthread_create(&threads[i],NULL,worker,(void*)(uintptr_t)i));
 __atomic_store_n(&start_workers,1,__ATOMIC_RELEASE);
 for(unsigned i=0;i<32;i++)assert(!pthread_join(threads[i],NULL));
 for(unsigned i=0;i<32;i++)for(unsigned j=0;j<i;j++)assert(worker_engines[i]!=worker_engines[j]);
 for(unsigned i=0;i<32;i++)spu_mfc_release(&contexts[i]);
 puts("PASS 128-slot ownership, overflow, reset/reuse; 32 parallel claimants x500 lookups");
 printf("{\"aligned128\":%llu,\"slot_bytes\":%llu,\"slot_alignment\":%llu,\"base_mod128\":%llu,\"stride_bytes\":%llu,\"engine_offset\":%llu,\"table_bytes\":%llu,\"engine_bytes\":%llu}\n",layout[0],layout[1],layout[2],layout[3],layout[4],layout[5],layout[6],layout[7]);
 free(contexts);return 0;
}
'''
for aligned in (False,True):
 modified=patch(raw,aligned);start=modified.index('#define SPU_MAX_CONTEXTS 128');end=modified.index(MARKER,start)
 prefix='#include <assert.h>\n#include <stddef.h>\n#include <pthread.h>\n#include <sched.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include "spu_dma.h"\n#include "win32_compat.h"\n'
 fixture=prefix+modified[start:end]+body.replace('ALIGNED',str(int(aligned)))
 source=O/('aligned.c' if aligned else 'original.c');source.write_text(fixture);binary=source.with_suffix('')
 cmd=['xcrun','clang','-std=c17','-O2','-g','-fsanitize=address,undefined','-pthread']
 for p in (S/'runtime/spu',S/'runtime/platform',S/'include'):cmd+=['-I',str(p)]
 cmd += [str(source),'-o',str(binary)];env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
 r=subprocess.run(cmd,env=env,text=True,capture_output=True)
 if r.returncode:raise RuntimeError(r.stderr)
 r=subprocess.run([str(binary)],env=env,text=True,capture_output=True)
 if r.returncode:raise RuntimeError(r.stderr)
 layout=json.loads(r.stdout.splitlines()[-1]);results.append(dict(layout=layout,stdout=r.stdout,fixture_sha256=hashlib.sha256(fixture.encode()).hexdigest()));print(r.stdout.strip())
(R/'out/align56-native.json').write_text(json.dumps(dict(valid=True,results=results,scope='Actual private registry and engine types, ASan/UBSan. Layout only; no game performance or full DMA/atomic reservation simulation.'),indent=2)+'\n')
