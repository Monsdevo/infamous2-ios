#include "LightingTile.h"
#include <cassert>
#include <array>
#include <cstdio>
int main(){
 std::array<uint8_t,0x40000> ls{};
 auto put=[&](unsigned p,unsigned v){ls[p]=v>>24;ls[p+1]=v>>16;ls[p+2]=v>>8;ls[p+3]=v;};
 put(0x100,0x200);ls[0x200]=40;ls[0x201]=18;ls[0x249]=32;ls[0x24b]=40;
 put(0x10c,0x20000);put(0x110,0x20000);put(0x114,0x22000);put(0x118,0x22000);
 put(0x9c80,0x300);put(0x9cb0,0x400);put(0x390,1);
 LightingTile t;assert(light_tile_decode(ls.data(),0x100,t));assert(t.full_w==1280 && t.full_h==720 && t.count==1);
 put(0x104,40);assert(!light_tile_decode(ls.data(),0x100,t));put(0x104,0);
 put(0x390,129);assert(!light_tile_decode(ls.data(),0x100,t));put(0x390,1);
 put(0x114,0x3ffff);assert(!light_tile_decode(ls.data(),0x100,t));
 assert(!light_tile_decode(ls.data(),0xfffffff0,t));
 puts("PASS: decoded 1280x720 tile layout; invalid coordinates/light limits/ranges rejected");
}
