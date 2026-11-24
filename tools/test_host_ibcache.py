#!/usr/bin/env python3
"""Compile the actual transformed resolver and its original with native stubs.
Checks function selection, mutable residency/registry, relocation, task exclusion,
reset calls and fail-closed validation; execution callbacks are invoked once.
"""
from pathlib import Path
import subprocess
from prepare_host_ibcache import patch
root=Path(__file__).resolve().parents[1];out=root/'build/bces01229/host-ib-test';out.mkdir(exist_ok=True)
original=(root/'build/bces01229/ios-prepared/diagnostic_spu_channels.c').read_text();modified=patch(original)
def function(s):
 a=s.index('void spu_indirect_branch(spu_context* ctx)\n{');return s[a:s.index('\n}',a)+2]
decl=modified[modified.index('typedef struct {uint32_t pc;'):modified.index('void spu_indirect_branch(spu_context* ctx)\n{')]
preamble=r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include "HostIBCache.h"
#include "SpuDispatchControl.h"
#define SPU_LS_MASK 0x3ffffu
#define SPU_RESIDENT_CODE_SLOTS 16
#define SPURS_TASKSET_PM_SYSCALL_LS 0x123u
#define SPURS_PM_EXIT_TO_KERNEL_LS 0x124u
#define SPURS_PM_SELECT_WORKLOAD_LS 0x128u
#define SPU_JOB_RETURN_LS 0x12cu
#define SPU_RESOLVER_ONLY_IMAGE_ID 999
#define SPU_TASKSET_TASK_LO 0x30000u
typedef struct spu_context {uint32_t pc,stop_request,irq_saved,irq_resume_pc,int_enable;
 int image_id,policy_mode,resident_ovl,resident_task,host_depth;uint32_t code_base,spu_id;
 struct {uint32_t lsa,size,source_ea;int image_id;uint32_t reloc;} resident_code[16];
 unsigned selected,calls,resets;} spu_context;
typedef void (*spu_fn)(spu_context*);
static uint64_t bces_ib_registry_generation;
static int s_task_elf_count,s_task_entry_count,diag;
static spu_fn map[4096];static unsigned lookup_calls;
static void a(spu_context*c){c->selected=1;c->calls++;}
static void b(spu_context*c){c->selected=2;c->calls++;}
static spu_fn spu_lookup(uint32_t pc,int image){lookup_calls++;return map[((pc>>2)+(unsigned)image*7)&4095];}
static int spu_taskset_resident_image(spu_context*c){(void)c;return 300;}
static int spu_taskset_task_image(uint32_t pc){(void)pc;return 301;}
static int spu_ib_diag_enabled(void){return diag;}
static void spu_check_stack_reset(spu_context*c,spu_fn f){(void)f;c->resets++;}
static void spu_indirect_branch_slow(spu_context*c){c->selected=99;c->calls++;}
'''
test=r'''
static void compare(spu_context initial,unsigned mode){
 spu_context r=initial,c=initial;bces_ib_set(0);original_branch(&r);
 bces_ib_set(mode);spu_indirect_branch(&c);
 assert(memcmp(&r,&c,sizeof r)==0);
 // Use the same address across iterations so the second dispatch can hit TLS.
 bces_ib_set(mode);spu_indirect_branch(&c);original_branch(&r);
 assert(memcmp(&r,&c,sizeof r)==0);
}
int main(void){
 for(unsigned i=0;i<4096;i++)map[i]=(i&1)?a:b;
 bces_spu_dispatch_set(1,1);
 for(unsigned i=0;i<10000;i++){
  spu_context c={0};c.pc=0x4000+4*(i%128);c.image_id=100;c.resident_ovl=200+(i%5);c.spu_id=i%5;
  if(i%3){c.resident_code[0].lsa=0x4000;c.resident_code[0].size=0x1000;c.resident_code[0].image_id=201;c.resident_code[0].reloc=i%2;}
  if(i%17==0)c.stop_request=1;if(i%19==0)c.policy_mode=1;
  if(i%23==0){c.pc=0x31000;s_task_elf_count=1;}else s_task_elf_count=0;
  if(i%29==0)c.irq_saved=1;
  compare(c,1);compare(c,2);
 }
 spu_context c={0};c.pc=0x5000;c.image_id=100;c.resident_ovl=200;c.spu_id=0;
 bces_ib_set(2);spu_indirect_branch(&c);spu_indirect_branch(&c);
 uint64_t counts[4];bces_ib_totals(counts);assert(counts[0]>0 && counts[2]>0 && !counts[3]);
 // Registry replacement invalidation must select the updated function.
 for(unsigned i=0;i<4096;i++)map[i]=a;bces_ib_registry_generation++;
 bces_ib_set(1);spu_indirect_branch(&c);assert(c.selected==1);
 // Mutate the answer WITHOUT generation only to inject a shadow mismatch.
 bces_ib_set(2);for(unsigned i=0;i<4096;i++)map[i]=b;
 spu_indirect_branch(&c);assert(c.selected==2);assert(bces_ib_mode==0);
 bces_ib_totals(counts);assert(counts[3]==1);
 puts("PASS actual resolver: 40000 differential dispatches, hit shadow validation, registry/residency keys and fault closure");
}
'''
src=out/'resolver.c';src.write_text(preamble+function(original).replace('void spu_indirect_branch(','void original_branch(',1)+'\n'+decl+function(modified)+'\n'+test)
exe=out/'resolver';subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-I',str(root/'src/platform'),str(src),str(root/'src/platform/HostIBCache.c'),str(root/'src/platform/SpuDispatchControl.c'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True)
