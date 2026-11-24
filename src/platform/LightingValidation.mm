#include "LightingValidation.h"
#include "LightingTile.h"
#include "spu_context.h"
#include "rsx_draw_engine.h"
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <atomic>
#include <memory>
#include <algorithm>
#include <cmath>
#include "lighting_validation_msl.inc"

namespace {
struct Capture {
    LightingTile tile;
    uint32_t spu_id,image,pc;
    uint8_t before[SPU_LS_SIZE],after[SPU_LS_SIZE],gpr[2048];
};
std::unique_ptr<Capture> captures[3];
std::atomic<unsigned> claimed{0},completed{0},rejectedZeroOutput{0};
std::atomic<bool> enabled{false};
bool litOnly=false;
NSString* directory;
NSString* reportPath;
NSString* session;
dispatch_queue_t worker;
id<MTLDevice> device;
id<MTLCommandQueue> queue;
id<MTLRenderPipelineState> pipeline;
id<MTLComputePipelineState> maskPipeline;
NSMutableArray* results;
NSString* referenceFixture;

float bef(const uint8_t* p) {uint32_t u=light_be32(p);float f;memcpy(&f,&u,4);return f;}
float half_be(const uint8_t* p) {
    unsigned h=unsigned(p[0])<<8|p[1],e=(h>>10)&31,m=h&1023;
    float v=e==0?float(m)/1024/16384:e==31?65504.0f:ldexpf(1+float(m)/1024,int(e)-15);
    return h>>15?-v:v;
}
rsx_gpu_light_params params(const Capture& c) {
    rsx_gpu_light_params p={};const auto& t=c.tile;const uint8_t* f=c.before+t.frame;
    for(int i=0;i<16;i++)p.m[i]=bef(f+0x10+i*4);
    p.scale=bef(f+0x98);p.width=t.full_w;p.height=t.full_h;
    unsigned n=0;
    for(unsigned i=0;i<t.count;i++) {
        const uint8_t* r=c.before+t.lights+i*48;unsigned type=light_be32(r+0x14);
        if(type!=1 && type!=2)continue;
        auto& l=p.light[n++];l.type=type;
        for(int k=0;k<3;k++){l.pos[k]=bef(r+k*4);l.col[k]=half_be(r+0xc+k*2);l.dir[k]=half_be(r+0x28+k*2);}
        l.inner=half_be(r+0x20);l.outer=half_be(r+0x22);l.cone_a=half_be(r+0x24);l.cone_b=half_be(r+0x26);l.near_=half_be(r+0x2e);
    }
    p.count=n;return p;
}
void save(NSString* path,const void* bytes,NSUInteger size) {
    NSError* error=nil;
    if(![[NSData dataWithBytes:bytes length:size] writeToFile:path options:NSDataWritingAtomic error:&error])
        fprintf(stderr,"[lighting validation] write failed: %s\n",error.description.UTF8String);
}
bool prepareGPU(NSString** failure) {
    if(pipeline && maskPipeline)return true;
    device=MTLCreateSystemDefaultDevice();if(!device){*failure=@"Metal device unavailable";return false;}
    queue=[device newCommandQueue];
    MTLCompileOptions* options=[MTLCompileOptions new];options.fastMathEnabled=NO;
    NSError* error=nil;
    id<MTLLibrary> lib=[device newLibraryWithSource:[NSString stringWithUTF8String:lighting_validation_msl] options:options error:&error];
    if(!lib){*failure=error.description?:@"shader compilation failed";return false;}
    auto d=[MTLRenderPipelineDescriptor new];d.vertexFunction=[lib newFunctionWithName:@"capture_vs"];d.fragmentFunction=[lib newFunctionWithName:@"eng_light_fs"];
    for(int i=0;i<2;i++)d.colorAttachments[i].pixelFormat=MTLPixelFormatRGBA8Unorm;
    pipeline=[device newRenderPipelineStateWithDescriptor:d error:&error];
    maskPipeline=[device newComputePipelineStateWithFunction:[lib newFunctionWithName:@"bces_light_tile_mask"] error:&error];
    if(!pipeline || !maskPipeline || !queue){*failure=error.description?:@"pipeline/queue unavailable";return false;}return true;
}
void compare(unsigned index,const Capture& c) {
    @autoreleasepool {
        const auto& t=c.tile;
        NSString* folder=[directory stringByAppendingPathComponent:[NSString stringWithFormat:@"tile-%u",index]];
        [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
        save([folder stringByAppendingPathComponent:@"before-ls.bin"],c.before,sizeof c.before);
        save([folder stringByAppendingPathComponent:@"after-ls.bin"],c.after,sizeof c.after);
        save([folder stringByAppendingPathComponent:@"before-gpr.bin"],c.gpr,sizeof c.gpr);
        NSMutableDictionary* result=[@{@"tile":@(index),@"x":@(t.x),@"y":@(t.y),@"width":@(t.w),@"height":@(t.h),@"full_width":@(t.full_w),@"full_height":@(t.full_h),@"lights":@(t.count),@"parameter_lsa":@(t.parameter),@"spu_id":@(c.spu_id),@"image_id":@(c.image),@"guest_pc":@(c.pc),@"frame_lsa":@(t.frame),@"lights_lsa":@(t.lights),@"normal_lsa":@(t.normal),@"depth_lsa":@(t.depth),@"diffuse_lsa":@(t.diffuse),@"specular_lsa":@(t.specular),@"lit_only":@(litOnly),@"fast_math":@NO,@"game_uses":@"original SPU",@"status":@"captured"} mutableCopy];
        if(referenceFixture)result[@"reference_fixture"]=referenceFixture;
        NSString* failure=nil;
        if(prepareGPU(&failure)) {
            const unsigned n=t.w*t.h;std::unique_ptr<uint8_t[]> normals(new uint8_t[n*4]);std::unique_ptr<float[]> depth(new float[n]);
            for(unsigned i=0;i<n;i++) {
                const uint8_t* a=c.before+t.normal+i*4;
                normals[i*4]=a[1];normals[i*4+1]=a[2];normals[i*4+2]=a[3];normals[i*4+3]=a[0];
                const uint8_t* z=c.before+t.depth+i*4;depth[i]=float(unsigned(z[0])<<16|unsigned(z[1])<<8|z[2])/16777215.0f;
            }
            auto td=[MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:t.w height:t.h mipmapped:NO];td.storageMode=MTLStorageModeShared;td.usage=MTLTextureUsageShaderRead;
            id<MTLTexture> normal=[device newTextureWithDescriptor:td];td.pixelFormat=MTLPixelFormatR32Float;id<MTLTexture> z=[device newTextureWithDescriptor:td];
            td.pixelFormat=MTLPixelFormatRGBA8Unorm;td.storageMode=MTLStorageModePrivate;td.usage=MTLTextureUsageRenderTarget;
            id<MTLTexture> out[2]={[device newTextureWithDescriptor:td],[device newTextureWithDescriptor:td]};
            const unsigned row=(t.w*4+255)&~255u;id<MTLBuffer> readback[2]={[device newBufferWithLength:row*t.h options:MTLResourceStorageModeShared],[device newBufferWithLength:row*t.h options:MTLResourceStorageModeShared]};
            if(!normal || !z || !out[0] || !out[1] || !readback[0] || !readback[1])failure=@"validation texture/buffer allocation failed";
            else {
                MTLRegion region=MTLRegionMake2D(0,0,t.w,t.h);[normal replaceRegion:region mipmapLevel:0 withBytes:normals.get() bytesPerRow:t.w*4];[z replaceRegion:region mipmapLevel:0 withBytes:depth.get() bytesPerRow:t.w*4];
                auto pass=[MTLRenderPassDescriptor renderPassDescriptor];for(int k=0;k<2;k++){pass.colorAttachments[k].texture=out[k];pass.colorAttachments[k].loadAction=MTLLoadActionClear;pass.colorAttachments[k].storeAction=MTLStoreActionStore;}
                rsx_gpu_light_params p=params(c);uint32_t origin[2]={t.x*t.w,t.y*t.h},extent[2]={t.w,t.h};
                auto pb=[device newBufferWithBytes:&p length:sizeof p options:MTLResourceStorageModeShared];
                auto mask=[device newBufferWithLength:4*((t.w+31)/32)*((t.h+39)/40) options:MTLResourceStorageModeShared];
                auto cb=[queue commandBuffer];
                if(!pb || !mask)failure=@"validation parameter/mask allocation failed";
                if(!failure) {
                    auto compute=[cb computeCommandEncoder];
                    [compute setComputePipelineState:maskPipeline];[compute setTexture:z atIndex:0];
                    [compute setBuffer:pb offset:0 atIndex:0];[compute setBuffer:mask offset:0 atIndex:1];
                    [compute setBytes:origin length:sizeof origin atIndex:2];[compute setBytes:extent length:sizeof extent atIndex:3];
                    [compute dispatchThreadgroups:MTLSizeMake((t.w+31)/32,(t.h+39)/40,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];
                    [compute endEncoding];
                }
                auto encoder=[cb renderCommandEncoderWithDescriptor:pass];
                if(!failure) {
                    [encoder setRenderPipelineState:pipeline];[encoder setFragmentTexture:normal atIndex:0];[encoder setFragmentTexture:z atIndex:1];
                    [encoder setFragmentBuffer:pb offset:0 atIndex:0];[encoder setFragmentBuffer:mask offset:0 atIndex:1];
                    [encoder setFragmentBytes:origin length:sizeof origin atIndex:2];
                    [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
                }
                [encoder endEncoding];auto blit=[cb blitCommandEncoder];
                for(int k=0;k<2;k++)[blit copyFromTexture:out[k] sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(t.w,t.h,1) toBuffer:readback[k] destinationOffset:0 destinationBytesPerRow:row destinationBytesPerImage:row*t.h];
                [blit endEncoding];[cb commit];[cb waitUntilCompleted]; // Detached validation queue only, never game's renderer queue.
                if(cb.status!=MTLCommandBufferStatusCompleted)failure=cb.error.description?:@"validation GPU command failed";
                if(!failure) {
                    result[@"tile_mask"]=@(((const uint32_t*)mask.contents)[0]);
                    NSMutableArray* comparisons=[NSMutableArray new];
                    for(int k=0;k<2;k++) {
                        const uint8_t* ref=c.after+(k?t.specular:t.diffuse);const uint8_t* gpu=(const uint8_t*)readback[k].contents;
                        unsigned changed=0,maxError=0,nonzero=0,alphaChanged=0,alphaMax=0;uint64_t sum=0;std::unique_ptr<uint8_t[]> packed(new uint8_t[n*4]);
                        for(unsigned y=0;y<t.h;y++)for(unsigned x=0;x<t.w;x++)for(unsigned ch=0;ch<4;ch++) {
                            const unsigned i=(y*t.w+x)*4+ch;uint8_t expected=ref[(y*t.w+x)*4+(ch==3?0:ch+1)],actual=gpu[y*row+x*4+ch];
                            packed[i]=actual;unsigned d=unsigned(abs(int(actual)-int(expected)));changed+=d!=0;nonzero+=expected!=0;maxError=std::max(maxError,d);sum+=d;if(ch==3){alphaChanged+=d!=0;alphaMax=std::max(alphaMax,d);}
                        }
                        save([folder stringByAppendingPathComponent:k?@"metal-specular.rgba":@"metal-diffuse.rgba"],packed.get(),n*4);
                        save([folder stringByAppendingPathComponent:k?@"spu-specular.argb":@"spu-diffuse.argb"],ref,n*4);
                        [comparisons addObject:@{@"buffer":k?@"specular":@"diffuse",@"changed_bytes":@(changed),@"total_bytes":@(n*4),@"reference_nonzero_bytes":@(nonzero),@"max_error":@(maxError),@"mean_error":@(double(sum)/(n*4)),@"bit_exact":@(changed==0),@"alpha_changed_bytes":@(alphaChanged),@"alpha_max_error":@(alphaMax)}];
                    }
                    result[@"status"]=@"compared";result[@"comparison"]=comparisons;
                    result[@"gpu_ms"]=@((cb.GPUEndTime-cb.GPUStartTime)*1000);
                }
            }
        }
        if(failure){result[@"status"]=@"error";result[@"error"]=failure;}
        NSData* data=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];[data writeToFile:[folder stringByAppendingPathComponent:@"metadata.json"] atomically:YES];
        [results addObject:result];
        NSDictionary* report=@{@"session":session,@"build":NSBundle.mainBundle.infoDictionary[@"CFBundleVersion"]?:@"host-test",@"fixture_directory":directory,@"mode":@"SPU reference with bounded detached Metal comparisons",@"optimization_enabled":@NO,@"source":@"pinned eng_light_fs; tile origin adapter; fast math disabled",@"completed":@(results.count),@"samples":results};
        [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil] writeToFile:reportPath atomically:YES];
        fprintf(stderr,"[lighting validation] tile %u status=%s; original SPU remains active\n",index,[result[@"status"] UTF8String]);
        completed.fetch_add(1);
    }
}
}
extern "C" void bces_light_validation_configure(const char* documents,int on) {
    if(!on || !documents)return;
    litOnly=on>1;
    NSString* root=[[NSString stringWithUTF8String:documents] stringByAppendingPathComponent:@"lighting-validation"];
    session=NSUUID.UUID.UUIDString;
    directory=[root stringByAppendingPathComponent:session];
    reportPath=[root stringByAppendingPathComponent:@"report.json"];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary* waiting=@{@"session":session,@"fixture_directory":directory,@"status":@"waiting for eligible lighting tiles",@"completed":@0,@"optimization_enabled":@NO};
    [[NSJSONSerialization dataWithJSONObject:waiting options:NSJSONWritingPrettyPrinted error:nil] writeToFile:reportPath atomically:YES];
    results=[NSMutableArray new];worker=dispatch_queue_create("infamous.lighting.validation",dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL,QOS_CLASS_UTILITY,0));
    for(auto& c:captures)c=std::make_unique<Capture>();enabled=true;
}
extern "C" unsigned bces_light_validation_begin(void* opaque,uint32_t target) {
    if(!enabled.load(std::memory_order_relaxed) || claimed.load(std::memory_order_relaxed)==7 || target!=0x4ac8)return 0;
    const auto* ctx=(const spu_context*)opaque;LightingTile tile;
    if(!light_tile_decode(ctx->ls,ctx->gpr[3]._u32[0],tile))return 0;
    // The lit-only run must exercise actual light arithmetic and occupied depth,
    // not repeat the zero-light/sky smoke test from the first launch.
    if(litOnly) {
        if(!tile.count)return 0;
        bool occupied=false;
        for(unsigned i=0;i<tile.w*tile.h;i++) {
            const uint8_t* z=ctx->ls+tile.depth+4*i;
            if(z[0]!=255 || z[1]!=255 || z[2]!=255){occupied=true;break;}
        }
        if(!occupied)return 0;
    }
    unsigned nx=tile.full_w/tile.w,ny=tile.full_h/tile.h,index=3;
    if(tile.x==0 && tile.y==0)index=0;
    else if(tile.x==nx/2 && tile.y==ny/2)index=1;
    else if(tile.x==nx-1 && tile.y==ny-1)index=2;
    if(index==3 || (claimed.fetch_or(1u<<index)&(1u<<index)))return 0;
    auto& c=*captures[index];c.tile=tile;c.spu_id=ctx->spu_id;c.image=ctx->image_id;c.pc=ctx->pc;
    memcpy(c.before,ctx->ls,SPU_LS_SIZE);memcpy(c.gpr,ctx->gpr,sizeof c.gpr);
    return index+1;
}
extern "C" void bces_light_validation_end(void* opaque,unsigned token) {
    if(!token || token>3)return;const auto* ctx=(const spu_context*)opaque;unsigned index=token-1;
    if(litOnly) {
        const auto& t=captures[index]->tile;
        bool nonzero=false;
        for(unsigned i=0;i<t.w*t.h*4;i++)
            if(ctx->ls[t.diffuse+i] || ctx->ls[t.specular+i]){nonzero=true;break;}
        if(!nonzero) {
            rejectedZeroOutput.fetch_add(1,std::memory_order_relaxed);
            // No worker owns this slot: a later genuinely lit tile may claim it.
            claimed.fetch_and(~(1u<<index),std::memory_order_release);return;
        }
    }
    memcpy(captures[index]->after,ctx->ls,SPU_LS_SIZE);
    dispatch_async(worker,^{compare(index,*captures[index]);});
}
extern "C" unsigned bces_light_validation_completed(void) {return completed.load();}

