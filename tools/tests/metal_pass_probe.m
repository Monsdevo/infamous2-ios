#import "MetalPassProbe.h"
#import <Foundation/Foundation.h>
#include <unistd.h>
int main(int argc,char**argv){@autoreleasepool{
 if(argc!=2)return 2;setenv("BCES_RESEARCH_DIR",argv[1],1);
 NSString* root=@(argv[1]);id<MTLDevice> d=MTLCreateSystemDefaultDevice();if(!d)return 3;
 NSError* error=nil;
 NSString* source=@"#include <metal_stdlib>\nusing namespace metal; vertex float4 v(uint id [[vertex_id]]){float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};return float4(p[id],0,1);} fragment float4 f(){return float4(0.25,0.5,0.75,1);}";
 id<MTLLibrary> lib=[d newLibraryWithSource:source options:nil error:&error];if(!lib)return 4;
 MTLRenderPipelineDescriptor* pipeline=[MTLRenderPipelineDescriptor new];pipeline.vertexFunction=[lib newFunctionWithName:@"v"];pipeline.fragmentFunction=[lib newFunctionWithName:@"f"];pipeline.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;
 id<MTLRenderPipelineState> pso=[d newRenderPipelineStateWithDescriptor:pipeline error:&error];if(!pso)return 5;
 id<MTLCommandQueue> q=[d newCommandQueue];uint8_t result[2][4];
 for(unsigned trial=0;trial<2;trial++){
  if(trial){[@"fixture01\n" writeToFile:[root stringByAppendingPathComponent:@"gpu-pass-request.txt"] atomically:YES encoding:NSUTF8StringEncoding error:nil];bces_pass_probe_boundary(d);if(bces_pass_probe_state()!=1)return 6;}
  MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:16 height:16 mipmapped:NO];td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageRenderTarget;
  id<MTLTexture> target=[d newTextureWithDescriptor:td];MTLRenderPassDescriptor* rp=[MTLRenderPassDescriptor renderPassDescriptor];rp.colorAttachments[0].texture=target;rp.colorAttachments[0].loadAction=MTLLoadActionClear;rp.colorAttachments[0].storeAction=MTLStoreActionStore;
  id<MTLCommandBuffer> cb=[q commandBuffer];id<MTLRenderCommandEncoder> enc=bces_pass_probe_encoder(cb,rp,"fixture",0);[enc setRenderPipelineState:pso];bces_pass_probe_draw(1,3,0);[enc drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];[enc endEncoding];
  if(trial)bces_pass_probe_present_begin();bces_pass_probe_commit(cb);[cb commit];[cb waitUntilCompleted];if(cb.status==MTLCommandBufferStatusError)return 7;
  [target getBytes:result[trial] bytesPerRow:4 fromRegion:MTLRegionMake2D(8,8,1,1) mipmapLevel:0];
 }
 for(unsigned i=0;i<300&&bces_pass_probe_state()==2;i++)usleep(10000);
 if(memcmp(result[0],result[1],4))return 8;
 NSData* data=[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@"gpu-pass-fixture01.json"]];NSDictionary* report=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
 if(![report[@"valid"] boolValue]){fprintf(stderr,"%s\n",report.description.UTF8String);return 9;}
 if([report[@"rows"] count]!=1||[report[@"rows"][0][@"draw_records"] intValue]!=1)return 10;
 // A clear-only pass may have no fragment timestamps (zero/zero). It must
 // never turn into a span measured from GPU epoch0.
 [@"fixture02\n" writeToFile:[root stringByAppendingPathComponent:@"gpu-pass-request.txt"] atomically:YES encoding:NSUTF8StringEncoding error:nil];bces_pass_probe_boundary(d);
 MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:16 height:16 mipmapped:NO];td.usage=MTLTextureUsageRenderTarget;
 id<MTLTexture> t=[d newTextureWithDescriptor:td];MTLRenderPassDescriptor* pass=[MTLRenderPassDescriptor renderPassDescriptor];pass.colorAttachments[0].texture=t;pass.colorAttachments[0].loadAction=MTLLoadActionClear;pass.colorAttachments[0].storeAction=MTLStoreActionStore;
 id<MTLCommandBuffer> cb=[q commandBuffer];id<MTLRenderCommandEncoder> e=bces_pass_probe_encoder(cb,pass,"clear-only",0);[e endEncoding];bces_pass_probe_present_begin();bces_pass_probe_commit(cb);[cb commit];[cb waitUntilCompleted];
 for(unsigned i=0;i<300&&bces_pass_probe_state()==2;i++)usleep(10000);
 data=[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@"gpu-pass-fixture02.json"]];report=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
 if(![report[@"valid"] boolValue]||[report[@"rows"][0][@"span_ms"] doubleValue]>1000)return 11;
 NSString* cs=@"#include <metal_stdlib>\nusing namespace metal; kernel void k(device uint* p[[buffer(0)]],uint i[[thread_position_in_grid]]){p[i]=12345+i;}";
 id<MTLLibrary> cl=[d newLibraryWithSource:cs options:nil error:&error];if(!cl)return 12;
 id<MTLComputePipelineState> cp=[d newComputePipelineStateWithFunction:[cl newFunctionWithName:@"k"] error:&error];if(!cp)return 13;
 uint32_t values[2][64];
 for(unsigned trial=0;trial<2;trial++){
  if(trial){[@"fixture03\n" writeToFile:[root stringByAppendingPathComponent:@"gpu-pass-request.txt"] atomically:YES encoding:NSUTF8StringEncoding error:nil];bces_pass_probe_boundary(d);}
  id<MTLBuffer> out=[d newBufferWithLength:sizeof(values[trial]) options:MTLResourceStorageModeShared];memset(out.contents,0,out.length);
  id<MTLCommandBuffer> cb=[q commandBuffer];id<MTLComputeCommandEncoder> ce=bces_pass_probe_compute(cb,"compute-fixture");[ce setComputePipelineState:cp];[ce setBuffer:out offset:0 atIndex:0];[ce dispatchThreads:MTLSizeMake(64,1,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];[ce endEncoding];
  if(trial)bces_pass_probe_present_begin();bces_pass_probe_commit(cb);[cb commit];[cb waitUntilCompleted];if(cb.status==MTLCommandBufferStatusError)return 14;memcpy(values[trial],out.contents,sizeof(values[trial]));
 }
 for(unsigned i=0;i<300&&bces_pass_probe_state()==2;i++)usleep(10000);
 if(memcmp(values[0],values[1],sizeof(values[0])))return 15;
 for(unsigned i=0;i<64;i++)if(values[1][i]!=12345+i)return 16;
 data=[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@"gpu-pass-fixture03.json"]];report=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
 if(![report[@"valid"] boolValue]||![report[@"rows"][0][@"compute_present"] boolValue]||[report[@"rows"][0][@"compute_ms"] doubleValue]<=0)return 17;
 printf("PASS actual M3 stage timestamps; off/on pixel bytes identical: %u,%u,%u,%u\n",result[0][0],result[0][1],result[0][2],result[0][3]);return 0;
}}
