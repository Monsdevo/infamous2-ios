#include "LightingValidation.h"
#include "spu_context.h"
#import <Foundation/Foundation.h>
#include <memory>
#include <unistd.h>
int main(int argc,char** argv){
 if(argc!=2)return 2;
 @autoreleasepool {
  auto c=std::make_unique<spu_context>();c->ls=c->ls_store;
  auto put=[&](unsigned a,unsigned v){c->ls[a]=v>>24;c->ls[a+1]=v>>16;c->ls[a+2]=v>>8;c->ls[a+3]=v;};
  put(0x100,0x200);c->ls[0x200]=40;c->ls[0x201]=18;c->ls[0x249]=32;c->ls[0x24b]=40;
  put(0x10c,0x20000);put(0x110,0x20000);put(0x114,0x22000);put(0x118,0x22000);
  put(0x9c80,0x300);put(0x9cb0,0x400);c->gpr[3]._u32[0]=0x100;
  memset(c->ls+0x22000,0,32*40*4); // non-sky zero-light fixture catches alpha=90 regression
  bces_light_validation_configure(argv[1],1);unsigned token=bces_light_validation_begin(c.get(),0x4ac8);if(!token)return 3;
  memset(c->ls+0x20000,0,32*40*4);memset(c->ls+0x22000,0,32*40*4);
  bces_light_validation_end(c.get(),token);
  for(int i=0;i<500 && !bces_light_validation_completed();i++)usleep(20000);
  return bces_light_validation_completed()==1?0:4;
 }
}
