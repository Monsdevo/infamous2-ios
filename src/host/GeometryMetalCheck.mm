#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "SkinningSnapshot.h"
#include <chrono>
#include <cstdio>
int main(int argc,char**argv){@autoreleasepool{
    bool parallel=argc>1&&!strcmp(argv[1],"--parallel");if(parallel){argv++;argc--;}
    if(argc<2)return 2;
    id<MTLDevice> device=MTLCreateSystemDefaultDevice();if(!device){fprintf(stderr,"No Metal device\n");return 3;}
    NSError*error=nil;NSString*source=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:&error];
    MTLCompileOptions*options=[MTLCompileOptions new];options.mathMode=MTLMathModeSafe;
    id<MTLLibrary> library=[device newLibraryWithSource:source options:options error:&error];
    if(!library){fprintf(stderr,"MSL compile: %s\n",error.description.UTF8String);return 4;}
    id<MTLCommandQueue> queue=[device newCommandQueue];
    id<MTLComputePipelineState> pipelines[2];
    for(unsigned i=0;i<2;i++){
        pipelines[i]=[device newComputePipelineStateWithFunction:[library newFunctionWithName:i?@"geometry_cull":@"geometry_skin"] error:&error];
        if(!pipelines[i]){fprintf(stderr,"PSO compile: %s\n",error.description.UTF8String);return 5;}
    }
    id<MTLComputePipelineState> stages[4];NSString*names[4]={@"geometry_skin_control",@"geometry_snapshot",@"geometry_skin_parallel",@"geometry_hazards"};
    if(parallel)for(unsigned i=0;i<4;i++){stages[i]=[device newComputePipelineStateWithFunction:[library newFunctionWithName:names[i]] error:&error];if(!stages[i]){fprintf(stderr,"parallel PSO: %s\n",error.description.UTF8String);return 5;}}
    printf("PASS MSL skinning/culling pipelines on %s\n",device.name.UTF8String);
    for(int arg=2;arg<argc;arg++){@autoreleasepool{
        FILE*f=fopen(argv[arg],"rb");if(!f)return 6;SkinningSnapshot*s=(SkinningSnapshot*)malloc(sizeof *s);bool loaded=s&&fread(s,sizeof *s,1,f)==1;fclose(f);if(!loaded)return 7;
        if(s->magic!=0x534b494e||s->context_size!=sizeof(spu_context))return 8;
        unsigned route=s->version==2?1:0;
        auto begin=std::chrono::steady_clock::now();
        id<MTLBuffer> regs=[device newBufferWithBytes:s->input.gpr length:2048 options:MTLResourceStorageModeShared];
        id<MTLBuffer> ls=[device newBufferWithBytes:s->input_ls length:SPU_LS_SIZE options:MTLResourceStorageModeShared];
        id<MTLBuffer> dirty=[device newBufferWithLength:2048 options:MTLResourceStorageModeShared];memset(dirty.contents,0,2048);
        uint32_t parameters[32]={s->input.gpr[0]._u32[0],0,0xD0A8,0};id<MTLBuffer> control=[device newBufferWithBytes:parameters length:sizeof parameters options:MTLResourceStorageModeShared];
        id<MTLCommandBuffer> command=[queue commandBuffer];id<MTLComputeCommandEncoder> encoder=[command computeCommandEncoder];
        [encoder setComputePipelineState:pipelines[route]];[encoder setBuffer:regs offset:0 atIndex:0];[encoder setBuffer:ls offset:0 atIndex:1];[encoder setBuffer:dirty offset:0 atIndex:2];[encoder setBuffer:control offset:0 atIndex:3];
        if(parallel&&!route){
            id<MTLBuffer> completed=[device newBufferWithLength:2048 options:MTLResourceStorageModeShared];
            id<MTLBuffer> snapshot=[device newBufferWithLength:SPU_LS_SIZE options:MTLResourceStorageModeShared];
            id<MTLBuffer> reads=[device newBufferWithLength:65536 options:MTLResourceStorageModeShared],writes=[device newBufferWithLength:65536 options:MTLResourceStorageModeShared];
            [encoder setBuffer:reads offset:0 atIndex:6];[encoder setBuffer:writes offset:0 atIndex:7];
            [encoder setBuffer:completed offset:0 atIndex:4];[encoder setBuffer:snapshot offset:0 atIndex:5];
            for(unsigned phase=0;phase<32;phase++){
                [encoder setComputePipelineState:stages[0]];[encoder dispatchThreads:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];[encoder memoryBarrierWithScope:MTLBarrierScopeBuffers];
                [encoder setComputePipelineState:stages[1]];[encoder dispatchThreadgroupsWithIndirectBuffer:control indirectBufferOffset:48 threadsPerThreadgroup:MTLSizeMake(256,1,1)];[encoder memoryBarrierWithScope:MTLBarrierScopeBuffers];
                [encoder setComputePipelineState:stages[2]];[encoder dispatchThreadgroupsWithIndirectBuffer:control indirectBufferOffset:32 threadsPerThreadgroup:MTLSizeMake(64,1,1)];[encoder memoryBarrierWithScope:MTLBarrierScopeBuffers];
                [encoder setComputePipelineState:stages[3]];[encoder dispatchThreads:MTLSizeMake(16384,1,1) threadsPerThreadgroup:MTLSizeMake(256,1,1)];[encoder memoryBarrierWithScope:MTLBarrierScopeBuffers];
            }
            [encoder setComputePipelineState:stages[0]];[encoder dispatchThreads:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];
        }else [encoder dispatchThreads:MTLSizeMake(1,1,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];[encoder endEncoding];[command commit];[command waitUntilCompleted];
        auto end=std::chrono::steady_clock::now();uint32_t*p=(uint32_t*)control.contents;
        if(command.status!=MTLCommandBufferStatusCompleted||p[1]!=1){fprintf(stderr,"GPU failed %s status=%lu pc=%x phase=%u loop=%x n=%u hazard=%u source=%x quad=%x r=%u w=%u\n",argv[arg],(unsigned long)command.status,p[2],p[1],p[4],p[5],p[16],p[17],p[18]*16,p[19],p[20]);return 9;}
        bool okay=!memcmp(regs.contents,s->output.gpr,2048)&&!memcmp(ls.contents,s->output_ls,SPU_LS_SIZE)&&p[2]==s->output.pc;
        if(!okay){
            u128*r=(u128*)regs.contents;for(unsigned i=0;i<128;i++)if(memcmp(r+i,s->output.gpr+i,16))fprintf(stderr,"GPR %u got=%08x expected=%08x\n",i,r[i]._u32[0],s->output.gpr[i]._u32[0]);
            unsigned n=0;uint8_t*l=(uint8_t*)ls.contents;for(unsigned i=0;i<SPU_LS_SIZE;i++)if(l[i]!=s->output_ls[i]){if(n++<8)fprintf(stderr,"LS %x got=%02x expected=%02x\n",i,l[i],s->output_ls[i]);}fprintf(stderr,"LS diff bytes=%u\n",n);return 10;
        }
        uint32_t*d=(uint32_t*)dirty.contents;for(unsigned i=0;i<SPU_LS_SIZE;i++)if(s->input_ls[i]!=s->output_ls[i]&&!(d[i>>9]&(1u<<((i>>4)&31))))return 11;
        printf("PASS %s root=%s full GPR/LS/PC + dirty bitmap; steps=%u host_total_ms=%.3f GPU_ms=%.3f (Mac, not iPhone)\n",argv[arg],route?"culling":"skinning",p[3],std::chrono::duration<double,std::milli>(end-begin).count(),1000*(command.GPUEndTime-command.GPUStartTime));
        free(s);
    }}return 0;
}}
