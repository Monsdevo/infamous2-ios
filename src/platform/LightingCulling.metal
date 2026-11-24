// A tile is packed only after at least one per-four-pixel light list is nonempty
// (SPU 4E94/4EB8 -> 51F8; 50DC/5140 -> 5210). This is independent of
// N dot L, light colour and the spot near term. A rejected tile is all zero;
// an accepted tile retains the RGBM alpha floor even on unlit/sky pixels.
kernel void bces_light_tile_mask(texture2d<float> zt [[texture(0)]],
    constant GLParams& p [[buffer(0)]], device uint* masks [[buffer(1)]],
    constant uint2& origin [[buffer(2)]], constant uint2& extent [[buffer(3)]],
    uint tid [[thread_index_in_threadgroup]], uint2 tile [[threadgroup_position_in_grid]]) {
    threadgroup atomic_uint flags;
    if(tid==0)atomic_store_explicit(&flags,0u,memory_order_relaxed);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    BGrid grid=bgrid(p,origin/uint2(32,40)+tile);
    uint own=0;
    for(uint i=tid;i<1280u;i+=64u) {
        uint2 local=tile*uint2(32,40)+uint2(i%32u,i/32u);
        if(any(local>=extent))continue;
        uint z24=uint(clamp(zt.read(local).x,0.0,1.0)*16777215.0);
        if(z24!=0xFFFFFFu)own|=1u;
        uint3 P=bposition(grid,uint2(i%32u,i/32u),z24);
        for(int k=0;k<int(p.misc.y);k++) {
            if(bmember(P,p.l[k])){own|=2u;break;}
        }
        if(own==3u)break;
    }
    atomic_fetch_or_explicit(&flags,own,memory_order_relaxed);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if(tid==0)masks[tile.y*((extent.x+31u)/32u)+tile.x]=
        atomic_load_explicit(&flags,memory_order_relaxed)==3u?1u:0u;
}
