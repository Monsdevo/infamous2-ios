#!/usr/bin/env python3
import subprocess
from pathlib import Path
from prepare_skinning_reference import prepare,ROOT,MODULE
from prepare_geometry_kernels import prepare as kernels
work=prepare();kernels();out=ROOT/'out/skinning-derived';out.mkdir(exist_ok=True)
binary=work/'cases'
subprocess.run(['clang','-std=gnu17','-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT','-DBCES_GEOMETRY_PARALLEL_TEST','-fsanitize=address,undefined',
 '-I'+str(ROOT/'src/game'),'-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'src/host'),'-I'+str(ROOT/'build/bces01229/spu'/MODULE),'-I'+str(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'),
 str(work/'reference.c'),str(work/'geometry_flat.c'),str(ROOT/'tools/tests/geometry_cases.c'),'-o',str(binary)],check=True)
subprocess.run([str(binary),str(ROOT/'out/edge35-failure.bin'),str(out)],check=True)
