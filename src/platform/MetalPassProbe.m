#import "MetalPassProbe.h"
#import <Foundation/Foundation.h>
#import <QuartzCore/QuartzCore.h>
#include <stdatomic.h>
#include <unistd.h>
@interface BCESPassFrame:NSObject
@property(nonatomic,strong) id<MTLCounterSampleBuffer> buffer;
@property(nonatomic,strong) NSMutableArray* rows;
@property(nonatomic,strong) NSString* token;
@property(nonatomic,strong) NSString* directory;
@property uint64_t gpuStart;
@property double cpuStartNs;
@property double calibrationWidthNs;
@property unsigned samples;
@property unsigned dropped;
@end
@implementation BCESPassFrame
@end
static BCESPassFrame* active;
static int closing;
static _Atomic int state;
unsigned bces_pass_probe_draw_recording;
static NSMutableDictionary* currentRow;
void bces_pass_probe_draw(unsigned pipeline,unsigned vertices,unsigned indices){
 if(!active||!currentRow)return;
 currentRow[@"draw_records"]=@([currentRow[@"draw_records"] unsignedIntValue]+1);
 currentRow[@"vertices"]=@([currentRow[@"vertices"] unsignedLongLongValue]+vertices);
 currentRow[@"indices"]=@([currentRow[@"indices"] unsignedLongLongValue]+indices);
 NSMutableDictionary* pipelines=currentRow[@"pipelines"];NSString* key=[NSString stringWithFormat:@"%u",pipeline];pipelines[key]=@([pipelines[key] unsignedIntValue]+1);
}
int bces_pass_probe_state(void){return atomic_load_explicit(&state,memory_order_acquire);}
id<MTLRenderCommandEncoder> bces_pass_probe_encoder(id<MTLCommandBuffer> cb,MTLRenderPassDescriptor* rp,const char* site,unsigned record){
 currentRow=nil;
 if(active&&active.samples+4<=4096){
  unsigned start=active.samples;active.samples+=4;
  MTLRenderPassSampleBufferAttachmentDescriptor* attachment=rp.sampleBufferAttachments[0];
  attachment.sampleBuffer=active.buffer;attachment.startOfVertexSampleIndex=start;
  attachment.endOfVertexSampleIndex=start+1;attachment.startOfFragmentSampleIndex=start+2;attachment.endOfFragmentSampleIndex=start+3;
  NSMutableArray* textures=[NSMutableArray new];
  for(unsigned i=0;i<8;i++){id<MTLTexture> t=rp.colorAttachments[i].texture;if(t)[textures addObject:@{@"width":@(t.width),@"height":@(t.height),@"format":@(t.pixelFormat)}];}
  currentRow=[@{@"site":@(site),@"record":@(record),@"sample":@(start),@"colors":textures,@"depth_width":@(rp.depthAttachment.texture.width),@"depth_height":@(rp.depthAttachment.texture.height),@"draw_records":@0,@"vertices":@0,@"indices":@0,@"pipelines":[NSMutableDictionary new]} mutableCopy];
  [active.rows addObject:currentRow];
 }else if(active)active.dropped++;
 return [cb renderCommandEncoderWithDescriptor:rp];
}
void bces_pass_probe_present_begin(void){if(active)closing=1;}
id<MTLComputeCommandEncoder> bces_pass_probe_compute(id<MTLCommandBuffer> cb,const char* site){
 currentRow=nil;
 if(!active)return [cb computeCommandEncoder];
 if(active.samples+4>4096){active.dropped++;return [cb computeCommandEncoder];}
 unsigned start=active.samples;active.samples+=4;
 MTLComputePassDescriptor* descriptor=[MTLComputePassDescriptor new];
 descriptor.sampleBufferAttachments[0].sampleBuffer=active.buffer;
 descriptor.sampleBufferAttachments[0].startOfEncoderSampleIndex=start;
 descriptor.sampleBufferAttachments[0].endOfEncoderSampleIndex=start+1;
 [active.rows addObject:@{@"site":@(site),@"encoder_kind":@"compute",@"record":@0,@"sample":@(start),@"colors":@[],@"depth_width":@0,@"depth_height":@0,@"draw_records":@0,@"vertices":@0,@"indices":@0,@"pipelines":@{}}];
 return [cb computeCommandEncoderWithDescriptor:descriptor];
}
static void writeReport(BCESPassFrame* f,NSDictionary* result){
 NSString* filename=[NSString stringWithFormat:@"gpu-pass-%@.json",f.token];
 NSData* data=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
 [data writeToFile:[f.directory stringByAppendingPathComponent:filename] atomically:YES];
}
void bces_pass_probe_commit(id<MTLCommandBuffer> cb){
 if(!active||!closing)return;
 BCESPassFrame* f=active;active=nil;currentRow=nil;closing=0;__atomic_store_n(&bces_pass_probe_draw_recording,0,__ATOMIC_RELAXED);atomic_store_explicit(&state,2,memory_order_release);
 [cb addCompletedHandler:^(id<MTLCommandBuffer> done){@autoreleasepool{
  id<MTLDevice> device=done.commandQueue.device;MTLTimestamp cpu=0,gpu=0;
  double a=CACurrentMediaTime()*1e9;[device sampleTimestamps:&cpu gpuTimestamp:&gpu];double b=CACurrentMediaTime()*1e9;
  NSData* bytes=[f.buffer resolveCounterRange:NSMakeRange(0,f.samples)];
  BOOL valid=done.status!=MTLCommandBufferStatusError&&bytes.length==f.samples*sizeof(MTLCounterResultTimestamp)&&gpu>f.gpuStart;
  double scale=valid?(((a+b)/2-f.cpuStartNs)/(double)(gpu-f.gpuStart)):0;
  const MTLCounterResultTimestamp* samples=bytes.bytes;NSMutableArray* rows=[NSMutableArray new];unsigned invalid=0;
  if(valid)for(NSDictionary* source in f.rows){
   BOOL compute=[source[@"encoder_kind"] isEqual:@"compute"];
   unsigned i=[source[@"sample"] unsignedIntValue];uint64_t t[4];for(unsigned k=0;k<4;k++)t[k]=compute&&k>=2?0:samples[i+k].timestamp;
   BOOL v=t[0]&&t[1],p=t[2]&&t[3];
   BOOL ok=t[0]!=MTLCounterErrorValue&&t[1]!=MTLCounterErrorValue&&t[2]!=MTLCounterErrorValue&&t[3]!=MTLCounterErrorValue&&t[1]>=t[0]&&t[3]>=t[2]&&((t[0]==0)==(t[1]==0))&&((t[2]==0)==(t[3]==0));
   NSMutableDictionary* row=[source mutableCopy];row[@"raw_gpu_ticks"]=@[@(t[0]),@(t[1]),@(t[2]),@(t[3])];row[@"valid"]=@(ok);
   row[@"vertex_present"]=@(v&&!compute);row[@"fragment_present"]=@(p);row[@"compute_present"]=@(v&&compute);
   if(ok){row[@"vertex_ms"]=@((t[1]-t[0])*scale/1e6);row[@"fragment_ms"]=@((t[3]-t[2])*scale/1e6);uint64_t lo=v&&p?MIN(t[0],t[2]):v?t[0]:t[2],hi=MAX(t[1],t[3]);row[@"span_ms"]=@((hi-lo)*scale/1e6);}else invalid++;
   if(compute){row[@"compute_ms"]=row[@"vertex_ms"];row[@"vertex_ms"]=@0;}
   [rows addObject:row];
  }
  writeReport(f,@{@"token":f.token,@"valid":@(valid&&!invalid&&!f.dropped),@"invalid_samples":@(invalid),@"dropped_encoders":@(f.dropped),@"gpu_ticks_to_cpu_ns":@(scale),@"calibration_width_ns":@(MAX(b-a,f.calibrationWidthNs)),@"rows":rows,@"scope":@"One guest frame; render stages and tagged compute encoder boundaries; blits excluded. Overlapping spans must not be added; not an FPS benchmark"});
  atomic_store_explicit(&state,valid&&!invalid&&!f.dropped?3:-1,memory_order_release);
 }}];
}
void bces_pass_probe_boundary(id<MTLDevice> device){
 if(active||bces_pass_probe_state()==2)return;
 const char* directory=getenv("BCES_RESEARCH_DIR");if(!directory)return;
 NSString* root=@(directory);NSString* path=[root stringByAppendingPathComponent:@"gpu-pass-request.txt"];
 NSString* token=[[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
 if(!token.length||token.length>64)return;
 unlink(path.fileSystemRepresentation);
 if([token rangeOfCharacterFromSet:NSCharacterSet.alphanumericCharacterSet.invertedSet].location!=NSNotFound)return;
 BCESPassFrame* f=[BCESPassFrame new];f.token=token;f.directory=root;
 if(![device supportsCounterSampling:MTLCounterSamplingPointAtStageBoundary]){writeReport(f,@{@"valid":@NO,@"error":@"stage-boundary counters unavailable"});return;}
 id<MTLCounterSet> timestamps=nil;for(id<MTLCounterSet> set in device.counterSets)if([set.name isEqual:MTLCommonCounterSetTimestamp])timestamps=set;
 if(!timestamps){writeReport(f,@{@"valid":@NO,@"error":@"timestamp counter unavailable"});return;}
 MTLCounterSampleBufferDescriptor* descriptor=[MTLCounterSampleBufferDescriptor new];descriptor.counterSet=timestamps;descriptor.storageMode=MTLStorageModeShared;descriptor.sampleCount=4096;
 NSError* error=nil;f.buffer=[device newCounterSampleBufferWithDescriptor:descriptor error:&error];
 if(!f.buffer){writeReport(f,@{@"valid":@NO,@"error":error.description?:@"counter allocation failed"});return;}
 f.rows=[NSMutableArray new];MTLTimestamp cpu=0,gpu=0;double a=CACurrentMediaTime()*1e9;[device sampleTimestamps:&cpu gpuTimestamp:&gpu];double b=CACurrentMediaTime()*1e9;
 f.gpuStart=gpu;f.cpuStartNs=(a+b)/2;f.calibrationWidthNs=b-a;active=f;closing=0;__atomic_store_n(&bces_pass_probe_draw_recording,1,__ATOMIC_RELAXED);atomic_store_explicit(&state,1,memory_order_release);
}
