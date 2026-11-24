#pragma once
// Exact SPU single-precision semantics using bounded 64-bit significands.
// The low operand is floored for addition and ceiled for subtraction. A lost
// fraction cannot participate in close cancellation: the source significands
// have at most 48 bits and retain >=15 guard bits after normalization.
#ifdef __METAL_VERSION__
inline uint g_clz64(ulong x){return uint(clz(x));}
#else
#include <stdint.h>
typedef uint32_t uint;
typedef uint64_t ulong;
static inline uint g_clz64(ulong x){return (uint)__builtin_clzll(x);}
#endif
static inline uint g_pack(uint sign,ulong m,int power){
    if(!m)return 0;int k=63-(int)g_clz64(m),e=power+k+127;
    if(e<=0)return 0;if(e>255)return sign|0x7fffffffu;
    ulong v=k>23?m>>(k-23):m<<(23-k);
    return sign|((uint)e<<23)|((uint)v&0x7fffffu);
}
static inline uint g_sum(uint sa,ulong a,int ea,uint sb,ulong b,int eb){
    if(!a)return g_pack(sb,b,eb);if(!b)return g_pack(sa,a,ea);
    int ka=63-(int)g_clz64(a),kb=63-(int)g_clz64(b);
    int ta=ea+ka,tb=eb+kb;a<<=62-ka;b<<=62-kb;
    if(ta<tb){uint ts=sa;sa=sb;sb=ts;ulong tm=a;a=b;b=tm;int te=ta;ta=tb;tb=te;}
    uint gap=(uint)(ta-tb);ulong lo=gap>=64?0:b>>gap;
    bool lost=gap>=64?b!=0:gap?(b&((1ul<<gap)-1))!=0:false;
    if(sa==sb)return g_pack(sa,a+lo,ta-62);
    if(!gap&&a<b)return g_pack(sb,b-a,ta-62);
    return g_pack(sa,a-lo-(lost?1:0),ta-62);
}
static inline uint g_add(uint x,uint y){
    uint ex=(x>>23)&255,ey=(y>>23)&255;if(!ex)return ey?y:0;if(!ey)return x;
    return g_sum(x&0x80000000u,(x&0x7fffffu)|0x800000u,(int)ex-150,y&0x80000000u,(y&0x7fffffu)|0x800000u,(int)ey-150);
}
static inline uint g_mul(uint x,uint y){
    uint ex=(x>>23)&255,ey=(y>>23)&255;if(!ex||!ey)return 0;
    return g_pack((x^y)&0x80000000u,(ulong)((x&0x7fffffu)|0x800000u)*((y&0x7fffffu)|0x800000u),(int)ex+(int)ey-300);
}
static inline uint g_fma(uint x,uint y,uint z){
    uint ex=(x>>23)&255,ey=(y>>23)&255,ez=(z>>23)&255;
    if(!ex||!ey)return ez?z:0;
    ulong p=(ulong)((x&0x7fffffu)|0x800000u)*((y&0x7fffffu)|0x800000u);
    uint sign=(x^y)&0x80000000u;int power=(int)ex+(int)ey-300;
    if(!ez)return g_pack(sign,p,power);
    return g_sum(sign,p,power,z&0x80000000u,(z&0x7fffffu)|0x800000u,(int)ez-150);
}
static inline uint g_fi(uint a,uint b){
    uint e=(b>>23)&255;if(!e)return 0;
    ulong m=(((1ul<<13)|((b>>10)&0x1fffu))<<19)-(ulong)(b&0x3ffu)*(a&0x7ffffu);
    if(m<(1ul<<32)){m<<=1;if(!--e)return 0;}
    return (b&0x80000000u)|(e<<23)|((uint)(m>>9)&0x7fffffu);
}
#ifdef __METAL_VERSION__
// Precise IEEE/RNE operations only, in a range where all error terms stay
// normal. Other inputs retain the exact integer path above. Backend startup
// verifies native rounding and exact results before enabling these kernels.
#pragma clang fp contract(off)
#pragma clang fp reassociate(off)
static inline uint g_toward_zero(float result,float error){
 uint bits=as_type<uint>(result);if(!(bits&0x7fffffffu))return 0;
 if((result>0&&error<0)||(result<0&&error>0))bits--;
 return bits;
}
static inline float g_sum_error(float a,float b,float sum){
 float virtual_b=sum-a;float virtual_a=sum-virtual_b;
 return (a-virtual_a)+(b-virtual_b);
}
static inline uint g_fast_add(uint x,uint y){
 uint ex=(x>>23)&255,ey=(y>>23)&255;
 if(!ex)return ey?y:0;if(!ey)return x;
#if !defined(BCES_GEOMETRY_INTEGER_ONLY)
 if(ex>=64&&ex<=190&&ey>=64&&ey<=190){float a=as_type<float>(x),b=as_type<float>(y),s=a+b;return g_toward_zero(s,g_sum_error(a,b,s));}
#endif
 return g_add(x,y);
}
static inline uint g_fast_mul(uint x,uint y){
 uint ex=(x>>23)&255,ey=(y>>23)&255;if(!ex||!ey)return 0;
#if !defined(BCES_GEOMETRY_INTEGER_ONLY)
 int ep=int(ex)+int(ey)-127;
 if(ex<255&&ey<255&&ep>=64&&ep<=189){float a=as_type<float>(x),b=as_type<float>(y),p=a*b;return g_toward_zero(p,fma(a,b,-p));}
#endif
 return g_mul(x,y);
}
static inline uint g_fast_fma(uint x,uint y,uint z){
 uint ex=(x>>23)&255,ey=(y>>23)&255,ez=(z>>23)&255;
 if(!ex||!ey)return ez?z:0;if(!ez)return g_fast_mul(x,y);
#if !defined(BCES_GEOMETRY_INTEGER_ONLY)
 int ep=int(ex)+int(ey)-127;
 if(ex<255&&ey<255&&ep>=64&&ep<=189&&ez>=64&&ez<=190){
  float a=as_type<float>(x),b=as_type<float>(y),c=as_type<float>(z);
  float p=a*b,product_error=fma(a,b,-p),s=p+c;
  float addition_error=g_sum_error(p,c,s),r=fma(a,b,c),d=s-r;
  float u=d+addition_error,error=u+product_error;
  // A nonzero sum of two rounded floats has the exact sign despite the
  // preceding TwoSum residual. At exact cancellation, recover that residual.
  if(error==0)error=g_sum_error(d,addition_error,u);
  return g_toward_zero(r,error);
 }
#endif
 return g_fma(x,y,z);
}
#endif
