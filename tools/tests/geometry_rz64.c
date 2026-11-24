#include <stdbool.h>
#include "spu_helpers.h"
#include "GeometryRZ64.h"
#include <assert.h>
static uint32_t rng=0x7c195a43;
static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(void){
 const uint edge[]={0,0x80000000,1,0x7fffff,0x800000,0x800001,0x3effffff,0x3f000000,0x3f7fffff,0x3f800000,0x3f800001,0xbf800000,0x7f7fffff,0x7f800000,0x7fffffff,0xffffffff};
 uint64_t checked=0;
 for(unsigned i=0;i<2000000;i++){
  uint x=i<4096?edge[i&15]:next(),y=i<4096?edge[(i>>4)&15]:next(),z=i<4096?edge[(i>>8)&15]:next();
  if(i%4==0){uint32_t product=spu__fm_lane(x,y);z=product^0x80000000u;if(i&4)z+=(i&8)?1:-1;}
  uint ref[6]={spu__fa_lane(x,y),spu__fa_lane(x,y^0x80000000u),spu__fm_lane(x,y),spu__fma_lane(x,y,z,0,0),spu__fma_lane(x,y,z,0,0x80000000u),spu__fma_lane(x,y,z,0x80000000u,0)};
  uint got[6]={g_add(x,y),g_add(x,y^0x80000000u),g_mul(x,y),g_fma(x,y,z),g_fma(x,y,z^0x80000000u),g_fma(x^0x80000000u,y,z)};
  for(unsigned op=0;op<6;op++){if(ref[op]!=got[op]){fprintf(stderr,"FAIL i=%u op=%u %08x %08x %08x expected=%08x got=%08x\n",i,op,x,y,z,ref[op],got[op]);return 1;}checked++;}
 }
 printf("PASS %llu exact 64-bit geometry arithmetic comparisons, including cancellation\n",checked);return 0;
}
