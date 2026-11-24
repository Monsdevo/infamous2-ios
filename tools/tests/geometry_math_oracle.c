#include "spu_helpers.h"
void geometry_math_oracle(const uint32_t*input,uint32_t*out,unsigned n){
 for(unsigned i=0;i<n;i++){uint32_t x=input[3*i],y=input[3*i+1],z=input[3*i+2];
  out[6*i]=spu__fa_lane(x,y);out[6*i+1]=spu__fa_lane(x,y^0x80000000u);out[6*i+2]=spu__fm_lane(x,y);
  out[6*i+3]=spu__fma_lane(x,y,z,0,0);out[6*i+4]=spu__fma_lane(x,y,z,0,0x80000000u);out[6*i+5]=spu__fma_lane(x,y,z,0x80000000u,0);
 }
}
