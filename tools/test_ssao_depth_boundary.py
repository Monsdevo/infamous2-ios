#!/usr/bin/env python3
"""Execute production lifted GETLLAR/PUTLLC claim code with deterministic races.
Only descriptor preparation after a successful claim is stubbed. No game assets.
"""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_metal_ssao import depth_reference_source
import json
report=json.loads((ROOT/'out/bces-support-compile-iphoneos-spu-O2-copy.json').read_text())
work=ROOT/'build/bces01229/ssao-depth-test';work.mkdir(exist_ok=True)
depth_reference_source(work,report)
s=(work/'ssao_spu_reference.c').read_text()
a=s.index('void jobmod_e6fe749031f8_e2060_spu_func_00004B9C(spu_context* ctx) {');b=s.index('\nvoid ',a+1)
s=s[:a]+'''void jobmod_e6fe749031f8_e2060_spu_func_00004B9C(spu_context* ctx) {
 ctx->gpr[3]=spu_and(ctx->gpr[80],spu_ila(0xffff));
 ctx->pc=0x4BB8;g_spu_trampoline_fn=jobmod_e6fe749031f8_e2060_spu_func_00004BB8;return;
}
'''+s[b:]
(work/'claim.c').write_text(s)
sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'
command=['clang','-std=gnu17','-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT','-fsanitize=address,undefined','-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'build/bces01229/spu/jobmod_e6fe749031f8_e2060'),'-I'+str(sdk),str(work/'claim.c'),str(ROOT/'src/platform/SSAODepthBoundary.c'),str(ROOT/'tools/tests/ssao_depth_boundary.c'),'-Wl,-dead_strip','-o',str(work/'test')]
subprocess.run(command,check=True);subprocess.run([str(work/'test')],check=True)
