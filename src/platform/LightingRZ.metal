// Exact SPU single operations used only by the tile classifier. Mirrors the
// pinned spu_helpers.h integer reference (extended exponent, flush denormals,
// round toward zero). The colour shader keeps its separate float approximation.
struct B128 { ulong hi,lo; };
inline B128 b128(ulong x){return B128{0,x};}
inline B128 bsh(ulong x,uint s){return s==0?b128(x):s<64?B128{x>>(64-s),x<<s}:B128{x<<(s-64),0};}
inline B128 bad(B128 a,B128 b){ulong v=a.lo+b.lo;return B128{a.hi+b.hi+(v<a.lo),v};}
inline B128 bsu(B128 a,B128 b){return B128{a.hi-b.hi-(a.lo<b.lo),a.lo-b.lo};}
inline bool bgt(B128 a,B128 b){return a.hi>b.hi || (a.hi==b.hi && a.lo>b.lo);}
inline uint bpack(uint sign,B128 a,int e) {
 if(!(a.hi|a.lo))return 0;
 int top=a.hi?127-int(clz(a.hi)):63-int(clz(a.lo));int exp=top+e+127;
 if(exp>255)return sign|0x7FFFFFFFu;if(exp<1)return 0;
 int s=top-23;ulong m;
 if(s>=64)m=a.hi>>(s-64);
 else if(s>0)m=(a.lo>>s)|(a.hi<<(64-s));
 else m=a.lo<<(-s);
 return sign|(uint(exp)<<23)|(uint(m)&0x7FFFFFu);
}
inline uint bsum(uint sa,ulong a,int ea,uint sb,ulong b,int eb) {
 if(ea<eb){uint ts=sa;sa=sb;sb=ts;ulong t=a;a=b;b=t;int e=ea;ea=eb;eb=e;}
 uint d=uint(ea-eb);
 if(d>79)return bpack(sa,b128(sa==sb?a:(a*2-1)),sa==sb?ea:ea-1);
 B128 x=bsh(a,d),y=b128(b);
 if(sa==sb)return bpack(sa,bad(x,y),eb);
 return bgt(x,y)?bpack(sa,bsu(x,y),eb):bpack(sb,bsu(y,x),eb);
}
inline uint badd(uint x,uint y) {
 uint ex=(x>>23)&255,ey=(y>>23)&255;
 if(!ex)return ey?y:0;if(!ey)return x;
 return bsum(x&0x80000000u,(x&0x7FFFFFu)|0x800000u,int(ex)-150,y&0x80000000u,(y&0x7FFFFFu)|0x800000u,int(ey)-150);
}
inline uint bmul(uint x,uint y) {
 uint ex=(x>>23)&255,ey=(y>>23)&255;if(!ex || !ey)return 0;
 return bpack((x^y)&0x80000000u,b128(ulong((x&0x7FFFFFu)|0x800000u)*ulong((y&0x7FFFFFu)|0x800000u)),int(ex)+int(ey)-300);
}
inline uint bfma(uint x,uint y,uint z) {
 uint ex=(x>>23)&255,ey=(y>>23)&255,ez=(z>>23)&255;
 if(!ex || !ey)return ez?z:0;
 uint sign=(x^y)&0x80000000u;ulong prod=ulong((x&0x7FFFFFu)|0x800000u)*ulong((y&0x7FFFFFu)|0x800000u);
 if(!ez)return bpack(sign,b128(prod),int(ex)+int(ey)-300);
 return bsum(sign,prod,int(ex)+int(ey)-300,z&0x80000000u,(z&0x7FFFFFu)|0x800000u,int(ez)-150);
}
inline uint bfi(uint x,uint est) {
 uint sign=est&0x80000000u;int e=int((est>>23)&255);if(!e)return 0;
 ulong m=((ulong(8192)|ulong((est>>10)&8191))<<19)-ulong(est&1023)*ulong(x&0x7ffff);
 if(m<(1ul<<32)){m<<=1;if(--e==0)return 0;}
 return sign|(uint(e)<<23)|(uint(m>>9)&0x7fffff);
}
// LUTs below are extracted from the pinned toolkit, not host 1/x approximations.
BCES_RZ_LUTS
inline uint brecip(uint x){uint e=(x>>23)&255;return bfi(x,(x&0x80000000u)|((e==0?255:e>=253?0:253-e)<<23)|bces_frest[(x>>18)&31]);}
inline uint brsqrt(uint x){uint e=(x>>23)&255;return bfi(x,((e==0?255:190-(e+1)/2)<<23)|bces_frsqrt[(x>>18)&63]);}
inline uint bdivide(uint a,uint b){uint r=brecip(b),q=bmul(a,r);return bfma(bfma(q^0x80000000u,b,a),r,q);}
struct BGrid {uint4 top,step,dy,dz;};
inline BGrid bgrid(constant GLParams& p,uint2 tile) {
 uint x=bdivide(as_type<uint>(float(tile.x+1)),as_type<uint>(p.misc.z/32.0));
 uint y=bdivide(as_type<uint>(float(tile.y)),as_type<uint>(p.misc.w/40.0));
 uint dx=bdivide(0x3f800000u,as_type<uint>(p.misc.z)),dy=bdivide(0x3f800000u,as_type<uint>(p.misc.w));
 BGrid g;
 for(uint c=0;c<4;c++) {
  g.top[c]=bfma(as_type<uint>(p.m[1][c]),y,bfma(as_type<uint>(p.m[0][c]),x,as_type<uint>(p.m[3][c])));
  g.step[c]=bmul(bmul(as_type<uint>(p.m[0][c]),dx),0xc0800000u);
  g.dy[c]=bmul(as_type<uint>(p.m[1][c]),dy);g.dz[c]=bmul(as_type<uint>(p.m[2][c]),0x33800000u);
 }
 return g;
}
inline uint3 bposition(BGrid g,uint2 xy,uint z24) {
 uint4 h;
 for(uint c=0;c<4;c++) {
  uint row=bfma(as_type<uint>(float(xy.y)),g.dy[c],g.top[c]);
  uint value=bfma(as_type<uint>(1.0-.25*float(xy.x%4)),g.step[c],row);
  for(uint i=0;i<7-xy.x/4;i++)value=badd(value,g.step[c]);
  h[c]=bfma(as_type<uint>(float(z24)),g.dz[c],value);
 }
 uint inv=brecip(h.w);
 return uint3(bmul(h.x,inv),bmul(h.y,inv),bmul(h.z,inv));
}
inline uint bdistance(uint3 q){return bfma(q.z,q.z,bfma(q.y,q.y,bmul(q.x,q.x)));}
inline bool bmember(uint3 P,GLight light) {
 // Far rejects use a conservative 128-epsilon bound on rounded squared
 // distances. Boundary/accepted cases retain exact SPU operations below.
 float3 delta=as_type<float3>(P)-light.pos_type.xyz;
 float fastD=dot(delta,delta),fastR=light.oacbn.x*light.oacbn.x;
 if(isfinite(fastD) && isfinite(fastR) && fastD-fastR>1.52587890625e-5*max(fastD,fastR))return false;
 uint3 L=as_type<uint3>(light.pos_type.xyz),q;
 for(uint k=0;k<3;k++)q[k]=badd(L[k],P[k]^0x80000000u); // original L-P
 uint d2=bdistance(q),r2=bmul(as_type<uint>(light.oacbn.x),as_type<uint>(light.oacbn.x));
 if(d2>=r2)return false;
 if(light.pos_type.w<1.5)return true;
 uint3 dir=as_type<uint3>(-light.dir.xyz);
 uint dotValue=bfma(q.z,dir.z,bfma(q.y,dir.y,bmul(q.x,dir.x)));
 uint inv=brsqrt(d2),cosine=bmul(dotValue,inv),dist=bmul(inv,d2);
 // SPU scalar comparison treats signed magnitudes, exponent-zero as zero.
 float c=as_type<float>(cosine),d=as_type<float>(dist);
 return c>light.oacbn.z && d<light.oacbn.x;
}
