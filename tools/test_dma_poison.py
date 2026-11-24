#!/usr/bin/env python3
"""Actual DMA submit header: reference vs scan vs skip; no performance claim.
Stub host allocation/watch/overlay hooks; exercise both coherent copy branches,
GET/PUT, fence/barrier variants and tag completion. Concurrency not simulated.
"""
import os,subprocess,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'build/bces01229/dma-poison-test';out.mkdir(exist_ok=True)
s=(root/'build/bces01229/ios-prepared/diagnostic_spu_dma.h').read_text()
needle='          if(bces_dma_poison_scan(spu->spu_id,size))\n'
assert s.count(needle)==1
original=s.removeprefix('#include "DmaPoisonControl.h"\n').replace(needle,'',1)
(out/'oracle.h').write_text(original)
# Verify transformation roundtrip: the diagnostic scan guard is the only edit.
from prepare_dma_poison import patch
assert patch(original)==s
include=['src/platform','build/bces01229/ios-prepared/trace-include','build/bces01229/ios-prepared','upstream/infamous2-recomp/ps3recomp-fork/runtime/spu','upstream/infamous2-recomp/ps3recomp-fork/include']
cc=['xcrun','clang','-std=c17','-O1','-g','-fsanitize=address,undefined',*[x for p in include for x in ('-I',str(root/p))],'-I',str(out)]
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer');env.pop('SPU_POISON_DMA',None)
for name,extra in [('oracle',['-DDMA_TEST_HEADER="oracle.h"']),('candidate',[]),('original-build',['-DBCES_DMA_ORIGINAL_SCAN=1'])]:
 subprocess.run(cc+extra+[str(root/'tools/tests/dma_poison_transfer.c'),str(root/'src/platform/DmaPoisonControl.c'),'-o',str(out/name)],env=env,check=True,capture_output=True)
results=[]
for name,args,forced in [('oracle',[],False),('candidate',[],False),('candidate',['skip'],False),('candidate',['skip'],True),('original-build',['skip'],False)]:
 e=dict(env)
 if forced:e['SPU_POISON_DMA']='1'
 r=subprocess.run([str(out/name),*args],env=e,text=True,capture_output=True,check=True)
 results.append(dict(name=name,args=args,forced=forced,stdout=r.stdout.strip(),stderr=r.stderr.strip()))
assert len({r['stdout'] for r in results})==1,results
assert 'scanned=17 skipped=0' in results[1]['stderr']
assert 'scanned=0 skipped=17' in results[2]['stderr']
assert 'scanned=17 skipped=0' in results[3]['stderr']
assert all('[POISON-DMA]' in results[i]['stderr'] for i in (0,1,3))
assert '[POISON-DMA]' not in results[2]['stderr']
assert 'scanned=0 skipped=0' in results[4]['stderr'] and '[POISON-DMA]' in results[4]['stderr']
(root/'out/dma51-native-test.json').write_text(json.dumps(dict(valid=True,transfers_per_run=9000,runs=results,source_change='Only guard around post-copy diagnostic payload scan; fences and transfer paths byte-identical'),indent=2)+'\n')
print('PASS 5 x 9000 actual DMA submits under ASan/UBSan; data/tag/coherency fingerprints match; original-build scan preserved without counters')
