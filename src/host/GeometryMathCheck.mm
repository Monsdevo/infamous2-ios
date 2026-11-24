#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "GeometryRZ64.h"
#include <cassert>
#include <cstdio>
extern "C" void geometry_math_oracle(const uint32_t*,uint32_t*,unsigned);
int main(int argc,char**argv){@autoreleasepool{
 assert(argc==2);NSError*error=nil;id<MTLDevice>d=MTLCreateSystemDefaultDevice();assert(d);
 NSString*s=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];assert(s);
 s=[@"#include <metal_stdlib>\nusing namespace metal;\n" stringByAppendingString:s];s=[s stringByAppendingString:@"\nkernel void check(device const uint*input [[buffer(0)]],device uint*out [[buffer(1)]],constant uint&n [[buffer(2)]],uint i [[thread_position_in_grid]]){if(i>=n)return;uint x=input[3*i],y=input[3*i+1],z=input[3*i+2];out[6*i]=g_fast_add(x,y);out[6*i+1]=g_fast_add(x,y^0x80000000u);out[6*i+2]=g_fast_mul(x,y);out[6*i+3]=g_fast_fma(x,y,z);out[6*i+4]=g_fast_fma(x,y,z^0x80000000u);out[6*i+5]=g_fast_fma(x^0x80000000u,y,z);}\n"];
 MTLCompileOptions*opt=[MTLCompileOptions new];opt.mathMode=MTLMathModeSafe;opt.mathFloatingPointFunctions=MTLMathFloatingPointFunctionsPrecise;
 id<MTLLibrary>lib=[d newLibraryWithSource:s options:opt error:&error];if(!lib){fprintf(stderr,"%s\n",error.description.UTF8String);return 2;}
 id<MTLComputePipelineState>pso=[d newComputePipelineStateWithFunction:[lib newFunctionWithName:@"check"] error:&error];assert(pso);id<MTLCommandQueue>q=[d newCommandQueue];
 const unsigned n=262144;id<MTLBuffer>in=[d newBufferWithLength:n*3*4 options:MTLResourceStorageModeShared],out=[d newBufferWithLength:n*6*4 options:MTLResourceStorageModeShared];uint32_t*expected=(uint32_t*)malloc(n*6*4);assert(expected);
 const uint32_t edge[]={0,0x80000000,1,0x7fffff,0x800000,0x800001,0x3effffff,0x3f000000,0x3f7fffff,0x3f800000,0x3f800001,0xbf800000,0x7f7fffff,0x7f800000,0x7fffffff,0xffffffff};
 uint32_t rng=0x56e19a37;auto next=[&](){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;};uint64_t total=0;
 for(unsigned chunk=0;chunk<8;chunk++){
  auto*a=(uint32_t*)in.contents;for(unsigned i=0;i<n;i++){uint32_t x=chunk==0&&i<4096?edge[i&15]:next(),y=chunk==0&&i<4096?edge[(i>>4)&15]:next(),z=chunk==0&&i<4096?edge[(i>>8)&15]:next();if(chunk>=4){x=(x&0x807fffffu)|((96u+(x%63u))<<23);y=(y&0x807fffffu)|((96u+(y%63u))<<23);z=(z&0x807fffffu)|((64u+(z%127u))<<23);}if(i%4==0){z=g_mul(x,y)^0x80000000u;if(i&4)z+=(i&8)?1:-1;}a[3*i]=x;a[3*i+1]=y;a[3*i+2]=z;}
  geometry_math_oracle(a,expected,n);id<MTLCommandBuffer>cmd=[q commandBuffer];id<MTLComputeCommandEncoder>enc=[cmd computeCommandEncoder];[enc setComputePipelineState:pso];[enc setBuffer:in offset:0 atIndex:0];[enc setBuffer:out offset:0 atIndex:1];[enc setBytes:&n length:sizeof n atIndex:2];[enc dispatchThreads:MTLSizeMake(n,1,1) threadsPerThreadgroup:MTLSizeMake(128,1,1)];[enc endEncoding];[cmd commit];[cmd waitUntilCompleted];assert(cmd.status==MTLCommandBufferStatusCompleted);
  auto*got=(uint32_t*)out.contents;for(unsigned i=0;i<n*6;i++)if(got[i]!=expected[i]){fprintf(stderr,"FAIL chunk=%u case=%u op=%u expected=%08x actual=%08x\n",chunk,i/6,i%6,expected[i],got[i]);return 3;}total+=n*6;
 }
 printf("PASS %llu GPU exact RZ comparisons against independent 128-bit SPU oracle on %s; cancellation/overflow/subnormal inputs\n",total,d.name.UTF8String);free(expected);return 0;
}}
