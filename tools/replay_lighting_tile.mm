// Replay a bounded paired device fixture; never execute or modify the game.
#include "LightingValidation.h"
#include "spu_context.h"
#import <Foundation/Foundation.h>
#include <memory>
#include <unistd.h>
int main(int argc,char** argv) {
 if(argc!=3 && argc!=4)return 2;
 @autoreleasepool {
  NSString* fixture=[NSString stringWithUTF8String:argv[1]];
  auto data=[&](NSString* file){return [NSData dataWithContentsOfFile:[fixture stringByAppendingPathComponent:file]];};
  NSData* before=data(@"before-ls.bin"),*after=data(@"after-ls.bin"),*gpr=data(@"before-gpr.bin");
  NSDictionary* meta=[NSJSONSerialization JSONObjectWithData:data(@"metadata.json") options:0 error:nil];
  if(before.length!=SPU_LS_SIZE || after.length!=SPU_LS_SIZE || gpr.length!=2048 || !meta)return 3;
  auto c=std::make_unique<spu_context>();c->ls=c->ls_store;
  memcpy(c->ls,before.bytes,SPU_LS_SIZE);memcpy(c->gpr,gpr.bytes,2048);
  c->spu_id=[meta[@"spu_id"] unsignedIntValue];c->image_id=[meta[@"image_id"] intValue];c->pc=[meta[@"guest_pc"] unsignedIntValue];
  bces_light_validation_configure(argv[2],argc==4?2:1);
  unsigned token=bces_light_validation_begin(c.get(),0x4ac8);if(!token)return 4;
  memcpy(c->ls,after.bytes,SPU_LS_SIZE);bces_light_validation_end(c.get(),token);
  if(bces_light_validation_rejected_zero_output())return 6;
  for(int i=0;i<500 && !bces_light_validation_completed();i++)usleep(20000);
  return bces_light_validation_completed()==1?0:5;
 }
}
