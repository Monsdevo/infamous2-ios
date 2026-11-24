// Full five-pass shader smoke test with analytical constant-AO fixtures.
// This is not a captured-game/SPU equivalence test or a device FPS benchmark.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "ssao_gpu.h"
#include "ssao_test_msl.inc"
#include <vector>
#include <cassert>
int main(){@autoreleasepool {
 auto dev=MTLCreateSystemDefaultDevice();NSError* error=nil;
 auto options=[MTLCompileOptions new];options.fastMathEnabled=NO;
 auto lib=[dev newLibraryWithSource:[NSString stringWithUTF8String:shader] options:options error:&error];
 if(!lib){fprintf(stderr,"%s\n",error.description.UTF8String);return 2;}
 const char* names[]={"ssao_hd_fs","ssao_ao_fs","ssao_blur_h_fs","ssao_blur_v_fs","ssao_up4_fs"};
 const MTLPixelFormat fmt[]={MTLPixelFormatR32Float,MTLPixelFormatR8Unorm,MTLPixelFormatR8Unorm,MTLPixelFormatR8Unorm,MTLPixelFormatRGBA8Unorm};
 id<MTLRenderPipelineState> ps[5];
 for(int i=0;i<5;i++){auto d=[MTLRenderPipelineDescriptor new];d.vertexFunction=[lib newFunctionWithName:@"probe_vs"];d.fragmentFunction=[lib newFunctionWithName:[NSString stringWithUTF8String:names[i]]];d.colorAttachments[0].pixelFormat=fmt[i];ps[i]=[dev newRenderPipelineStateWithDescriptor:d error:&error];if(!ps[i]){fprintf(stderr,"%s\n",error.description.UTF8String);return 3;}}
 auto tex=[&](MTLPixelFormat f,unsigned w,unsigned h){auto d=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:f width:w height:h mipmapped:NO];d.storageMode=MTLStorageModeShared;d.usage=MTLTextureUsageRenderTarget|MTLTextureUsageShaderRead;return [dev newTextureWithDescriptor:d];};
 auto z=tex(MTLPixelFormatR32Float,64,64),n=tex(MTLPixelFormatRGBA8Unorm,64,64);
 std::vector<float> depth(64*64,.5f);std::vector<uint32_t> normal(64*64,0xff808080);
 [z replaceRegion:MTLRegionMake2D(0,0,64,64) mipmapLevel:0 withBytes:depth.data() bytesPerRow:256];[n replaceRegion:MTLRegionMake2D(0,0,64,64) mipmapLevel:0 withBytes:normal.data() bytesPerRow:256];
 id<MTLTexture> dst[5];for(int i=0;i<5;i++)dst[i]=tex(fmt[i],i==4?64:32,i==4?64:32);
 for(int test=0;test<2;test++){
  SsaoGpuConsts p={};p.depth_ab[0]=-.1;p.depth_ab[1]=.1;for(int k=0;k<12;k++)p.Z[k]=1;
  p.D0[0]=6;p.D0[3]=1;p.E0[1]=-1;p.E0[2]=1;p.E0[3]=1000;p.F0[1]=test?.5:0;
  memcpy(p.up,p.depth_ab,8);p.up[2]=40;p.dims[0]=p.dims[1]=64;p.dims[2]=p.dims[3]=32;
  auto pb=[dev newBufferWithBytes:&p length:sizeof p options:MTLResourceStorageModeShared];auto queue=[dev newCommandQueue];auto cb=[queue commandBuffer];
  id<MTLTexture> input[5][3]={{z,nil,nil},{dst[0],n,nil},{dst[1],dst[0],nil},{dst[2],dst[0],nil},{dst[3],dst[0],z}};
  for(int k=0;k<5;k++){
   auto pass=[MTLRenderPassDescriptor renderPassDescriptor];pass.colorAttachments[0].texture=dst[k];pass.colorAttachments[0].loadAction=MTLLoadActionDontCare;pass.colorAttachments[0].storeAction=MTLStoreActionStore;
   auto e=[cb renderCommandEncoderWithDescriptor:pass];[e setRenderPipelineState:ps[k]];[e setFragmentBuffer:pb offset:0 atIndex:0];for(int j=0;j<3;j++)if(input[k][j])[e setFragmentTexture:input[k][j] atIndex:j];[e drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];[e endEncoding];
  }
  [cb commit];[cb waitUntilCompleted];if(cb.status!=MTLCommandBufferStatusCompleted){fprintf(stderr,"%s\n",cb.error.description.UTF8String);return 4;}
  for(int k=0;k<5;k++){
   unsigned w=k==4?64:32,bytes=k==0?4:k==4?4:1;std::vector<uint8_t> data(w*w*bytes);[dst[k] getBytes:data.data() bytesPerRow:w*bytes fromRegion:MTLRegionMake2D(0,0,w,w) mipmapLevel:0];
   if(k==0){auto f=(float*)data.data();for(unsigned i=0;i<w*w;i++)assert(isfinite(f[i]) && fabs(f[i]-20)<.001);}
   else {int expected=test?128-k:0;for(unsigned i=0;i<data.size();i++)assert(abs(int(data[i])-expected)<=(test?1:0));}
  }
 }
 puts("PASS: all five production SSAO shaders compile and execute; half depth and zero/nonzero analytical AO fixtures");
 return 0;
}}
