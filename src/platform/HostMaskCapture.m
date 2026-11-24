#import "HostMaskCapture.h"
#import <Foundation/Foundation.h>
#include <stdatomic.h>
#include <unistd.h>
static _Atomic int state;
int bces_mask_capture_state(void){return atomic_load(&state);}
void bces_mask_capture(id<MTLCommandBuffer> cb,id<MTLTexture> texture,id<MTLBuffer> params){
 if(atomic_load(&state)==1)return;
 const char* dir=getenv("BCES_RESEARCH_DIR");if(!dir)return;
 NSString* root=@(dir),*request=[root stringByAppendingPathComponent:@"mask-input-request.txt"];
 if(access(request.fileSystemRepresentation,F_OK))return;
 NSString* token=[[NSString stringWithContentsOfFile:request encoding:NSUTF8StringEncoding error:nil] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];unlink(request.fileSystemRepresentation);
 if(!token.length||token.length>64||[token rangeOfCharacterFromSet:NSCharacterSet.alphanumericCharacterSet.invertedSet].location!=NSNotFound){atomic_store(&state,-1);return;}
 if(texture.pixelFormat!=MTLPixelFormatR32Float || params.length<80){atomic_store(&state,-1);return;}
 atomic_store(&state,1);NSUInteger row=(texture.width*4+255)&~255ull;
 id<MTLBuffer> pixels=[cb.commandQueue.device newBufferWithLength:row*texture.height options:MTLResourceStorageModeShared];
 if(!pixels){atomic_store(&state,-1);return;}
 NSData* constants=[NSData dataWithBytes:params.contents length:params.length];
 NSUInteger width=texture.width,height=texture.height;
 id<MTLBlitCommandEncoder> blit=[cb blitCommandEncoder];
 [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(width,height,1) toBuffer:pixels destinationOffset:0 destinationBytesPerRow:row destinationBytesPerImage:row*height];[blit endEncoding];
 [cb addCompletedHandler:^(id<MTLCommandBuffer> done){@autoreleasepool{
  if(done.status!=MTLCommandBufferStatusCompleted){atomic_store(&state,-1);return;}
  NSString* output=[root stringByAppendingPathComponent:[@"mask-input-" stringByAppendingString:token]];NSError* error=nil;
  if(![NSFileManager.defaultManager createDirectoryAtPath:output withIntermediateDirectories:YES attributes:nil error:&error]){atomic_store(&state,-1);return;}
  BOOL ok=[constants writeToFile:[output stringByAppendingPathComponent:@"params.bin"] atomically:YES];
  ok&=[[NSData dataWithBytes:pixels.contents length:row*height] writeToFile:[output stringByAppendingPathComponent:@"depth.raw"] atomically:YES];
  const float* p=constants.bytes;NSDictionary* meta=@{@"token":token,@"width":@(width),@"height":@(height),@"bytes_per_row":@(row),@"params_bytes":@(constants.length),@"light_count":@(p[17]),@"screen_width":@(p[18]),@"screen_height":@(p[19]),@"format":@"R32Float",@"scope":@"One actual light-mask input; readback outside FPS windows"};
  ok&=[[NSJSONSerialization dataWithJSONObject:meta options:NSJSONWritingPrettyPrinted error:nil] writeToFile:[output stringByAppendingPathComponent:@"metadata.json"] atomically:YES];atomic_store(&state,ok?3:-1);
 }}];
}
