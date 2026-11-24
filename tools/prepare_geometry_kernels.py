#!/usr/bin/env python3
"""Generate bounded whole-function ARM64/Metal prototypes from locked pure IR."""
from pathlib import Path
import json,re,subprocess
from skinning_ir import ROOT,program,switch
import geometry_parallel as parallel

def put(path,text):
    if not path.exists() or path.read_text()!=text:path.write_text(text)

def cpu_source(cases,name,parallel_sim=False,execution=False):
    hook="if ("+" || ".join(f"pc==0x{p:X}" for p in parallel.parts())+") {if(!geometry_parallel_sim(&pc,r,ls,dirty))return 0;continue;}" if parallel_sim else ""
    extra=',BCESGeometryExecution* execution' if execution else ''
    local='' if execution else 'BCESGeometryExecution* execution=NULL;'
    if execution:
        pcs=(0xD800,0xD5B0,0xDA28,0xDCE0,0xDF20,0x7030,0xA650)
        ids=''.join(f'case 0x{pc:X}:batch_index={i};break;' for i,pc in enumerate(pcs))
        hook=f'''if(execution&&execution->batch){{unsigned batch_index=64;switch(pc){{{ids}default:break;}}
 if(batch_index<64&&!(execution->declined&(1ull<<batch_index))){{
 uint64_t mode;__asm__ volatile("mrs %0, fpcr":"=r"(mode));bces_rz_end(mode&~(3ull<<22));
 int accepted=execution->batch(execution,&pc,r,ls);bces_rz_end(mode);
 if(accepted)continue;execution->declined|=1ull<<batch_index;
 }} }}'''
    return f'''int {name}(u128* restrict r,uint8_t* restrict ls,uint32_t ret,uint32_t* out_pc,uint32_t* restrict dirty{extra}) {{
 {local}const uint8_t* read_ls=ls;uint32_t pc={hex(next(iter(cases)))};
 for(uint32_t steps=0;steps<200000;++steps){{
  if(pc==ret){{*out_pc=pc;return 1;}}
  {hook}
  switch(pc){{
{switch(cases)}
  default:return 0;}}
 }}return 0;
}}
'''

def scalar_helpers(names,math64=False):
    sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'
    source=subprocess.check_output(['clang','-E','-P','-x','c','-DSPU_SCALAR_HELPERS','-DSPU_SCALAR_INT','-I'+str(sdk),str(sdk/'spu_helpers.h')],text=True)
    defs={}
    for m in re.finditer(r'static\s+inline\s+(\w+)\s+(spu_\w+)\s*\(([^;{}]*?)\)\s*\{',source):
        end=m.end();depth=1
        while depth:
            depth+=(source[end]=='{')-(source[end]=='}');end+=1
        defs[m[2]]='inline '+m[1]+' '+m[2]+'('+m[3]+')'+source[m.end()-1:end]
    special={
      'spu_zero':'inline u128 spu_zero(){u128 r;for(uint i=0;i<4;i++)r._u32[i]=0;return r;}',
      'spu_cuflt':'inline u128 spu_cuflt(u128 a,int imm){u128 r;for(uint i=0;i<4;i++)r._u32[i]=bpack(0,b128(a._u32[i]),-(155-(imm&255)));return r;}',
      'spu_cflts':'''inline u128 spu_cflts(u128 a,int imm){u128 r;for(uint i=0;i<4;i++){uint x=a._u32[i],e=(x>>23)&255u,m=(x&0x7fffffu)|0x800000u;int shift=int(e)-150+173-(imm&255);bool neg=(x>>31)!=0;uint v;if(!e)v=0;else if(shift>=8)v=neg?0x80000000u:0x7fffffffu;else {uint mag=shift>=0?m<<uint(shift):shift<=-24?0:m>>uint(-shift);v=neg?0u-mag:mag;}r._u32[i]=v;}return r;}''',
      'spu_fi':'inline u128 spu_fi(u128 a,u128 b){u128 r;for(uint i=0;i<4;i++)r._u32[i]=bfi(a._u32[i],b._u32[i]);return r;}',
      'spu_frsqest':'inline u128 spu_frsqest(u128 a){u128 r;for(uint i=0;i<4;i++){uint x=a._u32[i],e=(x>>23)&255;r._u32[i]=((e==0?255:190-(e+1)/2)<<23)|(bces_frsqrt[(x>>18)&63]&0x7fffffu);}return r;}',
      'spu_frest':'inline u128 spu_frest(u128 a){u128 r;for(uint i=0;i<4;i++){uint x=a._u32[i],e=(x>>23)&255;r._u32[i]=(x&0x80000000u)|((e==0?255:e>=253?0:253-e)<<23)|(bces_frest[(x>>18)&31]&0x7fffffu);}return r;}',
    }
    for op,expr in {'fm':'bmul(x,y)','fma':'bfma(x,y,z)','fms':'bfma(x,y,z^0x80000000u)','fnms':'bfma(x^0x80000000u,y,z)','fa':'badd(x,y)','fs':'badd(x,y^0x80000000u)'}.items():
        third=',u128 c' if op in ('fma','fms','fnms') else ''
        z='c._u32[i]' if third else '0'
        special['spu_'+op]=f'inline u128 spu_{op}(u128 a,u128 b{third}){{u128 r;for(uint i=0;i<4;i++){{uint x=a._u32[i],y=b._u32[i],z={z};r._u32[i]={expr};}}return r;}}'
    if math64:
        special['spu_cuflt']='inline u128 spu_cuflt(u128 a,int imm){u128 r;for(uint i=0;i<4;i++)r._u32[i]=g_pack(0,(ulong)a._u32[i],-(155-(imm&255)));return r;}'
        special['spu_fi']='inline u128 spu_fi(u128 a,u128 b){u128 r;for(uint i=0;i<4;i++)r._u32[i]=g_fi(a._u32[i],b._u32[i]);return r;}'
        for name in ('spu_fm','spu_fa','spu_fs','spu_fma','spu_fms','spu_fnms'):
            special[name]=special[name].replace('bmul(','g_fast_mul(').replace('bfma(','g_fast_fma(').replace('badd(','g_fast_add(')
    emitted=set();ordered=[]
    def emit(name):
        if name in emitted:return
        assert name in special or name in defs,'Missing scalar helper '+name
        code=special.get(name,defs.get(name))
        if name not in special and name+'_ref' in defs:
            code=defs[name+'_ref'].replace(name+'_ref(',name+'(',1)
        emitted.add(name)
        for dep in set(re.findall(r'\b(spu_\w+)\(',code))-{name}:emit(dep)
        code=code.replace('__builtin_popcount','popcount').replace('__builtin_clz','clz')
        assert not any(x in code for x in ('memcpy','memset','__uint128','vld1','vst1')),code
        ordered.append(code)
    for name in sorted(names):emit(name)
    return '\n'.join(ordered)

