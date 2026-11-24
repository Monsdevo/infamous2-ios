#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "HostDepthOnly.h"
#include <assert.h>
#include <string.h>
static NSData* draw(id<MTLDevice> d,id<MTLCommandQueue> q,id<MTLRenderPipelineState> pso,float z,BOOL write,unsigned mode,unsigned op){
 MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatDepth32Float_Stencil8 width:32 height:32 mipmapped:NO];
 td.storageMode=MTLStorageModePrivate;td.usage=MTLTextureUsageRenderTarget;
 id<MTLTexture> depth=[d newTextureWithDescriptor:td];assert(depth);
 td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:32 height:32 mipmapped:NO];td.usage=MTLTextureUsageRenderTarget;td.storageMode=MTLStorageModeShared;
 id<MTLTexture> color=[d newTextureWithDescriptor:td];assert(color);
 MTLRenderPassDescriptor* rp=[MTLRenderPassDescriptor renderPassDescriptor];rp.colorAttachments[0].texture=color;rp.colorAttachments[0].loadAction=MTLLoadActionClear;rp.colorAttachments[0].storeAction=MTLStoreActionStore;rp.colorAttachments[0].clearColor=MTLClearColorMake(.2,.4,.6,1);
 rp.depthAttachment.texture=depth;rp.depthAttachment.loadAction=MTLLoadActionClear;rp.depthAttachment.storeAction=MTLStoreActionStore;rp.depthAttachment.clearDepth=.5;
 rp.stencilAttachment.texture=depth;rp.stencilAttachment.loadAction=MTLLoadActionClear;rp.stencilAttachment.storeAction=MTLStoreActionStore;rp.stencilAttachment.clearStencil=3;
 MTLDepthStencilDescriptor* ds=[MTLDepthStencilDescriptor new];ds.depthCompareFunction=MTLCompareFunctionLess;ds.depthWriteEnabled=write;
 MTLStencilDescriptor* st=[MTLStencilDescriptor new];st.stencilCompareFunction=mode?MTLCompareFunctionEqual:MTLCompareFunctionAlways;st.readMask=255;st.writeMask=255;
 const MTLStencilOperation operations[]={MTLStencilOperationReplace,MTLStencilOperationIncrementClamp,MTLStencilOperationInvert,MTLStencilOperationDecrementWrap};
 st.stencilFailureOperation=operations[(op+1)%4];st.depthFailureOperation=operations[(op+2)%4];st.depthStencilPassOperation=operations[op];ds.frontFaceStencil=st;ds.backFaceStencil=st;
 id<MTLCommandBuffer> cb=[q commandBuffer];id<MTLRenderCommandEncoder> e=[cb renderCommandEncoderWithDescriptor:rp];assert(e);
 [e setRenderPipelineState:pso];[e setDepthStencilState:[d newDepthStencilStateWithDescriptor:ds]];[e setStencilReferenceValue:mode==2?4:3];[e setVertexBytes:&z length:sizeof z atIndex:0];[e drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];[e endEncoding];
 id<MTLBuffer> out=[d newBufferWithLength:16384 options:MTLResourceStorageModeShared];memset(out.contents,0,out.length);
 id<MTLBlitCommandEncoder> b=[cb blitCommandEncoder];
 [b copyFromTexture:depth sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(32,32,1) toBuffer:out destinationOffset:0 destinationBytesPerRow:256 destinationBytesPerImage:8192 options:MTLBlitOptionDepthFromDepthStencil];
 [b copyFromTexture:depth sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(32,32,1) toBuffer:out destinationOffset:8192 destinationBytesPerRow:256 destinationBytesPerImage:8192 options:MTLBlitOptionStencilFromDepthStencil];
 [b endEncoding];[cb commit];[cb waitUntilCompleted];assert(cb.status==MTLCommandBufferStatusCompleted);
 NSMutableData* bytes=[NSMutableData dataWithBytes:out.contents length:16384];unsigned char c[4096];[color getBytes:c bytesPerRow:128 fromRegion:MTLRegionMake2D(0,0,32,32) mipmapLevel:0];[bytes appendBytes:c length:sizeof c];return bytes;
}
int main(){@autoreleasepool{
 assert(bces_depth_only_eligible("float4 main():SV_TARGET{return 0;}",0,0));
 const char* rejected[]={"SV_TARGET clip(0)","SV_TARGET discard", "SV_TARGET SV_Depth", "SV_TARGET SV_Coverage", "SV_TARGET RWTexture2D", "SV_TARGET InterlockedAdd"};
 for(unsigned i=0;i<sizeof rejected/sizeof *rejected;i++)assert(!bces_depth_only_eligible(rejected[i],0,0));
 assert(!bces_depth_only_eligible("SV_TARGET",1,0));assert(!bces_depth_only_eligible("SV_TARGET",0,1));assert(!bces_depth_only_eligible(NULL,0,0));
 id<MTLDevice> d=MTLCreateSystemDefaultDevice();assert(d);id<MTLCommandQueue> q=[d newCommandQueue];NSError* error=nil;
 NSString* source=@"#include <metal_stdlib>\nusing namespace metal;\nvertex float4 vs(uint i[[vertex_id]],constant float& z[[buffer(0)]]){float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};return float4(p[i],z,1);}\nfragment float4 fs(){return float4(1,0,0,1);}";
 id<MTLLibrary> lib=[d newLibraryWithSource:source options:nil error:&error];assert(lib);
 MTLRenderPipelineDescriptor* pd=[MTLRenderPipelineDescriptor new];pd.vertexFunction=[lib newFunctionWithName:@"vs"];pd.fragmentFunction=[lib newFunctionWithName:@"fs"];pd.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;pd.colorAttachments[0].writeMask=MTLColorWriteMaskNone;pd.depthAttachmentPixelFormat=MTLPixelFormatDepth32Float_Stencil8;pd.stencilAttachmentPixelFormat=MTLPixelFormatDepth32Float_Stencil8;
 id<MTLRenderPipelineState> ref=[d newRenderPipelineStateWithDescriptor:pd error:&error];assert(ref);pd.fragmentFunction=nil;id<MTLRenderPipelineState> fast=[d newRenderPipelineStateWithDescriptor:pd error:&error];assert(fast);
 unsigned fixtures=0,depth_modified=0,stencil_modified=0;
 for(unsigned w=0;w<2;w++)for(unsigned z=0;z<2;z++)for(unsigned mode=0;mode<3;mode++)for(unsigned op=0;op<4;op++){
  NSData* a=draw(d,q,ref,z?.8f:.2f,w,mode,op);NSData* b=draw(d,q,fast,z?.8f:.2f,w,mode,op);assert([a isEqual:b]);fixtures++;
  const unsigned char* bytes=a.bytes;float depth;memcpy(&depth,bytes+16*256+16*4,4);depth_modified+=depth!=.5f;stencil_modified+=bytes[8192+16*256+16]!=3;
 }
 assert(depth_modified&&stencil_modified);printf("PASS: %u exact color/depth/stencil GPU fixtures, %u changed depth, %u changed stencil; eligibility guards passed\n",fixtures,depth_modified,stencil_modified);
}}
