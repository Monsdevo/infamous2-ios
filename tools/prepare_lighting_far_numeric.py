"""Extract actual compiled candidate guard and independent original weight math."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=ROOT/'build/bces01229/host-research-prepared/renderer-overlay/libs/video/rsx_metal_backend.m';s=p.read_text();a=s.index('"struct GLight {');b=s.index('/* inFAMOUS 2\'s SSAO job',a);msl=''.join(ast.literal_eval(l.strip()) for l in s[a:b].splitlines() if l.startswith('"'))
 struct=msl[msl.index('struct GLight {'):msl.index('};')+2]
 a=msl.index('fragment GLOut eng_light_fs_far(');body=msl[a:];a=body.index('        // Skip only');b=body.index('        float d = length(Lv);',a);guard=body[a:b].replace('continue;','return true;')+'return false;\n'
 body=msl[msl.index('fragment GLOut eng_light_fs('):];a=body.index('float d = length(Lv);');b=body.index('        if (w <= 0.0) continue;',a);oracle=body[a:b].replace('float d = length(Lv);','d = length(Lv);')+'return w;\n'
 kernel=r'''
uint mixbits(uint x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;x^=x>>16;return x;}
kernel void check_far(device atomic_uint* stats [[buffer(0)]],uint id [[thread_position_in_grid]],uint lane [[thread_index_in_simdgroup]]) {
 uint h=mixbits(id+52700u),h2=mixbits(h),h3=mixbits(h2),h4=mixbits(h3);uint cls=id&3u;
 GLight L;L.pos_type=float4(0,0,0,(h&1u)?1.0:2.0);L.col_inner=float4(1,1,1,0);
 L.dir=float4(float3(float(h&1023u)/512-1,float(h2&1023u)/512-1,float(h3&1023u)/512-1),0);
 float radius=exp2(float(int(h%101u)-50))*(1+float(h2&1023u)/1024);
 L.oacbn=float4(radius,-2.5,.5,0);L.col_inner.w=radius*.5;
 float3 Lv;
 if(cls==0){Lv=as_type<float3>(uint3(h,h2,h3));L.oacbn.x=as_type<float>(h4&0x7fffffffu);L.col_inner.w=as_type<float>(mixbits(h4));}
 else if(cls==1){float delta=float(int(h3%1025u)-512)*1.1920928955078125e-7f;Lv=float3(radius*(1+delta),0,0);}
 else if(cls==2){Lv=float3(radius*4,radius*.25,0);L.col_inner.w=radius*(1+((h4&1u)?1:-1)*1.1920928955078125e-7f);}
 else {
  L.pos_type.w=2;L.oacbn=float4(10,-2.5,.5,0);L.col_inner.w=0;Lv=float3(1000,2000,1000);
  switch((id>>2)&7u){case0:L.oacbn.y=as_type<float>(0x7fc00000u);break;
   case1:L.oacbn.y=INFINITY;break;case2:L.dir.x=as_type<float>(0x7fc00000u);break;
   case3:L.dir.z=1e30;break;case4:L.col_inner.w=as_type<float>(0x7fc00000u);break;
   case5:L.col_inner.w=-INFINITY;break;case6:L.oacbn.x=-1;break;case7:L.oacbn.w=INFINITY;break;}
 }
 float3 rgb=float3(h&255u,(h2>>8)&255u,h3&255u);float3 N=normalize(rgb*(2.0/255.0)-1.0);
 bool took=actual_guard(Lv,L);bool bad=false;
 if(took){float d;float w=original_weight(Lv,L,N,d);bad=!(d>=L.oacbn.x)||!(w<=0.0);}
 for(uint k=0;k<4;k++){uint n=simd_sum(uint(took&&cls==k));if(lane==0&&n)atomic_fetch_add_explicit(&stats[k],n,memory_order_relaxed);}
 if(bad){atomic_fetch_add_explicit(&stats[4+cls],1u,memory_order_relaxed);atomic_fetch_min_explicit(&stats[8],id,memory_order_relaxed);}
}
'''.replace('case0:','case 0:').replace('case1:','case 1:').replace('case2:','case 2:').replace('case3:','case 3:').replace('case4:','case 4:').replace('case5:','case 5:').replace('case6:','case 6:').replace('case7:','case 7:')
 out=ROOT/'build/bces01229/lighting-far-test/numeric.metal';out.write_text('#include <metal_stdlib>\nusing namespace metal;\n'+struct+'\nbool actual_guard(float3 Lv,GLight L){\n'+guard+'}\nfloat original_weight(float3 Lv,GLight L,float3 N,thread float& d){\n'+oracle+'}\n'+kernel);print(out)
if __name__=='__main__':main()
