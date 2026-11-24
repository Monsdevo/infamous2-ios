#!/usr/bin/env python3
"""Build the production routing adapter with sanitizers; Mac-only checks.
The returned binary exercises the real batching/admission code; no device IO.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
from prepare_skinning_reference import prepare,ROOT,MODULE
work=prepare()
subprocess.run([sys.executable,str(ROOT/'tools/test_geometry_batches.py')],check=True)
inc=['-I'+str(p) for p in (ROOT/'src/game',ROOT/'src/platform',ROOT/'src/host',work,ROOT/'build/bces01229/spu'/MODULE,ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu')]
common=['-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT','-DBCES_GEOMETRY_TEST_FAULT','-fsanitize=address,undefined']
objects=[str(work/(name+'-asan.o')) for name in ('geometry_execute','geometry_batches','GeometryMathProbe')]
for path in (work/'reference.c',ROOT/'tools/tests/geometry_runtime_cases.c'):
 obj=work/(path.stem+'-runtime.o');command=['clang','-std=gnu17',*common,*inc,'-c',str(path),'-o',str(obj)]
 h=hashlib.sha256(path.read_bytes()+json.dumps(command).encode()+b''.join(p.read_bytes() for p in (ROOT/'src/platform/GeometryKernels.h',ROOT/'src/platform/GeometryBatch.h'))).hexdigest();stamp=obj.with_suffix('.hash')
 if not obj.exists() or not stamp.exists() or stamp.read_text()!=h:subprocess.run(command,check=True);stamp.write_text(h)
 objects.append(str(obj))
binary=work/'runtime-check'
subprocess.run(['clang++','-std=c++20','-fobjc-arc',*common,*inc,str(ROOT/'src/platform/GeometryKernels.mm'),str(ROOT/'src/platform/GeometryMetalBatches.mm'),*objects,'-framework','Foundation','-framework','Metal','-o',str(binary)],check=True)
print(binary)