def prepare():
    out=ROOT/'build/bces01229/skinning';out.mkdir(exist_ok=True)
    programs={root:program(root) for root in (0xD0A8,0xA798)}
    # Preserve explicit entry rather than sorted first helper block.
    for root,cases in programs.items():programs[root]={root:cases[root],**{p:c for p,c in cases.items() if p!=root}}
    cpu='''#include "spu_context.h"
#include "spu_helpers.h"
#include "GeometryExecution.h"
#include "BCESSpuRZ.h"
static inline u128 geometry_read(const uint8_t* ls,uint32_t a){u128 r;a&=0x3fff0;for(unsigned i=0;i<4;i++){uint32_t x;memcpy(&x,ls+a+4*i,4);r._u32[i]=__builtin_bswap32(x);}return r;}
static inline void geometry_write(uint8_t*ls,uint32_t a,u128 r,uint32_t*dirty){a&=0x3fff0;for(unsigned i=0;i<4;i++){uint32_t x=__builtin_bswap32(r._u32[i]);memcpy(ls+a+4*i,&x,4);}dirty[a>>9]|=1u<<((a>>4)&31);}
#define SK_READ(a) geometry_read(read_ls,a)
#define SK_WRITE(a,v) bces_geometry_write(ls,a,v,dirty,execution)
'''
    execute=cpu
    for root,cases in programs.items():cpu+=cpu_source(cases,'bces_geometry_'+('skin' if root==0xD0A8 else 'cull')+'_flat')
    cpu+='#include "BCESSpuRZ.h"\n'
    for root,cases in programs.items():
        name='bces_geometry_'+('skin' if root==0xD0A8 else 'cull')+'_arm64'
        body=cpu_source(cases,name+'_body')
        for op in ('fm','fa','fs','fma','fms','fnms'):body=body.replace('spu_'+op+'(','bces_rz_'+op+'(')
        body=body.replace('int '+name+'_body','static __attribute__((noinline)) int '+name+'_body',1)
        cpu+=body+f'''int {name}(u128*r,uint8_t*ls,uint32_t ret,uint32_t*pc,uint32_t*dirty){{
 uint64_t fpsr;__asm__ volatile("mrs %0, fpsr":"=r"(fpsr));uint64_t old=bces_rz_begin();
 int result={name}_body(r,ls,ret,pc,dirty);bces_rz_end(old);__asm__ volatile("msr fpsr, %0"::"r"(fpsr):"memory");return result;
}}
'''
    for root,cases in programs.items():
        name='bces_geometry_'+('skin' if root==0xD0A8 else 'cull')+'_execute'
        body=cpu_source(cases,name+'_body',execution=True).replace('uint32_t* restrict dirty,BCESGeometryExecution*','uint32_t* dirty,BCESGeometryExecution*')
        for op in ('fm','fa','fs','fma','fms','fnms'):body=body.replace('spu_'+op+'(','bces_rz_'+op+'(')
        body=body.replace('int '+name+'_body','static __attribute__((noinline)) int '+name+'_body',1)
        execute+=body+f'''int {name}(u128*r,uint8_t*ls,uint32_t ret,uint32_t*pc,uint32_t*dirty,BCESGeometryExecution*execution){{
 uint64_t fpsr;__asm__ volatile("mrs %0, fpsr":"=r"(fpsr));uint64_t old=bces_rz_begin();
 int result={name}_body(r,ls,ret,pc,dirty,execution);bces_rz_end(old);__asm__ volatile("msr fpsr, %0"::"r"(fpsr):"memory");return result;
}}
'''
    put(out/'geometry_execute.c',execute)
    cpu+='\n#ifdef BCES_GEOMETRY_PARALLEL_TEST\n#undef SK_WRITE\n#define SK_WRITE(a,v) geometry_write(ls,a,v,dirty)\n'+parallel.cpu()+cpu_source(programs[0xD0A8],'bces_geometry_skin_parallel',True)+'\n#endif\n'
    put(out/'geometry_flat.c',cpu)
    helpers=set(re.findall(r'\b(spu_\w+)\(', '\n'.join(switch(c) for c in programs.values())))
    runtime=(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu/spu_helpers.h').read_text()
    rz=(ROOT/'src/platform/LightingRZ.metal').read_text().split('struct BGrid')[0]
    tables=[]
    for old,new,n in [('spu_frest_fraction_lut','bces_frest',32),('spu_frsqest_fraction_lut','bces_frsqrt',64)]:
        body=re.search(r'static const uint32_t '+old+r'\['+str(n)+r'\] = (\{.*?\});',runtime,re.S)[1];tables.append(f'constant uint {new}[{n}]={body};')
    rz=rz.replace('BCES_RZ_LUTS','\n'.join(tables))
    msl='''#include <metal_stdlib>
using namespace metal;
union u128 {uint _u32[4];int _s32[4];ushort _u16[8];short _s16[8];uchar _u8[16];int8_t _s8[16];ulong _u64[2];long _s64[2];float _f32[4];};
'''+rz+'\n'+scalar_helpers(helpers)+'''
inline u128 geometry_read(device const uchar* ls,uint a){u128 r;a&=0x3fff0;for(uint i=0;i<4;i++)r._u32[i]=(uint(ls[a+4*i])<<24)|(uint(ls[a+4*i+1])<<16)|(uint(ls[a+4*i+2])<<8)|ls[a+4*i+3];return r;}
inline void geometry_write(device uchar*ls,uint a,u128 r,device atomic_uint*dirty){a&=0x3fff0;for(uint i=0;i<4;i++){uint v=r._u32[i];for(uint b=0;b<4;b++)ls[a+4*i+b]=uchar(v>>(24-8*b));}atomic_fetch_or_explicit(dirty+(a>>9),1u<<((a>>4)&31),memory_order_relaxed);}
inline u128 geometry_read_traced(device const uchar*ls,uint a,device atomic_uint*reads,uint order){
 if(reads)atomic_fetch_max_explicit(reads+((a&0x3fff0)>>4),order,memory_order_relaxed);return geometry_read(ls,a);
}
inline void geometry_write_traced(device uchar*ls,uint a,u128 v,device atomic_uint*dirty,device atomic_uint*writes,uint order,device atomic_uint*hazard){
 if(writes){uint previous=atomic_fetch_min_explicit(writes+((a&0x3fff0)>>4),order,memory_order_relaxed);
 if(previous!=0xffffffffu&&previous/512!=order/512)atomic_fetch_or_explicit(hazard,1u,memory_order_relaxed);}

 geometry_write(ls,a,v,dirty);
}
#define SK_READ(a) geometry_read_traced(read_ls,a,reads,order*512+access_sequence)
#define SK_WRITE(a,v) geometry_write_traced(ls,a,v,dirty,writes,order*512+access_sequence,hazard)
'''
    for root,cases in programs.items():
        name='geometry_'+('skin' if root==0xD0A8 else 'cull')
        msl+=f'''kernel void {name}(device u128* registers [[buffer(0)]],device uchar*ls [[buffer(1)]],device atomic_uint*dirty [[buffer(2)]],device uint*control [[buffer(3)]],uint id [[thread_position_in_grid]]){{
 if(id)return;device atomic_uint*reads=nullptr;device atomic_uint*writes=nullptr;device atomic_uint*hazard=nullptr;uint order=0,access_sequence=0;device const uchar*read_ls=ls;u128 r[128];for(uint i=0;i<128;i++)r[i]=registers[i];uint pc=0x{root:X},ret=control[0],steps=0;control[1]=0;
 for(;steps<200000;steps++){{if(pc==ret){{control[1]=1;break;}}switch(pc){{
{switch(cases).replace('return 0;','control[1]=0;control[2]=pc;return;')}
 default:control[2]=pc;return;}}}}
 control[2]=pc;control[3]=steps;if(control[1])for(uint i=0;i<128;i++)registers[i]=r[i];
}}
'''
    msl+=parallel.metal(programs[0xD0A8],switch(programs[0xD0A8]))
    msl=msl.replace('steps<200000','steps<8192')
    put(out/'geometry.metal',msl)
    put(out/'geometry_msl.inc','static const char* bces_geometry_msl=\n'+''.join(json.dumps(line+'\n')+'\n' for line in msl.splitlines())+';\n')
    print(out)
    return out
if __name__=='__main__':prepare()
