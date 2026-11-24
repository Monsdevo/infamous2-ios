#!/usr/bin/env python3
"""Bounded independent loop batches: CPU control, sparse input, ordered outputs.
Never writes live SPU memory from a GPU kernel. CPU address preflight proves
snapshot independence; output records commit in original instruction order.
"""
import json,re
from pathlib import Path
from skinning_ir import ROOT,program
from geometry_parallel import parts as skin_parts,LOOPS
from prepare_geometry_kernels import scalar_helpers,put
PCS=(0xD800,0xD5B0,0xDA28,0xDCE0,0xDF20,0x7030,0xA650)

def parts():
 p=skin_parts()
 for pc,d in p.items():d['epilogue']=LOOPS[pc][1] if pc in LOOPS else []
 lines=program(0xA798)[0xA650].splitlines();lines=lines[:next(i for i,l in enumerate(lines) if l.startswith('if ('))]
 ops=[l for l in lines if re.match(r'r\[\d+\] = |SK_WRITE',l)]
 p[0xA650]={'ops':ops,'slice':[],'setup':'','counter':24,'step':64,'warm':3,'epilogue':[],
   'exit':'r[1]=spu_ai(r[1],48);r[80]=SK_READ(r[1]._u32[0]-16);return r[0]._u32[0];'}
 # Every GPU memory event receives its original iteration/instruction order.
 for pc,d in p.items():
  assert len(d['ops'])<512
  d['writes']=sum(l.startswith('SK_WRITE') for l in d['ops'])
  assert 0<d['writes']<=12
  w=set();live=set()
  for line in d['ops']:
   m=re.match(r'r\[(\d+)\]',line);t=int(m[1]) if m else None
   live|=regs(line.split('=',1)[1] if t is not None else line)-w
   if t is not None:w.add(t)
  if d.get('warm'):
   need=live.copy()
   for _ in range(d['warm']):
    for line in reversed(d['ops']):
     m=re.match(r'r\[(\d+)\]',line)
     if m and int(m[1]) in need:need.remove(int(m[1]));need|=regs(line.split('=',1)[1])
   affine={21,34} if pc==0x7030 else {22,24,31}
   assert (need&w)<=affine,(hex(pc),need&w)
 return p

def regs(s):return {int(x) for x in re.findall(r'r\[(\d+)\]',s)}
def address(line):
 if 'SK_READ(' in line:return line.split('SK_READ(',1)[1].rsplit(')',1)[0]
 return line.split('SK_WRITE(',1)[1].split(',',1)[0]

def address_slice(ops,tail_needed):
 need=set(tail_needed);kept=[]
 for line in reversed(ops):
  m=re.match(r'r\[(\d+)\]',line);t=int(m[1]) if m else None
  if line.startswith('SK_WRITE'):
   need|=regs(address(line));kept.append(line)
  elif 'SK_READ(' in line:
   if t in need:need.remove(t);kept.append(line)
   else:kept.append('PLAN_READ('+address(line)+');')
   need|=regs(address(line))
  elif t in need:
   assert not re.search(r'spu_(?:fm|fma|fms|fa|fs|fnms|fi|frest|frsqest|cflts|cuflt)\(',line),'Address depends on float: '+line
   need.remove(t);need|=regs(line.split('=',1)[1]);kept.append(line)
 return need,list(reversed(kept))

def planner_ops(d):
 needed=set()
 for _ in range(32):
  before=needed.copy();needed,ops=address_slice(d['ops'],needed)
  if before==needed:return ops,needed
 raise AssertionError('Address-state closure did not converge')

def skip_a650(metal=False):
 ptr='thread u128*' if metal else 'u128*'
 return f'''static inline int batch_skip_cull({ptr}r,uint32_t skip){{
 u128 phase=r[31],sum=spu_zero();uint32_t period=0;
 for(uint32_t i=1;i<=8;i++){{sum=spu_a(sum,phase);phase=spu_shufb(phase,phase,r[69]);bool same=true;for(uint32_t lane=0;lane<4;lane++)same=same&&phase._u32[lane]==r[31]._u32[lane];if(same){{period=i;break;}}}}
 if(!period)return 0;uint32_t cycles=skip/period,rest=skip%period;
 for(uint32_t lane=0;lane<4;lane++)r[22]._u32[lane]+=cycles*sum._u32[lane];
 phase=r[31];for(uint32_t i=0;i<rest;i++){{r[22]=spu_a(r[22],phase);phase=spu_shufb(phase,phase,r[69]);}}r[31]=phase;
 for(uint32_t lane=0;lane<4;lane++)r[24]._u32[lane]+=64u*skip;r[5]=spu_ori(r[24],0);return 1;
}}
'''

