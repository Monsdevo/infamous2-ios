#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
int main(int argc,char**argv){@autoreleasepool{
 if(argc!=2)return 2;const unsigned cases=4*1024*1024;
 NSString* source=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:nil];id<MTLDevice> d=MTLCreateSystemDefaultDevice();if(!source||!d)return 3;
 MTLCompileOptions* options=[MTLCompileOptions new];options.fastMathEnabled=NO;NSError* error=nil;
 id<MTLLibrary> lib=[d newLibraryWithSource:source options:options error:&error];
 id<MTLComputePipelineState> p=lib?[d newComputePipelineStateWithFunction:[lib newFunctionWithName:@"check_far"] error:&error]:nil;
 if(!p){fprintf(stderr,"%s\n",error.description.UTF8String);return 4;}
 id<MTLBuffer> results=[d newBufferWithLength:12*4 options:MTLResourceStorageModeShared];memset(results.contents,0,48);((uint32_t*)results.contents)[8]=UINT32_MAX;
 id<MTLCommandBuffer> cb=[[d newCommandQueue] commandBuffer];id<MTLComputeCommandEncoder> e=[cb computeCommandEncoder];[e setComputePipelineState:p];[e setBuffer:results offset:0 atIndex:0];
 [e dispatchThreads:MTLSizeMake(cases,1,1) threadsPerThreadgroup:MTLSizeMake(MIN(256,p.maxTotalThreadsPerThreadgroup),1,1)];[e endEncoding];[cb commit];[cb waitUntilCompleted];if(cb.status!=MTLCommandBufferStatusCompleted)return 5;
 const uint32_t* r=results.contents;NSMutableArray* groups=[NSMutableArray new];uint64_t took=0,failed=0;
 for(unsigned i=0;i<4;i++){took+=r[i];failed+=r[4+i];[groups addObject:@{@"class":@(i),@"cases":@(cases/4),@"early_rejects":@(r[i]),@"oracle_mismatches":@(r[4+i])}];}
 NSDictionary* report=@{@"valid":@(!failed&&took>1000),@"device":d.name,@"cases":@(cases),@"early_rejects":@(took),@"mismatches":@(failed),@"first_mismatch_id":@(r[8]),@"groups":groups,@"gpu_test_ms":@((cb.GPUEndTime-cb.GPUStartTime)*1000),@"scope":@"Actual candidate guard versus original distance/attenuation/weight; full-range, sphere-boundary, inner-radius and invalid-parameter cases. Not game FPS proof."};
 NSData* data=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil];fwrite(data.bytes,1,data.length,stdout);puts("");return failed||took<=1000?6:0;
}}
