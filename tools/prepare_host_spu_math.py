#!/usr/bin/env python3
"""Mac-only pure-block experiment; preserve the pinned module and its O2 object."""
import hashlib,json,re,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODULE='jobmod_d0d15ec83992_ea2a0'
# Audited integer/LS helpers, plus the six replaced single operations. No DMA,
# channels, external calls, scheduling, interrupts, double arithmetic or drains.
ALLOWED=set('ls_read128 shufb ori fma selb ls_write128 a shlqbyi shlqby rotqbyi ai fm rotm cgt cflts sfi and andi shli rotqby fa fsmbi fi cuflt shl il frsqest fs cfltu rotqmbyi gbb clz csflt rotqmby mpya cgti andbi ilhu fsmb roti rotqmbybi ila rotqmbi iohl ceq ceqb fcgt clgt cwd ilh ceqbi cbd rotma xor fnms fms ceqi xsbh orbi sf ah rotmai xorbi frest gbh clgti cntb gb or mpyui rotmi ahi andhi'.split())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def derive(source,promote=False):
 selected=[];replacements=[]
 for match in re.finditer(r'void (\w+)\(spu_context\* ctx\) \{(.*?)\n\}',source,re.S):
  name,body=match.groups()
  if not re.search(r'spu_f(?:a|s|m|ma|ms|nms)\(',body):continue
  calls=set(re.findall(r'\b(\w+)\s*\(',re.sub(r'/\*.*?\*/','',body,flags=re.S)))-{'if','while','for','switch','return','sizeof'}
  if calls-{'spu_'+s for s in ALLOWED}-{'SPU_RET'}:continue
  assert not re.search(r'\bSPU_(?!RET\b)\w+|\blongjmp\b',body)
  assert set(re.findall(r'ctx->(\w+)',body))<={'pc','gpr'}
  index=len(selected);assert index<64
  ref=name+'_math_reference';fast=name+'_math_arm64'
  original=match.group(0).replace('void '+name+'(', 'static __attribute__((noinline)) void '+ref+'(',1)
  b=body
  for op in ('fa','fs','fm','fma','fms','fnms'):b=b.replace('spu_'+op+'(','bces_rz_'+op+'(')
  for op in ('cflts','cfltu'):b=b.replace('spu_'+op+'(','spu_'+op+'_exact(')
  locals_init='';flush=''
  if promote:
   used=sorted(set(map(int,re.findall(r'ctx->gpr\[(\d+)\]',b))))
   writes=sorted(set(map(int,re.findall(r'ctx->gpr\[(\d+)\](?:\._\w+\[[^\]]+\])?\s*=(?!=)',b))))
   assert used and writes
   locals_init='\n'.join(f'u128 r{n}=ctx->gpr[{n}];' for n in used)
   flush=' '.join(f'ctx->gpr[{n}]=r{n};' for n in writes)
   b=re.sub(r'ctx->gpr\[(\d+)\]',lambda m:'r'+m.group(1),b)
   assert 'ctx->gpr[' not in b
  restore=flush+' bces_rz_end(saved_control); __asm__ volatile("msr fpsr, %0"::"r"(saved_status):"memory");'
  b=b.replace('return;',restore+' return;').replace('SPU_RET(ctx);',restore+' SPU_RET(ctx);')
  accelerated=f'''static __attribute__((noinline)) void {fast}(spu_context* ctx) {{
 uint64_t saved_status;__asm__ volatile("mrs %0, fpsr":"=r"(saved_status));
 uint64_t saved_control=bces_rz_begin();
 {locals_init}
 {b}
 {restore}
}}
'''
  wrapper=f'''void {name}(spu_context* ctx) {{
 unsigned mode=bces_host_math_mode();
 if(!mode){{bces_host_math_note(0|((ctx->spu_id&15u)<<8));{ref}(ctx);return;}}
 uintptr_t local_store=(uintptr_t)ctx->ls,register_file=(uintptr_t)ctx->gpr;
 if(local_store>UINTPTR_MAX-SPU_LS_SIZE || (local_store<register_file+sizeof ctx->gpr && register_file<local_store+SPU_LS_SIZE)){{bces_host_math_note(4|((ctx->spu_id&15u)<<8));{ref}(ctx);return;}}
 uint64_t control;__asm__ volatile("mrs %0, fpcr":"=r"(control));
 if((control&~((1ull<<24)|(1ull<<25)))||g_spu_ls_dbg){{bces_host_math_note(4|((ctx->spu_id&15u)<<8));{ref}(ctx);return;}}
 if(mode==2){{
  spu_context* shadow=malloc(sizeof *shadow);uint8_t* ls=malloc(SPU_LS_SIZE);
  if(!shadow||!ls){{free(shadow);free(ls);bces_host_math_note(4|((ctx->spu_id&15u)<<8));{ref}(ctx);return;}}
  memcpy(shadow,ctx,sizeof *shadow);memcpy(ls,ctx->ls,SPU_LS_SIZE);shadow->ls=ls;
  {ref}(shadow);{fast}(ctx);
  int equal=!memcmp(shadow->gpr,ctx->gpr,sizeof ctx->gpr)&&shadow->pc==ctx->pc&&shadow->tramp_fn==ctx->tramp_fn&&!memcmp(ls,ctx->ls,SPU_LS_SIZE);
  if(!equal){{memcpy(ctx->gpr,shadow->gpr,sizeof ctx->gpr);ctx->pc=shadow->pc;ctx->tramp_fn=shadow->tramp_fn;memcpy(ctx->ls,ls,SPU_LS_SIZE);}}
  bces_host_math_result({index},equal);free(ls);free(shadow);return;
 }}
 bces_host_math_note(1|((ctx->spu_id&15u)<<8));{fast}(ctx);
}}
'''
  replacements.append((match.start(),match.end(),original+'\n'+accelerated+wrapper));selected.append(dict(index=index,name=name,ops=len(re.findall(r'spu_f(?:a|s|m|ma|ms|nms)\(',body))))
 for start,end,text in reversed(replacements):source=source[:start]+text+source[end:]
 return '#include "BCESSpuRZ.h"\n#include "HostSpuMath.h"\n'+source,selected

def prepare(output,promote=False):
 report=json.loads((ROOT/'out/bces-support-compile-macosx-spu-O2.json').read_text());unit,=[u for u in report['units'] if Path(u['source']).parent.name==MODULE]
 assert sha(unit['source'])==unit['sha256'] and sha(unit['object'])==unit['object_sha256']
 text,selected=derive(Path(unit['source']).read_text(),promote);assert len(selected)==46
 output.mkdir(parents=True,exist_ok=True);p=output/'host_spu_math.c'
 if not p.exists() or p.read_text()!=text:p.write_text(text)
 (output/'host-spu-math.json').write_text(json.dumps(dict(source=unit['source'],sha256=unit['sha256'],selected=selected,local_registers=promote,default_mode=0,device_performance_claim=False),indent=2)+'\n')
 return Path(unit['object']).name
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--local-registers',action='store_true');a=p.parse_args();prepare(ROOT/'build/bces01229/host-math-test',a.local_registers)
