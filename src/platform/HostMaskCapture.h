#pragma once
#import <Metal/Metal.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_mask_capture(id<MTLCommandBuffer>,id<MTLTexture>,id<MTLBuffer>);
int bces_mask_capture_state(void);
#ifdef __cplusplus
}
#endif
