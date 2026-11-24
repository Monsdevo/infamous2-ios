#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Attach/detach only while the backend is shut down. The UIKit owner creates
// the layer on main; all backend operations belong to one serial render queue.
int rsx_metal_backend_attach_ios_layer(void* layer);
typedef struct {
    uint64_t submitted, completed, presented, errors;
} RSXSurfaceStats;
RSXSurfaceStats rsx_metal_backend_ios_stats(void);
#ifdef __cplusplus
}
#endif
