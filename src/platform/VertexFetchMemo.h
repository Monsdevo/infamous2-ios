#pragma once
#include "rsx_vertex_compact.h"
#ifdef __cplusplus
extern "C" {
#endif
// Borrowed output is valid until the next vertex-fetch call or renderer-only
// cache cleanup. The iOS backend copies it into its GPU staging buffer before
// another vertex batch can begin. Caller still owns the reference buffer.
const u8* bces_vertex_fetch_borrow(const rsx_vertex_fetch_plan*,const rsx_vertex_ref*,u32,u8* reference_buffer,int* ok);
int bces_vertex_fetch_copy(const rsx_vertex_fetch_plan*,const rsx_vertex_ref*,u32,u8* out);
#ifdef __cplusplus
}
#endif
