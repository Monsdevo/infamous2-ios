#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "GeometryMetalBatches.h"
#include "geometry_batches_msl.inc"
#include <atomic>
#include <memory>
#include <chrono>
#include <vector>
extern "C" void bces_geometry_math_probe(uint32_t*,uint32_t*,unsigned);
namespace {
using Clock=std::chrono::steady_clock;
uint64_t ns(Clock::time_point begin){return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin).count();}
struct Shared {
 std::atomic<unsigned> state{0},stage{0},slots{0},flight{0};std::atomic<bool> native_math{false};
 id<MTLDevice> device;id<MTLComputePipelineState> compute[7];
 bool probe(id<MTLLibrary>library,bool require_rne){
  NSError*error=nil;id<MTLComputePipelineState>pso=[device newComputePipelineStateWithFunction:[library newFunctionWithName:@"geometry_math_probe"] error:&error];if(!pso)return false;
  const unsigned n=4096;std::vector<uint32_t> input(n*3),expected(n*6);bces_geometry_math_probe(input.data(),expected.data(),n);
  id<MTLBuffer> in=[device newBufferWithBytes:input.data() length:input.size()*4 options:MTLResourceStorageModeShared];id<MTLBuffer> out=[device newBufferWithLength:(n*6+1)*4 options:MTLResourceStorageModeShared];
  id<MTLCommandQueue>q=[device newCommandQueue];if(!in||!out||!q)return false;id<MTLCommandBuffer>cmd=[q commandBuffer];id<MTLComputeCommandEncoder>enc=[cmd computeCommandEncoder];if(!enc)return false;
  [enc setComputePipelineState:pso];[enc setBuffer:in offset:0 atIndex:0];[enc setBuffer:out offset:0 atIndex:1];[enc setBytes:&n length:sizeof n atIndex:2];[enc dispatchThreads:MTLSizeMake(n,1,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];[enc endEncoding];[cmd commit];[cmd waitUntilCompleted];
  if(cmd.status!=MTLCommandBufferStatusCompleted||memcmp(out.contents,expected.data(),expected.size()*4))return false;
  return !require_rne||((uint32_t*)out.contents)[n*6]==0x3f800002;
 }
 bool prepare(){@autoreleasepool{
  device=MTLCreateSystemDefaultDevice();if(!device)return false;NSError*error=nil;
  MTLCompileOptions*options=[MTLCompileOptions new];if(@available(iOS 18.0,macOS 15.0,*)){options.mathMode=MTLMathModeSafe;options.mathFloatingPointFunctions=MTLMathFloatingPointFunctionsPrecise;}else options.fastMathEnabled=NO;
  stage=1;id<MTLLibrary> library=[device newLibraryWithSource:@(bces_geometry_batches_msl) options:options error:&error];
  if(!library){NSLog(@"Geometry batch library: %@",error);return false;}
  stage=2;bool native=probe(library,true);
  if(!native){stage=3;options.preprocessorMacros=@{@"BCES_GEOMETRY_INTEGER_ONLY":@1};library=[device newLibraryWithSource:@(bces_geometry_batches_msl) options:options error:&error];if(!library||!probe(library,false))return false;}
  native_math=native;
  NSString*names[7]={@"geometry_batch_d800",@"geometry_batch_d5b0",@"geometry_batch_da28",@"geometry_batch_dce0",@"geometry_batch_df20",@"geometry_batch_7030",@"geometry_batch_a650"};
  for(unsigned i=0;i<7;i++){stage=10+i;compute[i]=[device newComputePipelineStateWithFunction:[library newFunctionWithName:names[i]] error:&error];if(!compute[i]){NSLog(@"Geometry batch pipeline %@: %@",names[i],error);return false;}}return true;
 }}
} shared;
struct Slot {
 id<MTLCommandQueue> queue;id<MTLBuffer> seed,ls,output,hashes,parameters,states;
 bool leased=false;
 bool prepare(){
  if(queue)return seed&&ls&&parameters&&states;unsigned n=shared.slots.fetch_add(1);if(n>=8){shared.slots--;return false;}leased=true;
  queue=[shared.device newCommandQueue];queue.label=@"Geometry worker batch";
  seed=[shared.device newBufferWithLength:2048 options:MTLResourceStorageModeShared];ls=[shared.device newBufferWithLength:SPU_LS_SIZE options:MTLResourceStorageModeShared];
  parameters=[shared.device newBufferWithLength:16 options:MTLResourceStorageModeShared];states=[shared.device newBufferWithLength:BCES_BATCH_MAX_ITERATIONS*48 options:MTLResourceStorageModeShared];
  return queue&&seed&&ls&&parameters&&states;
 }
 ~Slot(){if(leased)shared.slots--;}
 bool ensure(NSUInteger output_bytes,NSUInteger hash_bytes){
  if(!output||output.length<output_bytes)output=[shared.device newBufferWithLength:output_bytes options:MTLResourceStorageModeShared];
  if(!hashes||hashes.length<hash_bytes)hashes=[shared.device newBufferWithLength:hash_bytes options:MTLResourceStorageModeShared];
  return output&&hashes;
 }
};
thread_local std::unique_ptr<Slot> slot;
struct Flight {~Flight(){shared.flight--;}};
}
extern "C" void bces_batch_metal_prepare(void){
 unsigned expected=0;if(!shared.state.compare_exchange_strong(expected,1))return;
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{bool okay=shared.prepare();shared.stage=okay?20:21;shared.state=okay?2:3;});
}
extern "C" unsigned bces_batch_metal_state(void){return shared.state.load();}
extern "C" unsigned bces_batch_metal_compile_stage(void){return shared.stage.load();}
extern "C" int bces_batch_native_math_enabled(void){return shared.native_math.load();}
extern "C" int bces_batch_metal_run(const BCESBatchPlan*p,const u128*r,const uint8_t*ls,BCESBatchWrite*out,u128*last,BCESBatchCost*cost){@autoreleasepool{
 *cost={};if(shared.state.load()!=2)return 0;
 unsigned current=shared.flight.load();do{if(current>=2)return -2;}while(!shared.flight.compare_exchange_weak(current,current+1));Flight ticket;
 if(!slot)slot.reset(new(std::nothrow) Slot);if(!slot||!slot->prepare())return -2;auto&s=*slot;
 unsigned n=p->iterations,w=p->writes_per_iteration;if(!n||n>BCES_BATCH_MAX_ITERATIONS||!w||w>BCES_BATCH_MAX_WRITES)return -1;
 NSUInteger bytes=(NSUInteger)n*w*sizeof(BCESBatchWrite),hashbytes=(2*n+2)*sizeof(uint32_t);if(!s.ensure(bytes,hashbytes))return -1;
 auto start=Clock::now();memcpy(s.seed.contents,r,2048);uint64_t pages=p->read_pages;
 while(pages){unsigned page=__builtin_ctzll(pages);memcpy((uint8_t*)s.ls.contents+4096*page,ls+4096*page,4096);cost->input_bytes+=4096;pages&=pages-1;}
 uint32_t parameters[4]={p->pc,n,w,0};memcpy(s.parameters.contents,parameters,sizeof parameters);memset(s.hashes.contents,0,hashbytes);if(p->pc==0xA650){memcpy(s.states.contents,p->cull_states,n*48);cost->input_bytes+=n*48;}cost->input_bytes+=2048;cost->input_ns=ns(start);
 start=Clock::now();id<MTLCommandBuffer> command=[s.queue commandBuffer];id<MTLComputeCommandEncoder> encoder=[command computeCommandEncoder];if(!encoder)return -1;
 [encoder setBuffer:s.seed offset:0 atIndex:0];[encoder setBuffer:s.ls offset:0 atIndex:1];[encoder setBuffer:s.output offset:0 atIndex:2];[encoder setBuffer:s.hashes offset:0 atIndex:3];[encoder setBuffer:s.parameters offset:0 atIndex:4];[encoder setBuffer:s.states offset:0 atIndex:6];
 unsigned index=p->pc==0xD800?0:p->pc==0xD5B0?1:p->pc==0xDA28?2:p->pc==0xDCE0?3:p->pc==0xDF20?4:p->pc==0x7030?5:6;
 [encoder setComputePipelineState:shared.compute[index]];NSUInteger width=MIN((NSUInteger)32,shared.compute[index].maxTotalThreadsPerThreadgroup);[encoder dispatchThreads:MTLSizeMake(n,1,1) threadsPerThreadgroup:MTLSizeMake(width,1,1)];
 [encoder endEncoding];[command commit];cost->submit_ns=ns(start);
 start=Clock::now();bool tail_okay=bces_batch_tail(p,r,ls,last);cost->cpu_tail_ns=ns(start);
 start=Clock::now();[command waitUntilCompleted];cost->wait_ns=ns(start);if(command.status!=MTLCommandBufferStatusCompleted||!tail_okay)return -1;
 cost->gpu_ns=(uint64_t)(1e9*(command.GPUEndTime-command.GPUStartTime));
 start=Clock::now();const uint32_t*hash=(const uint32_t*)s.hashes.contents;
 for(unsigned i=0;i<n;i++)if(!hash[n+2+i]||hash[i]!=p->hashes[i])return -1;
 const BCESBatchWrite*records=(const BCESBatchWrite*)s.output.contents;for(unsigned i=0;i<n*w;i++)if(records[i].address!=p->addresses[i])return -1;
 memcpy(out,records,bytes);cost->output_bytes=bytes+hashbytes;cost->output_ns=ns(start);return 1;
}}
