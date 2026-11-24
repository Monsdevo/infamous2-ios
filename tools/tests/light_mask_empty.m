#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <simd/simd.h>
#include <assert.h>
typedef struct {simd_float4 pos,col,oacbn,dir;} Light;
typedef struct {simd_float4 m[4],misc;Light l[128];} Params;
static double last_gpu_ms;
static NSData* run(id<MTLDevice> d,id<MTLCommandQueue> q,id<MTLComputePipelineState> p,id<MTLTexture> z,Params* params,unsigned width,unsigned height,unsigned offset){
 unsigned n=((width+31)/32)*((height+39)/40);id<MTLBuffer> out=[d newBufferWithLength:n*4 options:MTLResourceStorageModeShared];memset(out.contents,0xA5,n*4);
 uint32_t origin[2]={offset*32,offset*40},extent[2]={width,height};id<MTLCommandBuffer> cb=[q commandBuffer];id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];
 id<MTLBuffer> pb=[d newBufferWithBytes:params length:sizeof(*params) options:MTLResourceStorageModeShared];
 [e setComputePipelineState:p];[e setTexture:z atIndex:0];[e setBuffer:pb offset:0 atIndex:0];[e setBuffer:out offset:0 atIndex:1];[e setBytes:origin length:8 atIndex:2];[e setBytes:extent length:8 atIndex:3];[e dispatchThreadgroups:MTLSizeMake((width+31)/32,(height+39)/40,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];[e endEncoding];[cb commit];[cb waitUntilCompleted];assert(cb.status==MTLCommandBufferStatusCompleted);last_gpu_ms=(cb.GPUEndTime-cb.GPUStartTime)*1000;return [NSData dataWithBytes:out.contents length:n*4];
}
int main(int argc,char** argv){@autoreleasepool{
 assert(argc==2||argc==3||argc==4);id<MTLDevice> d=MTLCreateSystemDefaultDevice();assert(d);NSError* error=nil;MTLCompileOptions* opts=[MTLCompileOptions new];opts.fastMathEnabled=NO;
 NSString* source=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];assert(source);id<MTLLibrary> lib=[d newLibraryWithSource:source options:opts error:&error];if(!lib){fprintf(stderr,"%s\n",error.description.UTF8String);return 2;}
 id<MTLComputePipelineState> ref=[d newComputePipelineStateWithFunction:[lib newFunctionWithName:@"bces_light_tile_mask"] error:&error],fast=[d newComputePipelineStateWithFunction:[lib newFunctionWithName:@"bces_light_tile_mask_empty"] error:&error];assert(ref&&fast);id<MTLCommandQueue> q=[d newCommandQueue];unsigned cases=0,accepted=0,rejected=0;
 id<MTLFunction> boundsFn=[lib newFunctionWithName:@"bces_light_bounds_check"];id<MTLComputePipelineState> bounds=boundsFn?[d newComputePipelineStateWithFunction:boundsFn error:&error]:nil;unsigned boundsChecked=0,boundsFallback=0;
 if(argc==4){
  assert(!strcmp(argv[2],"fixture"));NSString* path=@(argv[3]);NSDictionary* meta=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[path stringByAppendingPathComponent:@"metadata.json"]] options:0 error:nil];assert(meta);
  NSData* constants=[NSData dataWithContentsOfFile:[path stringByAppendingPathComponent:@"params.bin"]],*pixels=[NSData dataWithContentsOfFile:[path stringByAppendingPathComponent:@"depth.raw"]];assert(constants.length==sizeof(Params));Params p;memcpy(&p,constants.bytes,sizeof p);
  unsigned w=[meta[@"width"] unsignedIntValue],h=[meta[@"height"] unsignedIntValue],row=[meta[@"bytes_per_row"] unsignedIntValue];assert(w&&h&&pixels.length==row*h);
  MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float width:w height:h mipmapped:NO];td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageShaderRead;id<MTLTexture> z=[d newTextureWithDescriptor:td];[z replaceRegion:MTLRegionMake2D(0,0,w,h) mipmapLevel:0 withBytes:pixels.bytes bytesPerRow:row];NSMutableArray* timings=[NSMutableArray new];NSData* reference=nil;
  for(unsigned trial=0;trial<10;trial++){
   NSData* a=run(d,q,ref,z,&p,w,h,0);double ms=last_gpu_ms;NSData* b=run(d,q,fast,z,&p,w,h,0);assert([a isEqual:b]);if(!reference)reference=a;
   [timings addObject:@{@"reference_ms":@(ms),@"candidate_ms":@(last_gpu_ms)}];
  }
  if(bounds){NSData* checks=run(d,q,bounds,z,&p,w,h,0);const uint32_t* v=checks.bytes;for(unsigned i=0;i<checks.length/4;i++){assert(v[i]==1||v[i]==2);if(v[i]==1)boundsChecked++;else boundsFallback++;}}
  const uint32_t* words=reference.bytes;for(unsigned i=0;i<reference.length/4;i++){assert(words[i]<=1);if(words[i])accepted++;else rejected++;}
  NSDictionary* result=@{@"valid":@YES,@"tiles":@(reference.length/4),@"accepted":@(accepted),@"rejected":@(rejected),@"lights":@(p.misc.y),@"timings":timings,@"bounds_checked":@(boundsChecked),@"bounds_fallback":@(boundsFallback),@"scope":@"Exact captured game input; isolated kernel timings, not game FPS"};NSData* data=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];fwrite(data.bytes,1,data.length,stdout);puts("");return 0;
 }
 for(unsigned variant=0;variant<(bounds?8u:1u);variant++)for(unsigned size=0;size<2;size++)for(unsigned pattern=0;pattern<6;pattern++)for(unsigned nl=0;nl<3;nl++)for(unsigned offset=0;offset<2;offset++){
  unsigned width=size?37:64,height=size?53:80;float* depths=calloc(width*height,4);
  for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
   BOOL geometry=pattern==1 || (pattern==2&&((x+y)%2)) || (pattern==3&&x%32==0&&y%40==0) || (pattern==4&&x==width-1&&y==height-1) || (pattern==5&&x<32&&y<40);
   depths[y*width+x]=geometry?.5f:1.f;
  }
  MTLTextureDescriptor* td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float width:width height:height mipmapped:NO];td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageShaderRead;id<MTLTexture> z=[d newTextureWithDescriptor:td];[z replaceRegion:MTLRegionMake2D(0,0,width,height) mipmapLevel:0 withBytes:depths bytesPerRow:width*4];free(depths);
  Params p={0};p.m[0]=(simd_float4){1,0,0,0};p.m[1]=(simd_float4){0,1,0,0};p.m[2]=(simd_float4){0,0,1,0};p.m[3]=(simd_float4){0,0,0,1};p.misc=(simd_float4){1,nl==2?4:nl,1280,720};
  for(unsigned k=0;k<4;k++){p.l[k].pos=(simd_float4){0,0,0,1};p.l[k].col=(simd_float4){1,1,1,0};p.l[k].oacbn=(simd_float4){k?0.001f:100,-2.5,.5,0};p.l[k].dir=(simd_float4){0,0,-1,0};}
  if(variant){
   p.m[0]=(simd_float4){.7f,-.2f,.125f,variant==3?.05f:0};
   p.m[1]=(simd_float4){-.15f,.8f,.0625f,variant==3?-.1f:0};
   p.m[2]=(simd_float4){-.4f,.1f,.9f,variant==4?-.5f:0};
   p.m[3]=(simd_float4){-.3f,.2f,-.8f,variant==2?-1.f:variant==3?0.f:1.f};
   if(variant>=5){uint32_t bits=variant==5?1u:variant==6?0x7fffffffu:0xff800001u;float f;memcpy(&f,&bits,4);p.m[0].x=f;}
   for(unsigned k=0;k<4;k++){p.l[k].pos=(simd_float4){.1f*k,-.2f*k,.3f*k,1};p.l[k].oacbn.x=k?.01f:variant==1?-2.f:2.f;}
  }
  NSData* a=run(d,q,ref,z,&p,width,height,offset),*b=run(d,q,fast,z,&p,width,height,offset);assert([a isEqual:b]);cases++;
  if(bounds){NSData* checks=run(d,q,bounds,z,&p,width,height,offset);const uint32_t* v=checks.bytes;for(unsigned i=0;i<checks.length/4;i++){assert(v[i]==1||v[i]==2);if(v[i]==1)boundsChecked++;else boundsFallback++;}}
  const uint32_t* masks=a.bytes;for(unsigned i=0;i<a.length/4;i++){assert(masks[i]<=1);if(masks[i])accepted++;else rejected++;}
 }
 assert(accepted&&rejected);
 if(bounds)printf("PASS bounds: %u contained tiles, %u conservative fallbacks\n",boundsChecked,boundsFallback);
 if(argc==3){
  id<MTLFunction> fn=[lib newFunctionWithName:@"bces_mask_compare"];assert(fn);id<MTLComputePipelineState> cp=[d newComputePipelineStateWithFunction:fn error:&error];assert(cp);
  uint32_t a[]={0,1,0,1},b[]={0,1,1,0},count=4;id<MTLBuffer> ra=[d newBufferWithBytes:a length:sizeof a options:MTLResourceStorageModeShared],rb=[d newBufferWithBytes:b length:sizeof b options:MTLResourceStorageModeShared],result=[d newBufferWithLength:8 options:MTLResourceStorageModeShared];memset(result.contents,0,8);
  id<MTLCommandBuffer> cb=[q commandBuffer];id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];[e setComputePipelineState:cp];[e setBuffer:ra offset:0 atIndex:0];[e setBuffer:rb offset:0 atIndex:1];[e setBuffer:result offset:0 atIndex:2];[e setBytes:&count length:4 atIndex:3];[e dispatchThreads:MTLSizeMake(4,1,1) threadsPerThreadgroup:MTLSizeMake(4,1,1)];[e endEncoding];[cb commit];[cb waitUntilCompleted];assert(cb.status==MTLCommandBufferStatusCompleted);const uint32_t* r=result.contents;assert(r[0]==2&&r[1]==4);puts("PASS GPU comparison negative fixture: exactly 2 mismatches, 4 comparisons");
 }
 printf("PASS %u exact GPU mask fixtures; %u accepted and %u rejected tiles; background/mixed/sparse/partial/origin/light-count cases\n",cases,accepted,rejected);
}}