extern "C" unsigned bces_light_validation_rejected_zero_output(void) {return rejectedZeroOutput.load();}

extern "C" void bces_light_validation_replay(const char* documents) {
    bces_light_validation_configure(documents,1);
    enabled.store(false); // This mode only replays files; never captures a running job.
    NSString* fixtures=[[NSString stringWithUTF8String:documents] stringByAppendingPathComponent:@"lighting-test-fixtures"];
    dispatch_async(worker,^{ @autoreleasepool {
        NSArray* names=[[NSFileManager.defaultManager contentsOfDirectoryAtPath:fixtures error:nil] sortedArrayUsingSelector:@selector(compare:)];
        unsigned index=0;
        for(NSString* name in names) {
            if(index>=16)break; // At most 16 bounded fixtures, no unbounded file import.
            if([name hasPrefix:@"."])continue;
            NSString* dir=[fixtures stringByAppendingPathComponent:name];
            NSData* before=[NSData dataWithContentsOfFile:[dir stringByAppendingPathComponent:@"before-ls.bin"]];
            NSData* after=[NSData dataWithContentsOfFile:[dir stringByAppendingPathComponent:@"after-ls.bin"]];
            NSData* gpr=[NSData dataWithContentsOfFile:[dir stringByAppendingPathComponent:@"before-gpr.bin"]];
            NSData* metadata=[NSData dataWithContentsOfFile:[dir stringByAppendingPathComponent:@"metadata.json"]];
            if(before.length!=SPU_LS_SIZE || after.length!=SPU_LS_SIZE || gpr.length!=2048 || !metadata)continue;
            NSDictionary* meta=[NSJSONSerialization JSONObjectWithData:metadata options:0 error:nil];
            auto c=std::make_unique<Capture>();
            memcpy(c->before,before.bytes,SPU_LS_SIZE);memcpy(c->after,after.bytes,SPU_LS_SIZE);memcpy(c->gpr,gpr.bytes,2048);
            uint32_t parameter=0;memcpy(&parameter,c->gpr+3*16,4);
            if(!light_tile_decode(c->before,parameter,c->tile))continue;
            c->spu_id=[meta[@"spu_id"] unsignedIntValue];c->image=[meta[@"image_id"] unsignedIntValue];c->pc=[meta[@"guest_pc"] unsignedIntValue];
            referenceFixture=name;
            compare(index++,*c);
        }
        referenceFixture=nil;
    }});
}