def iteration(metal=False,plan=False,tail=False):
 if metal:
  sig='static inline int batch_iteration(uint pc,thread u128*r,uint i,device const uchar*read_ls,device BCESBatchWrite*outputs,thread uint&hash,bool emit,device const u128*cull_states)'
 elif plan:sig='static int batch_iteration(uint32_t pc,u128*r,uint32_t i,const uint8_t*read_ls,PlanState*s)'
 elif tail:sig='static int batch_tail_iteration(uint32_t pc,u128*r,uint32_t i,const uint8_t*read_ls,const BCESBatchPlan*p)'
 else:raise AssertionError()
 code=sig+'{uint32_t order=i,sequence=0;'+('uint wi=0;' if metal else '')+'switch(pc){\n'
 for pc,d in parts().items():
  planops,need=planner_ops(d) if plan else (d['ops'],set())
  def emit_ops(ops,warm=False,slice_ops=False):
   text=[]
   for line in ops:
    if warm and line.startswith('SK_WRITE'):continue
    if line.startswith('PLAN_READ('):
     # Preserve the instruction number of a read whose value was dead in planning.
     addr=address(line.replace('PLAN_READ','SK_READ'))
     seq=next(j+1 for j,l in enumerate(d['ops']) if 'SK_READ(' in l and address(l).strip()==addr.strip())
    else:seq=d['ops'].index(line)+1 if line in d['ops'] else 0
    text.append(f'sequence={seq};'+line)
   return '\n'.join(text)
  code+=f'case 0x{pc:X}:{{\n'
  if d.get('warm'):
   code+='uint32_t warm=i<3?i:3,skip=i-warm;\n'
   if pc==0xA650:
    states='cull_states' if metal else 's->p->cull_states' if plan else 'p->cull_states'
    code+=f'r[22]={states}[i*3];r[24]={states}[i*3+1];r[31]={states}[i*3+2];r[5]=spu_ori(r[24],0);\n' 
   else:code+=''.join(f'for(uint32_t lane=0;lane<4;lane++)r[{reg}]._u32[lane]+=128u*skip;\n' for reg in (21,34))
   code+='for(uint32_t cycle=0;cycle<warm;cycle++){order=skip+cycle;\n'+emit_ops(planops if plan else d['ops'],True)+'\n}\n'
  else:
   seedops=d['slice']
   if plan:_,seedops=address_slice(seedops,need)
   code+='if(i){uint32_t prev=i-1;order=prev;\n'+d['setup']+'\n'+emit_ops(seedops,slice_ops=True)+'\n}\n'
  code+='order=i;\n'+emit_ops(planops if plan else d['ops'])+'\nreturn 1;}\n'
 return code+'default:return 0;}}\n'

