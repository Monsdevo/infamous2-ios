#!/usr/bin/env python3
"""Exercise the exact derived skip predicate with a captured BCES descriptor."""
from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
s=(root/'build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_draw_engine.c').read_text()
start=s.index('static u32 bces_ls_word(');end=s.index('\n}\n',s.index('int bces_light_allow_job(',start))+3
body=s[start:end]
program=r'''
#include "spu_context.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
uint8_t* vm_base;
uint32_t bces_light_input_epoch,bces_light_active_epoch,io_base=0x40500000;
uint64_t bces_light_fallback_count;
uint32_t bces_gcm_io_ea(uint32_t io){return io_base+io;}
'''+body+r'''
int main(int argc,char** argv){
 assert(argc==2);spu_context* c=calloc(1,sizeof *c);c->ls=c->ls_store;
 FILE* f=fopen(argv[1],"rb");assert(f && fread(c->ls,1,0x40000,f)==0x40000);fclose(f);
 vm_base=calloc(1,0x1000000);assert(vm_base);c->gpr[84]._u32[0]=0xa000;
 uint32_t state=bces_ls_word(c->ls+0xa000),desc=bces_ls_word(c->ls+0x9f0c);
 assert(state+128<0x1000000 && desc+128<0x1000000);
 memcpy(vm_base+state,c->ls+0x9f00,16);memcpy(vm_base+desc,c->ls+0x9d80,128);
 spu_context* saved=malloc(sizeof *c);memcpy(saved,c,sizeof *c);
 assert(!bces_light_allow_job(c)); // GPU input not ready.
 bces_light_input_epoch=1;assert(bces_light_allow_job(c));assert(bces_light_active_epoch==1);
 io_base=0x40400000;assert(!bces_light_allow_job(c));io_base=0x40500000;
 vm_base[desc+0x49]=0x10;assert(!bces_light_allow_job(c));vm_base[desc+0x49]=0x20;
 assert(!memcmp(saved,c,sizeof *c));
 puts("PASS: actual BCES layout accepted only with ready/matching GPU mapping; wrong tile geometry rejected; SPU state unchanged");
 free(saved);free(vm_base);free(c);return 0;
}
'''
with tempfile.TemporaryDirectory(dir=root/'build/tmp',prefix='light-guard-') as d:
 d=Path(d);(d/'test.c').write_text(program)
 subprocess.run(['clang','-std=c17','-O2','-I'+str(root/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'),str(d/'test.c'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test'),str(a.fixture.resolve())],check=True)
