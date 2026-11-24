"""Independent skinning loop kernels with verified backward live-in slices."""
import re
from skinning_ir import program

LOOPS={
 0xD800:([0xD800,0xD808,0xD8A8],['r[39]=spu_ori(r[85],0);','r[41]=spu_ai(r[85],32);'],{41:32,44:96,45:-2,46:32,47:16},45,2,'r[43]=spu_xsbh(r[86]); return r[43]._u16[0]?0xD698:0xD9E8;'),
 0xD5B0:([0xD5B0],['r[41]=spu_ai(r[85],32);'],{19:-2,20:96,21:2,22:32,41:32},19,2,'r[43]=spu_xsbh(r[86]); return r[43]._u16[0]?0xD698:0xD9E8;'),
 0xDA28:([0xDA28],[],{49:192,50:-4,88:64},50,4,'return 0xD698;'),
 0xDCE0:([0xDCE0],[],{8:-4,33:64,42:192,64:64},8,4,'return 0xD71C;'),
 0xDF20:([0xDF20],['r[33]=spu_ori(r[64],0);'],{33:64,42:192,62:-4,64:64,65:64,70:64},62,4,'return 0xD71C;')}

def parts():
 cases=program(0xD0A8);result={}
 for pc,(blocks,epilogue,affine,counter,step,exitcode) in LOOPS.items():
  ops=[]
  for b in blocks:
   for line in cases[b].splitlines():
    if line.startswith('if ('):break
    if re.match(r'r\[\d+\] = |SK_WRITE',line.strip()):ops.append(line.strip())
  written=set();live=set()
  for line in ops+epilogue:
   m=re.match(r'r\[(\d+)\]',line);target=int(m[1]) if m else None
   rhs=line.split('=',1)[1] if target is not None else line
   live|={int(x) for x in re.findall(r'r\[(\d+)\]',rhs)}-written
   if target is not None:written.add(target)
  needed=live.copy();slice=[]
  for line in reversed(ops+epilogue):
   m=re.match(r'r\[(\d+)\]',line)
   if m and int(m[1]) in needed:
    needed.remove(int(m[1]));needed|={int(x) for x in re.findall(r'r\[(\d+)\]',line.split('=',1)[1])};slice.append(line)
  assert not ((needed&written)-set(affine)),(hex(pc),needed&written)
  assert all('spu_fma(' not in x and 'spu_fms(' not in x for x in slice)
  setup='\n'.join(f'{{u128 delta;for(uint32_t lane=0;lane<4;lane++)delta._u32[lane]=(uint32_t)((int32_t)prev*({stride}));r[{r}]=spu_a(r[{r}],delta);}}' for r,stride in affine.items())
  result[pc]={'ops':ops,'slice':list(reversed(slice)),'setup':setup,'counter':counter,'step':step,'exit':exitcode}
 # The normalizer is a three-iteration software pipeline, not a reduction.
 # Backward dependency closure proves its carried data is entirely reloaded
 # after three iterations; only the two affine byte offsets remain live.
 ops=[line.strip() for line in cases[0x7030].splitlines() if re.match(r'r\[\d+\] = |SK_WRITE',line.strip())]
 written=set();live=set()
 for line in ops:
  m=re.match(r'r\[(\d+)\]',line);target=int(m[1]) if m else None
  live|={int(x) for x in re.findall(r'r\[(\d+)\]',line.split('=',1)[1] if target is not None else line)}-written
  if target is not None:written.add(target)
 needed=live.copy()
 for depth in range(3):
  for line in reversed(ops):
   m=re.match(r'r\[(\d+)\]',line)
   if m and int(m[1]) in needed:
    needed.remove(int(m[1]));needed|={int(x) for x in re.findall(r'r\[(\d+)\]',line.split('=',1)[1])}
 assert needed&written <= {21,34},needed&written
 result[0x7030]={'ops':ops,'slice':[],'setup':'','counter':34,'step':128,'exit':'return r[0]._u32[0];','warm':3}
 return result

def iteration(metal=False):
 signature='inline uint geometry_parallel_iteration(uint pc,thread u128*r,uint i,device const uchar*read_ls,device uchar*ls,device atomic_uint*dirty,device atomic_uint*reads,device atomic_uint*writes,device atomic_uint*hazard)' if metal else 'static uint32_t geometry_parallel_iteration(uint32_t pc,u128*r,uint32_t i,const uint8_t*read_ls,uint8_t*ls,uint32_t*dirty)'
 code=signature+('{uint order=i,access_sequence=0;switch(pc){\n' if metal else '{switch(pc){\n')
 for pc,p in parts().items():
  assert len(p['ops'])<512
  memory_ops=[line for line in p['ops'] if 'SK_READ(' in line or 'SK_WRITE(' in line]
  assert len(memory_ops)==len(set(memory_ops)),hex(pc)
  def emit(ops):
   return '\n'.join((f'access_sequence={p["ops"].index(line)+1};' if metal and line in p['ops'] else '')+line for line in ops)
  if p.get('warm'):
   setup=''.join(f'{{u128 delta;for(uint32_t lane=0;lane<4;lane++)delta._u32[lane]=128u*skip;r[{r}]=spu_a(r[{r}],delta);}}' for r in (21,34))
   warm=emit([line for line in p['ops'] if not line.startswith('SK_WRITE')])
   code+=f'case 0x{pc:X}:{{uint32_t warm=i<3?i:3,skip=i-warm;{setup}for(uint32_t cycle=0;cycle<warm;cycle++){{'+('order=skip+cycle;' if metal else '')+f'\n{warm}\n}}\n'+('order=i;\n' if metal else '')+emit(p['ops'])+'\n'+p['exit']+'}\n'
   continue
  code+=f'case 0x{pc:X}:{{if(i){{uint32_t prev=i-1;'+('order=i-1;' if metal else '')+f'\n{p["setup"]}\n'+ emit(p['slice'])+'\n}\n'+('order=i;\n' if metal else '')+emit(p['ops'])+'\n'+p['exit']+'}\n'
 return code+'default:return 0;}}\n'

