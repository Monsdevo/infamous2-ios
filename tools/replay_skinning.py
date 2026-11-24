#!/usr/bin/env python3
import argparse,subprocess
from pathlib import Path
from prepare_skinning_reference import prepare,ROOT,MODULE
ap=argparse.ArgumentParser();ap.add_argument('fixture',type=Path);ap.add_argument('--states',type=Path,required=True);args=ap.parse_args()
work=prepare();binary=work/'replay'
subprocess.run(['clang','-std=gnu17','-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT','-fsanitize=address,undefined',
    '-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'src/host'),'-I'+str(ROOT/'build/bces01229/spu'/MODULE),
    '-I'+str(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'),str(work/'reference.c'),str(ROOT/'tools/tests/skinning_replay.c'),'-o',str(binary)],check=True)
subprocess.run([str(binary),str(args.fixture.resolve()),str(args.states.resolve())],check=True)
