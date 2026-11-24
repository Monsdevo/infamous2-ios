#pragma once
#include <stdint.h>
#include <string.h>
#include <initializer_list>
struct LightingTile {
    uint32_t parameter,descriptor,x,y,w,h,full_w,full_h,normal,depth,diffuse,specular,frame,lights,count;
};
static inline uint32_t light_be32(const uint8_t* p) {
    return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];
}
static inline bool light_range(uint32_t p,uint64_t size) {return p<0x40000u && uint64_t(p)+size<=0x40000u;}
static inline bool light_tile_decode(const uint8_t* ls,uint32_t parameter,LightingTile& t) {
    memset(&t,0,sizeof t);if(!ls || !light_range(parameter,28))return false;
    t.parameter=parameter;t.descriptor=light_be32(ls+parameter);
    if(!light_range(t.descriptor,0x4c))return false;
    t.x=light_be32(ls+parameter+4);t.y=light_be32(ls+parameter+8);
    t.w=uint32_t(ls[t.descriptor+0x48])<<8|ls[t.descriptor+0x49];
    t.h=uint32_t(ls[t.descriptor+0x4a])<<8|ls[t.descriptor+0x4b];
    const unsigned nx=ls[t.descriptor],ny=ls[t.descriptor+1];
    // Bound snapshots; reject unsupported layouts rather than guessing pitch.
    if(!nx || !ny || !t.w || !t.h || t.w>128 || t.h>128 || t.x>=nx || t.y>=ny)return false;
    t.full_w=t.w*nx;t.full_h=t.h*ny;
    t.diffuse=light_be32(ls+parameter+12);t.normal=light_be32(ls+parameter+16);
    t.depth=light_be32(ls+parameter+20);t.specular=light_be32(ls+parameter+24);
    t.frame=light_be32(ls+0x9c80);t.lights=light_be32(ls+0x9cb0);
    if(!light_range(t.frame,0x100))return false;
    t.count=light_be32(ls+t.frame+0x90);if(t.count>128 || !light_range(t.lights,uint64_t(t.count)*48))return false;
    for(uint32_t p : {t.normal,t.depth,t.diffuse,t.specular})if(!light_range(p,uint64_t(t.w)*t.h*4))return false;
    return true;
}
