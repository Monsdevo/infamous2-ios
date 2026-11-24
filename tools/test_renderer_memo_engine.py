#!/usr/bin/env python3
"""Exercise the actual borrowed-output/hash adaptation against the SDK mock backend."""
from pathlib import Path
import os
import subprocess
from prepare_renderer_memo import renderer_source
from check_renderer_regression import EXPECTED

ROOT=Path(__file__).resolve().parents[1]
sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork'
out=ROOT/'build/bces01229/renderer-memo-test'
out.mkdir(parents=True,exist_ok=True)
host=ROOT/'build/host'
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
engine=out/'engine.c';engine.write_text(renderer_source((sdk/'libs/video/rsx_draw_engine.c').read_text()))
driver=out/'engine-driver.c'
driver.write_text('''#include "RendererMemo.h"
#include <stdio.h>
#include <stdlib.h>
int bces_engine_test_main(void);
int main(int argc,char**argv){unsigned mode=argc>1?atoi(argv[1]):0;
 bces_renderer_memo_set(0,mode);bces_renderer_memo_set(1,mode);
 int result=bces_engine_test_main();bces_renderer_memo_publish();
 for(unsigned k=0;k<2;k++){BCESMemoStats s=bces_renderer_memo_stats(k);
  printf("MEMO kind=%u mode=%u calls=%llu hits=%llu validations=%llu mismatches=%llu\\n",k,mode,(unsigned long long)s.calls,(unsigned long long)s.hits,(unsigned long long)s.validations,(unsigned long long)s.mismatches);
  if(s.mismatches)return 2;bces_renderer_memo_clear(k);}
 return result;}
''')
sources=[sdk/'libs/video/tests/test_rsx_draw_engine.c',engine,driver,out/'reference.c',
         ROOT/'src/platform/RendererMemo.c',ROOT/'src/platform/TextureHashMemo.c',ROOT/'src/platform/VertexFetchMemo.c']
objects=[]
for i,source in enumerate(sources):
    obj=out/f'engine-{i}.o';objects.append(str(obj))
    command=['xcrun','clang','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',
             '-fno-strict-aliasing','-fwrapv','-ffp-contract=off','-I'+str(sdk/'libs/video'),
             '-I'+str(sdk/'include'),'-I'+str(ROOT/'src/platform')]
    if i==0:command+=['-Dmain=bces_engine_test_main']
    subprocess.run(command+['-c',str(source),'-o',str(obj)],env=env,check=True)
# These are existing macOS-only test archives. No Mac library enters the iOS app.
archives=[host/'librsx_core.a',host/'librsx_diag_clock.a',host/'librsx_texture_common.a']
archives += [host/p for p in ['shader-deps/glslang/SPIRV/libSPIRV.a','shader-deps/glslang/glslang/libglslang.a',
    'shader-deps/glslang/External/spirv-tools/source/opt/libSPIRV-Tools-opt.a',
    'shader-deps/glslang/External/spirv-tools/source/libSPIRV-Tools.a',
    'shader-deps/glslang/glslang/libglslang-default-resource-limits.a',
    'shader-deps/spirv-cross/libspirv-cross-c.a','shader-deps/spirv-cross/libspirv-cross-msl.a',
    'shader-deps/spirv-cross/libspirv-cross-glsl.a','shader-deps/spirv-cross/libspirv-cross-core.a']]
executable=out/'engine-test'
subprocess.run(['xcrun','clang++','-fsanitize=address,undefined','-Wl,-dead_strip',*objects,*map(str,archives),'-o',str(executable)],env=env,check=True)
for mode in range(3):
    run=subprocess.run([str(executable),str(mode)],env=env,capture_output=True,text=True)
    (out/f'engine-mode{mode}.log').write_text(run.stdout+run.stderr)
    failures=[line.split('   (')[0] for line in run.stdout.splitlines() if line.startswith('[FAIL]')]
    if run.returncode!=1 or failures!=EXPECTED or 'runtime error:' in run.stderr or 'AddressSanitizer' in run.stderr:
        raise SystemExit(f'Mode {mode} failed: {failures}; inspect {out}/engine-mode{mode}.log')
    print(f'Mode {mode}: no new failures; four known SDK fixture mismatches retained')
    print('\n'.join(line for line in run.stdout.splitlines() if line.startswith('MEMO ')))
