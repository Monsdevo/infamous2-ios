#include "spu_helpers.h"
// Independent exact integer oracle; runs only during background GPU setup.
void bces_geometry_math_probe(uint32_t*input,uint32_t*out,unsigned n){
 uint32_t state=0xc7318e2d;
 for(unsigned i=0;i<n;i++){
  uint32_t v[3];for(unsigned j=0;j<3;j++){state^=state<<13;state^=state>>17;state^=state<<5;v[j]=state;}
  uint32_t x=v[0],y=v[1],z=v[2];
  if(i%2){x=(x&0x807fffffu)|((96u+x%63u)<<23);y=(y&0x807fffffu)|((96u+y%63u)<<23);z=(z&0x807fffffu)|((64u+z%127u)<<23);}
  if(i%4==1){z=spu__fm_lane(x,y)^0x80000000u;if(i&4)z+=(i&8)?1:-1;}
  if(!i){x=0x3f800001;y=0x33800000;z=0;}
  input[3*i]=x;input[3*i+1]=y;input[3*i+2]=z;
  out[6*i]=spu__fa_lane(x,y);out[6*i+1]=spu__fa_lane(x,y^0x80000000u);out[6*i+2]=spu__fm_lane(x,y);
  out[6*i+3]=spu__fma_lane(x,y,z,0,0);out[6*i+4]=spu__fma_lane(x,y,z,0,0x80000000u);out[6*i+5]=spu__fma_lane(x,y,z,0x80000000u,0);
 }
}
