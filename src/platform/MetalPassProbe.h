#pragma once
#import <Metal/Metal.h>
#ifdef __cplusplus
extern "C" {
#endif
// Opt-in, one complete guest frame; stage-boundary timestamps, no extra waits.
id<MTLRenderCommandEncoder> bces_pass_probe_encoder(id<MTLCommandBuffer>,MTLRenderPassDescriptor*,const char*,unsigned);
id<MTLComputeCommandEncoder> bces_pass_probe_compute(id<MTLCommandBuffer>,const char*);
void bces_pass_probe_present_begin(void);
void bces_pass_probe_commit(id<MTLCommandBuffer>);
void bces_pass_probe_boundary(id<MTLDevice>);
int bces_pass_probe_state(void);
extern unsigned bces_pass_probe_draw_recording;
void bces_pass_probe_draw(unsigned,unsigned,unsigned);
#ifdef __cplusplus
}
#endif
