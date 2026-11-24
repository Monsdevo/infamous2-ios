#!/usr/bin/env python3
"""Full-state tests for non-loop leaf blocks; loop blocks validated on real input."""
import json,re,subprocess,os,sys
from pathlib import Path
from prepare_host_spu_math import ROOT,MODULE,derive
work=ROOT/'build/bces01229/host-math-test';work.mkdir(exist_ok=True)
s=(ROOT/'build/bces01229/spu'/MODULE/'spu_recomp.c').read_text()
functions={n:b for n,b in re.findall(r'void (\w+)\(spu_context\* ctx\) \{(.*?)\n\}',s,re.S)}
_,selection=derive(s);names={i['name'] for i in selection}
# Use exactly the generated transformation, without the registration tail.
full=(work/'host_spu_math.c').read_text();parts=[]
for i in selection:
 n=i['name'];start=full.index('static __attribute__((noinline)) void '+n+'_math_reference(')
 end=full.index('\n}\n',full.index('void '+n+'(spu_context* ctx)',start))+3
 parts.append(full[start:end])
proto='#include "spu_recomp.h"\n#include "BCESSpuRZ.h"\n#include "HostSpuMath.h"\n'
proto+='\n'.join('void '+n+'(spu_context*ctx){(void)ctx;}' for n in functions if n not in names)
(work/'kernels.c').write_text(proto+'\n'+'\n'.join(parts))
selected=[i['name'] for i in selection if 'goto loc' not in functions[i['name']]]
main='''
#include "spu_recomp.h"
#include "HostSpuMath.h"
#include <assert.h>
int g_spu_ls_dbg=0,g_spu_ls_watch_n=0;
void spu_indirect_branch(spu_context*c){(void)c;}
void spu_ls_watch_slow(const spu_context*c,uint32_t a,int w,const uint8_t*p,uint32_t pc,uint32_t lr){(void)c;(void)a;(void)w;(void)p;(void)pc;(void)lr;}
static uint32_t seed=0x41a40023;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
typedef void(*Fn)(spu_context*);
static Fn fns[]={FNS};
int main(void){
 spu_context*a=calloc(1,sizeof*a),*b=calloc(1,sizeof*b);uint8_t*ls=malloc(SPU_LS_SIZE),*other=malloc(SPU_LS_SIZE);assert(a&&b&&ls&&other);
 unsigned cases=0;uint64_t initial;__asm__ volatile("mrs %0, fpcr":"=r"(initial));
 for(unsigned flush=0;flush<2;flush++)for(unsigned fn=0;fn<sizeof(fns)/sizeof(*fns);fn++)for(unsigned t=0;t<64;t++){
  uint64_t control=(initial&~((3ull<<22)|(1ull<<24)))|((uint64_t)flush<<24);__asm__ volatile("msr fpcr, %0\\n\\tisb"::"r"(control):"memory");
  memset(a,0,sizeof*a);a->ls=ls;a->host_depth=t&1;a->spu_id=t&15;
  for(unsigned r=0;r<128;r++)for(unsigned l=0;l<4;l++)a->gpr[r]._u32[l]=next();
  for(unsigned i=0;i<SPU_LS_SIZE;i+=4){uint32_t v=next();memcpy(ls+i,&v,4);}
  if(t&2){memcpy(a->ls_store,ls,SPU_LS_SIZE);a->ls=a->ls_store;}
  memcpy(b,a,sizeof*a);b->ls=(t&2)?b->ls_store:other;memcpy(b->ls,a->ls,SPU_LS_SIZE);
  bces_host_math_set(0);fns[fn](a);
  uint64_t fpsr,after,fpcr;__asm__ volatile("mrs %0, fpsr":"=r"(fpsr));bces_host_math_set(1);fns[fn](b);
  __asm__ volatile("mrs %0, fpsr":"=r"(after));__asm__ volatile("mrs %0, fpcr":"=r"(fpcr));assert(after==fpsr&&fpcr==control);
  int equal=!memcmp(a->ls,b->ls,SPU_LS_SIZE);b->ls=a->ls;
  if(!equal||memcmp(a,b,sizeof*a)){fprintf(stderr,"FAIL block=%u case=%u flush=%u\\n",fn,t,flush);return 1;}cases++;
 }
 __asm__ volatile("msr fpcr, %0\\n\\tisb"::"r"(initial):"memory");
 BCESHostSpuMathStats counters=bces_host_math_stats();assert(counters.reference==cases&&counters.fast==cases&&!counters.mismatches);
 bces_host_math_result(0,0);bces_host_math_set(1);assert(bces_host_math_mode()==0&&bces_host_math_stats().mismatches==1);
 printf("PASS %u complete context/LS comparisons across %zu non-loop blocks; both LS layouts, both return modes, FZ off/on, FPCR/FPSR preserved. Loop blocks require actual-input validation.\\n",cases,sizeof(fns)/sizeof(*fns));
}
'''.replace('FNS',','.join(selected))
(work/'test.c').write_text(main)
command=['xcrun','clang','-std=gnu17','-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT','-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'src/game'),'-I'+str(ROOT/'build/bces01229/spu'/MODULE),'-I'+str(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'),str(work/'kernels.c'),str(work/'test.c'),str(ROOT/'src/platform/HostSpuMath.c'),'-o',str(work/'test')]
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer',TMPDIR=str(ROOT/'build/tmp'))
if '--sanitize' in sys.argv:command[2:2]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
marker=ROOT/'out/host-research/measurement-inhibit.json';owned=not marker.exists()
if owned:marker.write_text(json.dumps(dict(reason='SPU math correctness build/test active',owner_pid=os.getpid()))+'\n')
try:
 subprocess.run(command,env=env,check=True);subprocess.run([str(work/'test')],check=True)
finally:
 if owned:marker.unlink()