def specialized_kernels(descriptors):
 """Output-only scalar SSA-like registers; no full r[128] GPU context.
 Full ABI/tail registers are completed once on CPU. Read-only dead values
 retain their address hash but cause no GPU load or arithmetic.
 """
 text=''
 for pc,d in descriptors.items():
  signature=f'kernel void geometry_batch_{pc:04x}(device const u128*seed [[buffer(0)]],device const uchar*ls [[buffer(1)]],device BCESBatchWrite*outputs [[buffer(2)]],device uint*hashes [[buffer(3)]],constant uint*parameters [[buffer(4)]],device const u128*cull_states [[buffer(6)]],uint i [[thread_position_in_grid]])'
  text+=signature+'{uint n=parameters[1];if(i>=n)return;outputs+=i*'+str(d['writes'])+';uint hash=2166136261u,wi=0;\n'
  branches=range(4) if d.get('warm') else range(2)
  for branch in branches:
   condition=f'i=={branch}' if branch<3 else 'true'
   if not d.get('warm'):condition='i==0' if branch==0 else 'true'
   text+=('if' if branch==0 else 'else if')+'('+condition+'){\n'
   seq=[]
   def append_ops(ops,order,omit_writes=False):
    for line in ops:
     if omit_writes and line.startswith('SK_WRITE'):continue
     stamp=f'(({order})*512u+{d["ops"].index(line)+1 if line in d["ops"] else 0})'
     seq.append((line,stamp))
   if d.get('warm'):
    warm=branch;skip=f'(i-{warm}u)'
    if pc==0xA650:
     for reg,j in [(22,0),(24,1),(31,2)]:seq.append((f'r[{reg}] = cull_states[i*3+{j}];',None))
     seq.append(('r[5] = spu_ori(r[24],0);',None))
    else:
     for reg in (21,34):seq.append((f'ADJUST {reg} 128u*{skip}',None))
    for cycle in range(warm):append_ops(d['ops'],f'i-{warm}u+{cycle}u',True)
   elif branch:
    affine=LOOPS[pc][2]
    for reg,stride in affine.items():seq.append((f'ADJUST {reg} (uint32_t)((int32_t)(i-1u)*({stride}))',None))
    append_ops(d['slice'],'i-1u')
   append_ops(d['ops'],'i')
   need=set();kept=[]
   for line,stamp in reversed(seq):
    if line.startswith('ADJUST '):
     _,r,expr=line.split(' ',2);r=int(r)
     if r in need:kept.append((f'for(uint lane=0;lane<4;lane++)r[{r}]._u32[lane]+={expr};',None))
     continue
    m=re.match(r'r\[(\d+)\]',line);target=int(m[1]) if m else None
    if line.startswith('SK_WRITE'):
     need|=regs(line);kept.append((line,stamp))
    elif 'SK_READ(' in line:
     if target in need:need.remove(target);kept.append((line,stamp))
     else:kept.append(('GPU_READ_ADDRESS('+address(line)+');',stamp))
     need|=regs(address(line))
    elif target in need:
     need.remove(target);need|=regs(line.split('=',1)[1]);kept.append((line,stamp))
   kept.reverse();used=set().union(*(regs(line) for line,_ in kept))
   for reg in sorted(used):text+=f'u128 v{reg}'+(f'=seed[{reg}]' if reg in need else '')+';'
   text+='\n'
   for line,stamp in kept:
    line=re.sub(r'r\[(\d+)\]',lambda m:'v'+m[1],line)
    line=line.replace('SK_READ(','batch_load(ls,').replace('SK_WRITE(','batch_store(outputs,').replace('GPU_READ_ADDRESS(','batch_hash_read(')
    if stamp is not None:
     if 'batch_load(' in line:line=line.rsplit(')',1)[0]+f',{stamp},hash,true);'
     elif 'batch_store(' in line:line=line.rsplit(')',1)[0]+f',{stamp},hash,wi,true);'
     elif 'batch_hash_read(' in line:line=line.rsplit(')',1)[0]+f',{stamp},hash);'
    text+=line+'\n'
   text+='}\n'
  text+='hashes[i]=hash;hashes[n+2+i]=wi=='+str(d['writes'])+'?1:0;}\n'
 return text