def count_code():
 return 'switch(pc){'+''.join(f'case 0x{pc:X}:n={'0u-' if pc==0x7030 else ''}r[{p["counter"]}]._u32[0];if(n%{p["step"]})return 0;n/={p["step"]};break;' for pc,p in parts().items())+'default:return 0;}'

def cpu():
 return iteration()+'''static int geometry_parallel_sim(uint32_t*out_pc,u128*registers,uint8_t*ls,uint32_t*dirty){
 uint32_t pc=*out_pc,n=0;u128*r=registers;
'''+count_code()+'''
 if(!n||n>8192)return 0;
 uint8_t*read_ls=malloc(0x40000);if(!read_ls)return 0;memcpy(read_ls,ls,0x40000);
 u128 seed[128],local[128];memcpy(seed,registers,2048);uint32_t next=0;
 for(uint32_t i=0;i<n;i++){memcpy(local,seed,2048);next=geometry_parallel_iteration(pc,local,i,read_ls,ls,dirty);}
 memcpy(registers,local,2048);*out_pc=next;free(read_ls);return 1;
}
'''

def metal(cases,switch_text):
 hook=' || '.join(f'pc==0x{p:X}' for p in parts())
 return iteration(True)+'''
kernel void geometry_skin_control(device u128*registers [[buffer(0)]],device uchar*ls [[buffer(1)]],device atomic_uint*dirty [[buffer(2)]],device uint*control [[buffer(3)]],device const u128*completed [[buffer(4)]],uint id [[thread_position_in_grid]]){
 if(id||control[1]==1||control[1]==4)return;
 if(control[16]){control[1]=4;control[4]=0;control[5]=0;return;}
 u128 r[128];for(uint i=0;i<128;i++)r[i]=control[1]==3?completed[i]:registers[i];
 device atomic_uint*reads=nullptr;device atomic_uint*writes=nullptr;device atomic_uint*hazard=nullptr;uint order=0,access_sequence=0;
 device const uchar*read_ls=ls;uint pc=control[2],ret=control[0];
 control[1]=0;control[4]=0;control[5]=0;control[8]=1;control[9]=1;control[10]=1;control[12]=1;control[13]=1;control[14]=1;
 for(uint steps=0;steps<200000;steps++){
  if(pc==ret){control[1]=1;control[2]=pc;for(uint i=0;i<128;i++)registers[i]=r[i];return;}
  if('''+hook+'''){
    uint n=0;
'''+count_code().replace('return 0;','{control[1]=4;control[4]=0;control[5]=0;return;}')+'''
    if(!n||n>8192){control[1]=4;control[4]=0;control[5]=0;return;}
    control[1]=2;control[2]=pc;control[4]=pc;control[5]=n;control[8]=(n+63)/64;control[12]=256;
    for(uint i=0;i<128;i++)registers[i]=r[i];return;
  }
  switch(pc){
'''+switch_text.replace('return 0;','control[1]=4;control[4]=0;control[5]=0;control[2]=pc;return;')+'''
  default:control[1]=4;control[4]=0;control[5]=0;control[2]=pc;return;}
 }control[1]=4;control[4]=0;control[5]=0;
}
kernel void geometry_snapshot(device const uchar*ls [[buffer(1)]],device const uint*control [[buffer(3)]],device uchar*snapshot [[buffer(5)]],device atomic_uint*reads [[buffer(6)]],device atomic_uint*writes [[buffer(7)]],uint id [[thread_position_in_grid]]){
 if(!control[4]||id>=65536)return;if(id<16384){atomic_store_explicit(reads+id,0,memory_order_relaxed);atomic_store_explicit(writes+id,0xffffffffu,memory_order_relaxed);}device const uint*src=(device const uint*)ls;device uint*dst=(device uint*)snapshot;dst[id]=src[id];
}
kernel void geometry_skin_parallel(device const u128*seed [[buffer(0)]],device uchar*ls [[buffer(1)]],device atomic_uint*dirty [[buffer(2)]],device uint*control [[buffer(3)]],device u128*completed [[buffer(4)]],device const uchar*read_ls [[buffer(5)]],device atomic_uint*reads [[buffer(6)]],device atomic_uint*writes [[buffer(7)]],uint id [[thread_position_in_grid]]){
 uint n=control[5],pc=control[4];if(!pc||id>=n)return;u128 r[128];for(uint i=0;i<128;i++)r[i]=seed[i];
 uint next=geometry_parallel_iteration(pc,r,id,read_ls,ls,dirty,reads,writes,(device atomic_uint*)(control+16));
 if(id==n-1){for(uint i=0;i<128;i++)completed[i]=r[i];control[2]=next;control[1]=3;}
}
kernel void geometry_hazards(device uint*control [[buffer(3)]],device atomic_uint*reads [[buffer(6)]],device atomic_uint*writes [[buffer(7)]],uint id [[thread_position_in_grid]]){
 if(!control[4]||id>=16384)return;uint r=atomic_load_explicit(reads+id,memory_order_relaxed),w=atomic_load_explicit(writes+id,memory_order_relaxed);
 if(r&&w<r){atomic_fetch_or_explicit((device atomic_uint*)(control+16),1u,memory_order_relaxed);control[17]=control[4];control[18]=id;control[19]=r;control[20]=w;}
}
'''
