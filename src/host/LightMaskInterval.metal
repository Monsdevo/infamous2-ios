// Included after the preserved SPU arithmetic and original mask kernel.
inline uint ikey(uint x){return (x&0x7f800000u)==0?0x80000000u:(x&0x80000000u)?~x:x^0x80000000u;}
inline uint imin(uint a,uint b){return ikey(a)<ikey(b)?a:b;}
inline uint imax(uint a,uint b){return ikey(a)>ikey(b)?a:b;}
struct IBox {uint3 lo,hi;uint valid;};
inline IBox interval_box(BGrid g,uint zlo,uint zhi){
 uint4 lo,hi;
 for(uint c=0;c<4;c++){
  uint r0=bfma(0u,g.dy[c],g.top[c]),r1=bfma(0x421c0000u,g.dy[c],g.top[c]); //39
  uint a=imin(r0,r1),b=imax(r0,r1);
  uint x0=bfma(0x3e800000u,g.step[c],a),x1=bfma(0x3f800000u,g.step[c],a);
  uint x2=bfma(0x3e800000u,g.step[c],b),x3=bfma(0x3f800000u,g.step[c],b);
  a=imin(imin(x0,x1),imin(x2,x3));b=imax(imax(x0,x1),imax(x2,x3));
  for(uint j=0;j<7;j++){uint aa=badd(a,g.step[c]),bb=badd(b,g.step[c]);a=imin(a,aa);b=imax(b,bb);}
  uint zl=as_type<uint>(float(zlo)),zh=as_type<uint>(float(zhi));
  x0=bfma(zl,g.dz[c],a);x1=bfma(zh,g.dz[c],a);x2=bfma(zl,g.dz[c],b);x3=bfma(zh,g.dz[c],b);
  lo[c]=imin(imin(x0,x1),imin(x2,x3));hi[c]=imax(imax(x0,x1),imax(x2,x3));
 }
 IBox out;out.valid=0;
 if(ikey(lo.w)<=0x80000000u&&ikey(hi.w)>=0x80000000u)return out;
 uint il=brecip(hi.w),ih=brecip(lo.w);if(ikey(il)>ikey(ih))return out;
 for(uint c=0;c<3;c++){
  uint a=bmul(lo[c],il),b=bmul(lo[c],ih),c0=bmul(hi[c],il),d=bmul(hi[c],ih);
  out.lo[c]=imin(imin(a,b),imin(c0,d));out.hi[c]=imax(imax(a,b),imax(c0,d));
 }
 out.valid=1;return out;
}
inline bool interval_far(IBox box,GLight light){
 if(!box.valid)return false;
 uint3 q;uint3 L=as_type<uint3>(light.pos_type.xyz);
 for(uint c=0;c<3;c++){
  uint lo=badd(L[c],box.hi[c]^0x80000000u),hi=badd(L[c],box.lo[c]^0x80000000u);
  q[c]=(ikey(lo)<=0x80000000u&&ikey(hi)>=0x80000000u)?0u:min(lo&0x7fffffffu,hi&0x7fffffffu);
 }
 uint radius=as_type<uint>(light.oacbn.x);
 return bdistance(q)>=bmul(radius,radius);
}
inline void interval_depth(texture2d<float> zt,uint2 tile,uint2 extent,uint tid,
 threadgroup atomic_uint& flags,threadgroup atomic_uint& zlo,threadgroup atomic_uint& zhi){
 if(tid==0){atomic_store_explicit(&flags,0u,memory_order_relaxed);atomic_store_explicit(&zlo,0xffffffu,memory_order_relaxed);atomic_store_explicit(&zhi,0u,memory_order_relaxed);}
 threadgroup_barrier(mem_flags::mem_threadgroup);
 uint mn=0xffffffu,mx=0u;
 for(uint i=tid;i<1280u;i+=64u){uint2 xy=tile*uint2(32,40)+uint2(i%32u,i/32u);if(any(xy>=extent))continue;uint z=uint(clamp(zt.read(xy).x,0.0,1.0)*16777215.0);mn=min(mn,z);mx=max(mx,z);}
 atomic_fetch_min_explicit(&zlo,mn,memory_order_relaxed);atomic_fetch_max_explicit(&zhi,mx,memory_order_relaxed);
 atomic_fetch_or_explicit(&flags,mn!=0xffffffu?1u:0u,memory_order_relaxed);threadgroup_barrier(mem_flags::mem_threadgroup);
}
kernel void bces_light_tile_mask_empty(texture2d<float> zt [[texture(0)]],
 constant GLParams& p [[buffer(0)]],device uint* masks [[buffer(1)]],
 constant uint2& origin [[buffer(2)]],constant uint2& extent [[buffer(3)]],
 uint tid [[thread_index_in_threadgroup]],uint2 tile [[threadgroup_position_in_grid]]){
 threadgroup atomic_uint flags,zlo,zhi,nc;threadgroup uint candidates[128];threadgroup BGrid grid;threadgroup IBox box;
 interval_depth(zt,tile,extent,tid,flags,zlo,zhi);uint index=tile.y*((extent.x+31u)/32u)+tile.x;int n=int(p.misc.y);
 if(!atomic_load_explicit(&flags,memory_order_relaxed)||n<=0){if(tid==0)masks[index]=0;return;}
 if(tid==0){grid=bgrid(p,origin/uint2(32,40)+tile);box=interval_box(grid,atomic_load_explicit(&zlo,memory_order_relaxed),atomic_load_explicit(&zhi,memory_order_relaxed));atomic_store_explicit(&nc,0u,memory_order_relaxed);}
 threadgroup_barrier(mem_flags::mem_threadgroup);
 if(n<=128)for(uint k=tid;k<uint(n);k+=64u)if(!interval_far(box,p.l[k])){uint j=atomic_fetch_add_explicit(&nc,1u,memory_order_relaxed);candidates[j]=k;}
 threadgroup_barrier(mem_flags::mem_threadgroup);uint count=n<=128?atomic_load_explicit(&nc,memory_order_relaxed):uint(n);
 if(!count){if(tid==0)masks[index]=0;return;}
 for(uint i=tid;i<1280u;i+=64u){
  if(atomic_load_explicit(&flags,memory_order_relaxed)==3u)break;
  uint2 xy=tile*uint2(32,40)+uint2(i%32u,i/32u);if(any(xy>=extent))continue;
  uint z=uint(clamp(zt.read(xy).x,0.0,1.0)*16777215.0);uint3 P=bposition(grid,uint2(i%32u,i/32u),z);
  for(uint j=0;j<count;j++){uint k=n<=128?candidates[j]:j;if(bmember(P,p.l[k])){atomic_fetch_or_explicit(&flags,2u,memory_order_relaxed);break;}}
 }
 threadgroup_barrier(mem_flags::mem_threadgroup);if(tid==0)masks[index]=atomic_load_explicit(&flags,memory_order_relaxed)==3u?1u:0u;
}
kernel void bces_light_bounds_check(texture2d<float> zt [[texture(0)]],
 constant GLParams& p [[buffer(0)]],device uint* outputs [[buffer(1)]],
 constant uint2& origin [[buffer(2)]],constant uint2& extent [[buffer(3)]],
 uint tid [[thread_index_in_threadgroup]],uint2 tile [[threadgroup_position_in_grid]]){
 threadgroup atomic_uint flags,zlo,zhi,bad;threadgroup BGrid grid;threadgroup IBox box;
 interval_depth(zt,tile,extent,tid,flags,zlo,zhi);
 if(tid==0){grid=bgrid(p,origin/uint2(32,40)+tile);box=interval_box(grid,atomic_load_explicit(&zlo,memory_order_relaxed),atomic_load_explicit(&zhi,memory_order_relaxed));atomic_store_explicit(&bad,0u,memory_order_relaxed);}
 threadgroup_barrier(mem_flags::mem_threadgroup);uint index=tile.y*((extent.x+31u)/32u)+tile.x;
 if(!box.valid){if(tid==0)outputs[index]=2u;return;}
 for(uint i=tid;i<1280u;i+=64u){uint2 xy=tile*uint2(32,40)+uint2(i%32u,i/32u);if(any(xy>=extent))continue;uint z=uint(clamp(zt.read(xy).x,0.0,1.0)*16777215.0);uint3 P=bposition(grid,uint2(i%32u,i/32u),z);
  for(uint c=0;c<3;c++)if(ikey(P[c])<ikey(box.lo[c])||ikey(P[c])>ikey(box.hi[c]))atomic_store_explicit(&bad,1u,memory_order_relaxed);
 }
 threadgroup_barrier(mem_flags::mem_threadgroup);if(tid==0)outputs[index]=atomic_load_explicit(&bad,memory_order_relaxed)?0u:1u;
}
