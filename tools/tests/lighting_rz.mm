#include "spu_helpers.h"
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <vector>
#include "lighting_validation_msl.inc"
int main(){ @autoreleasepool {
 constexpr unsigned n=4096;
 std::vector<uint32_t> input(n*4),expected(n*4);
 uint32_t random=0x51f85210;
 auto next=[&](){random^=random<<13;random^=random>>17;random^=random<<5;return random;};
 for(unsigned i=0;i<n;i++) {
  uint32_t x=next(),y=next(),z=next();
  if(i<16){x=i==0?0:1u<<(i+8);y=0x7fffffffu;z=0xffffffffu;}
  input[4*i]=x;input[4*i+1]=y;input[4*i+2]=z;
  u128 a=spu_splat_u32(x),b=spu_splat_u32(y),c=spu_splat_u32(z);
  expected[4*i]=spu_fa_ref(a,b)._u32[0];expected[4*i+1]=spu_fm_ref(a,b)._u32[0];
  expected[4*i+2]=spu_fma_ref(a,b,c)._u32[0];expected[4*i+3]=spu_fi(a,spu_frest(a))._u32[0];
 }
 NSString* source=[[NSString stringWithUTF8String:lighting_validation_msl] stringByAppendingString:@"\nkernel void rz_test(device const uint4* a [[buffer(0)]], device uint4* b [[buffer(1)]], uint i [[thread_position_in_grid]]) { uint4 x=a[i];b[i]=uint4(badd(x.x,x.y),bmul(x.x,x.y),bfma(x.x,x.y,x.z),brecip(x.x));}\n"];
 auto device=MTLCreateSystemDefaultDevice();NSError* error=nil;auto options=[MTLCompileOptions new];options.fastMathEnabled=NO;
 auto lib=[device newLibraryWithSource:source options:options error:&error];
 auto pipeline=[device newComputePipelineStateWithFunction:[lib newFunctionWithName:@"rz_test"] error:&error];
 if(!pipeline){fprintf(stderr,"%s\n",error.description.UTF8String);return 2;}
 auto a=[device newBufferWithBytes:input.data() length:input.size()*4 options:MTLResourceStorageModeShared];
 auto b=[device newBufferWithLength:input.size()*4 options:MTLResourceStorageModeShared];
 auto cb=[[device newCommandQueue] commandBuffer];auto encoder=[cb computeCommandEncoder];[encoder setComputePipelineState:pipeline];[encoder setBuffer:a offset:0 atIndex:0];[encoder setBuffer:b offset:0 atIndex:1];[encoder dispatchThreads:MTLSizeMake(n,1,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];[encoder endEncoding];[cb commit];[cb waitUntilCompleted];
 if(cb.status!=MTLCommandBufferStatusCompleted)return 3;
 const uint32_t* actual=(const uint32_t*)b.contents;
 for(unsigned i=0;i<n*4;i++)if(actual[i]!=expected[i]){fprintf(stderr,"FAIL op %u case %u input=%08x,%08x,%08x actual=%08x expected=%08x\n",i%4,i/4,input[(i/4)*4],input[(i/4)*4+1],input[(i/4)*4+2],actual[i],expected[i]);return 4;}
 printf("PASS: %u exact GPU RZ add/mul/fma/frest+fi comparisons, random extended-range bit patterns\n",n*4);
 return 0;
}}
