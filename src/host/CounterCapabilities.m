#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
int main(void){@autoreleasepool{
 id<MTLDevice> d=MTLCreateSystemDefaultDevice();if(!d)return 1;
 NSMutableArray* sets=[NSMutableArray new];
 for(id<MTLCounterSet> s in d.counterSets){NSMutableArray* names=[NSMutableArray new];for(id<MTLCounter> c in s.counters)[names addObject:c.name];[sets addObject:@{@"name":s.name,@"counters":names}];}
 NSDictionary* report=@{@"device":d.name,@"stage_boundary":@([d supportsCounterSampling:MTLCounterSamplingPointAtStageBoundary]),@"draw_boundary":@([d supportsCounterSampling:MTLCounterSamplingPointAtDrawBoundary]),@"dispatch_boundary":@([d supportsCounterSampling:MTLCounterSamplingPointAtDispatchBoundary]),@"sets":sets};
 NSData* bytes=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil];fwrite(bytes.bytes,1,bytes.length,stdout);puts("");return 0;
}}