def prepare():
 out=ROOT/'build/bces01229/skinning';out.mkdir(exist_ok=True)
 descriptors=parts()
 common='''#include "GeometryBatch.h"
#include "BCESSpuRZ.h"
#include <stdbool.h>
static inline u128 batch_read(const uint8_t*ls,uint32_t a){a&=0x3fff0;u128 r;for(unsigned i=0;i<4;i++){uint32_t x;memcpy(&x,ls+a+4*i,4);r._u32[i]=__builtin_bswap32(x);}return r;}
'''
 count='unsigned bces_batch_count(uint32_t pc,const u128*r){uint32_t n=0;switch(pc){'
 for pc,d in descriptors.items():count+=f'case 0x{pc:X}:n={"0u-" if pc in (0x7030,0xA650) else ""}r[{d["counter"]}]._u32[0];if(n%{d["step"]})return 0;n/={d["step"]};break;'
 count+='default:return 0;}return n<=BCES_BATCH_MAX_ITERATIONS?n:0;}\n'
 finish='uint32_t bces_batch_finish(uint32_t pc,u128*r,const uint8_t*ls){switch(pc){\n'
 for pc,d in descriptors.items():finish+=f'case 0x{pc:X}:{{'+d['exit'].replace('SK_READ(','batch_read(ls,')+'}\n'
 finish+='default:return 0;}}\n'
 ref='''#define SK_READ(a) batch_read(ls,a)
#define SK_WRITE(a,v) bces_geometry_write(ls,a,v,dirty,execution)
static int batch_cpu_body(uint32_t pc,u128*r,uint8_t*ls,uint32_t*next,BCESGeometryExecution*execution){
 unsigned n=bces_batch_count(pc,r);if(!n)return 0;uint32_t*dirty=execution->dirty;switch(pc){
'''
 for pc,d in descriptors.items():
  ref+=f'case 0x{pc:X}:{{for(unsigned i=0;i<n;i++){{\n'+'\n'.join(d['ops'])+'\nif(i+1<n){'+'\n'.join(d['epilogue'])+'}\n}break;}\n'
 ref+='default:return 0;}*next=bces_batch_finish(pc,r,ls);return *next!=0;}\n'
 for op in ('fm','fa','fs','fma','fms','fnms'):ref=ref.replace('spu_'+op+'(','bces_rz_'+op+'(')
 ref+='''int bces_batch_cpu(uint32_t pc,u128*r,uint8_t*ls,uint32_t*next,BCESGeometryExecution*execution){
 uint64_t fpsr;__asm__ volatile("mrs %0, fpsr":"=r"(fpsr));uint64_t old=bces_rz_begin();int okay=batch_cpu_body(pc,r,ls,next,execution);bces_rz_end(old);__asm__ volatile("msr fpsr, %0"::"r"(fpsr):"memory");return okay;
}
#undef SK_READ
#undef SK_WRITE
'''
 planner='''typedef struct PlanState {BCESBatchPlan*p;unsigned iteration,write_index;uint32_t hash;int valid;} PlanState;
static void plan_read(PlanState*s,uint32_t address,uint32_t stamp){address&=0x3fff0;s->p->read_pages|=1ull<<(address>>12);unsigned q=address>>4;if(s->p->read_max[q]<stamp)s->p->read_max[q]=stamp;s->hash=(s->hash^address^stamp)*16777619u;}
static u128 plan_load(PlanState*s,const uint8_t*ls,uint32_t a,uint32_t stamp){plan_read(s,a,stamp);return batch_read(ls,a);}
static void plan_write(PlanState*s,uint32_t address,uint32_t stamp){
 address&=0x3fff0;unsigned q=address>>4;if(s->p->write_first[q]>stamp)s->p->write_first[q]=stamp;s->hash=(s->hash^address^stamp^0x80000000u)*16777619u;
 if(s->write_index>=s->p->writes_per_iteration){s->valid=0;return;}s->p->addresses[s->iteration*s->p->writes_per_iteration+s->write_index++]=address;
}
#define SK_READ(a) plan_load(s,read_ls,a,order*512+sequence)
#define PLAN_READ(a) plan_read(s,a,order*512+sequence)
#define SK_WRITE(a,v) plan_write(s,a,order*512+sequence)
'''+skip_a650()+iteration(plan=True)+'''
int bces_batch_plan(uint32_t pc,const u128*seed,const uint8_t*ls,BCESBatchPlan*p){
 p->pc=pc;p->rejection=0;p->iterations=bces_batch_count(pc,seed);p->read_pages=0;
 if(!p->iterations){p->rejection=1;return 0;}switch(pc){
'''
 for pc,d in descriptors.items():planner+=f'case 0x{pc:X}:p->writes_per_iteration={d["writes"]};break;'
 planner+='''default:return 0;}
 memset(p->read_max,0,sizeof p->read_max);memset(p->write_first,0xff,sizeof p->write_first);
 u128 state22=seed[22],state24=seed[24],state31=seed[31];unsigned cursor=0;
 for(unsigned i=0;i<p->iterations;i++){
 if(pc==0xA650){unsigned skip=i>3?i-3:0;while(cursor<skip){state22=spu_a(state22,state31);state31=spu_shufb(state31,state31,seed[69]);state24=spu_ai(state24,64);cursor++;}p->cull_states[i*3]=state22;p->cull_states[i*3+1]=state24;p->cull_states[i*3+2]=state31;}
 u128 r[128];memcpy(r,seed,2048);PlanState s={.p=p,.iteration=i,.hash=2166136261u,.valid=1};
 if(!batch_iteration(pc,r,i,ls,&s)||!s.valid||s.write_index!=p->writes_per_iteration){p->rejection=2;p->address=i;return 0;}p->hashes[i]=s.hash;}
 unsigned total=p->iterations*p->writes_per_iteration;
 for(unsigned i=0;i<total;i++){unsigned q=p->addresses[i]>>4;if(p->read_max[q]>p->write_first[q]){p->rejection=3;p->address=q*16;p->read_stamp=p->read_max[q];p->write_stamp=p->write_first[q];return 0;}}
 return 1;
}
'''
 tailcode='''
#undef SK_READ
#undef SK_WRITE
#define SK_READ(a) batch_read(read_ls,a)
#define SK_WRITE(a,v) ((void)0)
'''+iteration(tail=True)+'''
int bces_batch_tail(const BCESBatchPlan*p,const u128*seed,const uint8_t*ls,u128*r){
 memcpy(r,seed,2048);uint64_t fpsr;__asm__ volatile("mrs %0, fpsr":"=r"(fpsr));uint64_t old=bces_rz_begin();
 int okay=batch_tail_iteration(p->pc,r,p->iterations-1,ls,p);bces_rz_end(old);__asm__ volatile("msr fpsr, %0"::"r"(fpsr):"memory");return okay;
}
'''
 for op in ('fm','fa','fs','fma','fms','fnms'):tailcode=tailcode.replace('spu_'+op+'(','bces_rz_'+op+'(')
 put(out/'geometry_batches.c',common+count+finish+ref+planner+tailcode)
 # GPU math uses the new exact 64-bit arithmetic, not the large 128-bit replay.
 helpers=set(re.findall(r'\b(spu_\w+)\(', '\n'.join('\n'.join(d['ops']+d['slice'])+d['setup'] for d in descriptors.values())))|{'spu_zero','spu_a','spu_shufb'}
 msl='''#include <metal_stdlib>
using namespace metal;
union u128 {uint _u32[4];int _s32[4];ushort _u16[8];short _s16[8];uchar _u8[16];int8_t _s8[16];ulong _u64[2];long _s64[2];float _f32[4];};
struct BCESBatchWrite {uint address,pad[3];u128 value;};
'''+(ROOT/'src/platform/GeometryRZ64.h').read_text()+'\n'
 runtime=(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu/spu_helpers.h').read_text()
 for old,new,n in [('spu_frest_fraction_lut','bces_frest',32),('spu_frsqest_fraction_lut','bces_frsqrt',64)]:
  body=re.search(r'static const uint32_t '+old+r'\['+str(n)+r'\] = (\{.*?\});',runtime,re.S)[1];msl+=f'constant uint {new}[{n}]={body};\n'
 msl+=scalar_helpers(helpers,math64=True)+'''
inline u128 batch_read(device const uchar*ls,uint a){a&=0x3fff0;u128 r;for(uint lane=0;lane<4;lane++)r._u32[lane]=(uint(ls[a+4*lane])<<24)|(uint(ls[a+4*lane+1])<<16)|(uint(ls[a+4*lane+2])<<8)|ls[a+4*lane+3];return r;}
inline u128 batch_load(device const uchar*ls,uint a,uint stamp,thread uint&hash,bool emit){if(emit)hash=(hash^(a&0x3fff0)^stamp)*16777619u;return batch_read(ls,a);}
inline void batch_store(device BCESBatchWrite*outputs,uint a,u128 v,uint stamp,thread uint&hash,thread uint&wi,bool emit){if(emit){outputs[wi].address=a&0x3fff0;outputs[wi].value=v;hash=(hash^(a&0x3fff0)^stamp^0x80000000u)*16777619u;wi++;}}
#define SK_READ(a) batch_load(read_ls,a,order*512+sequence,hash,emit)
#define SK_WRITE(a,v) batch_store(outputs,a,v,order*512+sequence,hash,wi,emit)
'''+'\ninline void batch_hash_read(uint a,uint stamp,thread uint&hash){hash=(hash^(a&0x3fff0)^stamp)*16777619u;}\n'+specialized_kernels(descriptors)
 msl+='''
kernel void geometry_math_probe(device const uint*input [[buffer(0)]],device uint*out [[buffer(1)]],constant uint&n [[buffer(2)]],uint i [[thread_position_in_grid]]){
 if(i>=n)return;uint x=input[3*i],y=input[3*i+1],z=input[3*i+2];
 out[6*i]=g_fast_add(x,y);out[6*i+1]=g_fast_add(x,y^0x80000000u);out[6*i+2]=g_fast_mul(x,y);
 out[6*i+3]=g_fast_fma(x,y,z);out[6*i+4]=g_fast_fma(x,y,z^0x80000000u);out[6*i+5]=g_fast_fma(x^0x80000000u,y,z);
 if(!i)out[6*n]=as_type<uint>(as_type<float>(x)+as_type<float>(y));
}
'''
 msl=msl.replace('inline u128 spu_','__attribute__((always_inline)) inline u128 spu_')
 put(out/'geometry_batches.metal',msl)
 put(out/'geometry_batches_msl.inc','static const char* bces_geometry_batches_msl=\n'+''.join(json.dumps(l+'\n')+'\n' for l in msl.splitlines())+';\n')
 print('Prepared sparse journaled batches:',','.join(hex(pc) for pc in descriptors));return out
if __name__=='__main__':prepare()
