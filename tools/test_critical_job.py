#!/usr/bin/env python3
"""Exercise the actual probe and transformed whole-call bracket with deferred work."""
import json,os,re,subprocess
from pathlib import Path
from prepare_critical_job import patch,patch_wws
R=Path(__file__).resolve().parents[1];S=R/'upstream/infamous2-recomp/ps3recomp-fork';O=R/'build/bces01229/critical-job-test';O.mkdir(exist_ok=True)
raw=(R/'build/bces01229/spu/jobmod_638a73a6476e_e60c0/spu_recomp.c').read_text();derived=patch(raw)
part=derived[derived.index('void jobmod_638a73a6476e_e60c0_spu_func_00008648('):]
wrapper=re.search(r'        if \(__atomic_load_n\(&bces_critical_job_enabled,[\s\S]*?\n        }\n',part).group()
wws=patch_wws((R/'build/bces01229/spu/wwsjob_pm_at_00887100/spu_recomp.c').read_text())
wws_wrapper=re.search(r'        if \(__atomic_load_n\(&bces_critical_job_enabled,[\s\S]*?\n        }\n',wws).group()
fixture=r'''
#include "CriticalJobTrace.h"
#include "ps3emu/ps3_ftrace.h"
#include "spu_helpers.h"
#include <assert.h>
#include <pthread.h>
#include <unistd.h>
#include <setjmp.h>
ps3_ft_state g_ps3_ft={0};
static _Thread_local int pending;
void jobmod_638a73a6476e_e60c0_spu_func_00006B90(spu_context*c){c->gpr[10]._u32[0]+=1;pending=1;}
void spu_drain_call(spu_context*c,uint32_t ret){assert(pending);usleep(5000);c->gpr[10]._u32[0]+=2;c->ls[99]=17;c->pc=ret;pending=0;}
void spu_img_restore(spu_context*c,int32_t image){c->image_id=image;}
static void measured_call(spu_context*ctx){
WRAPPER
}
void spu_indirect_branch(spu_context*c){jobmod_638a73a6476e_e60c0_spu_func_00006B90(c);}
static void measured_job(spu_context*ctx){
JOB_WRAPPER
}
static void* worker(void* n){
 spu_context*c=calloc(1,sizeof*c);c->spu_id=(uint32_t)(uintptr_t)n;
 for(unsigned i=0;i<50;i++){
  BCESCriticalSpan a=bces_critical_begin(c,0x6B90,0x866C);
  BCESCriticalSpan b=bces_critical_begin(c,0x68D8,0x6BD8);
  c->pc=0x6BD8;bces_critical_end(b,c);c->pc=0x866C;bces_critical_end(a,c);
 }
 free(c);return NULL;
}
int main(void){
 g_ps3_ft.cap=20000;g_ps3_ft.buf=calloc(g_ps3_ft.cap,sizeof(ps3_ft_rec));
 g_ps3_ft.start=ps3_ft_now()-1;g_ps3_ft.end=g_ps3_ft.start+10000000000ull;g_ps3_ft.on=2;
 spu_context*c=calloc(1,sizeof*c),*reference=calloc(1,sizeof*c);assert(c&&reference);
 spu_context_init(c,100);c->spu_id=7;
 bces_critical_job_enable(0);measured_call(c);assert(!g_ps3_ft.n);memcpy(reference,c,sizeof*c);
 spu_context_init(c,100);c->spu_id=7;
 bces_critical_job_enable(1);measured_call(c);assert(!memcmp(c,reference,sizeof*c));
 assert(g_ps3_ft.n==13);ps3_ft_rec end=g_ps3_ft.buf[1];
 assert(end.kind==401 && end.t1-end.t0>=5000000ull);
 assert(g_ps3_ft.buf[4].kind==404 && g_ps3_ft.buf[4].a==0x866C && g_ps3_ft.buf[4].b==0x866C);
 assert(g_ps3_ft.buf[8].kind==408 && g_ps3_ft.buf[8].b==1);
 assert((g_ps3_ft.buf[2].a+((uint64_t)g_ps3_ft.buf[2].b<<32))<end.t1-end.t0);
 /* The common WWS job bracket must include its indirect entry and drain. */
 unsigned checkpoint=g_ps3_ft.n;
 spu_context_init(c,100);c->spu_id=7;c->gpr[5]._u32[0]=0x18F90;
 bces_critical_job_enable(0);measured_job(c);memcpy(reference,c,sizeof*c);
 spu_context_init(c,100);c->spu_id=7;c->gpr[5]._u32[0]=0x18F90;
 bces_critical_job_enable(1);measured_job(c);assert(!memcmp(c,reference,sizeof*c));
 assert(g_ps3_ft.n==checkpoint+13 && g_ps3_ft.buf[checkpoint+1].a==0x80018F90u);
 assert(g_ps3_ft.buf[checkpoint+1].t1-g_ps3_ft.buf[checkpoint+1].t0>=5000000ull);
 /* Probe-only entry/exit is read-only for guest registers, LS and context. */
 memcpy(reference,c,sizeof*c);BCESCriticalSpan span=bces_critical_begin(c,0x6B90,c->pc);bces_critical_end(span,c);assert(!memcmp(c,reference,sizeof*c));
 unsigned sampled=0;for(unsigned i=0;i<32;i++){span=bces_critical_begin(c,0x5A98,c->pc);sampled+=!!span.id;bces_critical_end(span,c);}assert(sampled==2);
 pthread_t threads[4];for(unsigned i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,worker,(void*)(uintptr_t)i));
 for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
 assert(!g_ps3_ft.writers&&!g_ps3_ft.dropped);
 /* Logical job lifetime survives an abandoned native C continuation. */
 c->gpr[0]=spu_link(0x3218);checkpoint=g_ps3_ft.n;
 jmp_buf resume;
 if(setjmp(resume)==0){bces_critical_logical_begin(c,0x18F90);usleep(5000);longjmp(resume,1);}
 c->host_depth++;bces_critical_logical_end(c);c->host_depth--;
 assert(g_ps3_ft.n==checkpoint+13 && g_ps3_ft.buf[checkpoint+1].a==0xC0018F90u);
 assert(g_ps3_ft.buf[checkpoint+1].t1-g_ps3_ft.buf[checkpoint+1].t0>=5000000ull);
 checkpoint=g_ps3_ft.n;bces_critical_logical_begin(c,0x18F90);bces_critical_logical_begin(c,0xE2A0);bces_critical_logical_end(c);
 assert(g_ps3_ft.n==checkpoint+15 && g_ps3_ft.buf[checkpoint+2].kind==418);
 span=bces_critical_begin(c,0x6B90,c->pc);unsigned before=g_ps3_ft.n;g_ps3_ft.on=3;bces_critical_end(span,c);assert(g_ps3_ft.n==before);
 g_ps3_ft.on=2;g_ps3_ft.start++;bces_critical_end(span,c);assert(g_ps3_ft.n==before);
 printf("PASS disabled/read-only state equivalence, actual call+deferred drain bracket, CPU/wall separation, 1/16 child sampling, concurrent writers, stopped/changed epoch; rows=%u\n",g_ps3_ft.n);
 free(c);free(reference);free(g_ps3_ft.buf);return 0;
}
'''.replace('JOB_WRAPPER',wws_wrapper).replace('WRAPPER',wrapper)
(O/'test.c').write_text(fixture)
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer');cmd=['xcrun','clang','-std=c17','-O2','-g','-fsanitize=address,undefined','-pthread']
for p in (R/'src/platform',R/'build/bces01229/ios-prepared/trace-include',S/'include',S/'runtime/spu'):cmd+=['-I',str(p)]
cmd += [str(O/'test.c'),str(R/'src/platform/CriticalJobTrace.c'),'-o',str(O/'test')]
r=subprocess.run(cmd,env=env,text=True,capture_output=True)
if r.returncode:raise RuntimeError(r.stderr)
r=subprocess.run([str(O/'test')],env=env,text=True,capture_output=True)
if r.returncode:raise RuntimeError(r.stderr)
(R/'out/job57-native.json').write_text(json.dumps(dict(valid=True,stdout=r.stdout,scope='Actual diagnostic code and transformed wrapper; deferred drain/callee stub, real context layout; not full game semantics or FPS.'),indent=2)+'\n');print(r.stdout)
