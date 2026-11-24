#!/usr/bin/env python3
"""iOS-only skinning boundary adapter, preserving original logical call/drain."""
def patch(source):
    before='jobmod_d0d15ec83992_ea2a0_spu_func_0000D0A8(ctx); spu_drain_call(ctx, 0x5980);'
    assert source.count(before)==1
    source=source.replace(before,'{ void* _skin_capture=bces_geometry_capture_begin(ctx,0); bces_geometry_execute(ctx,0,jobmod_d0d15ec83992_ea2a0_spu_func_0000D0A8,0x5980); bces_skinning_capture_end(_skin_capture,ctx); }')
    before='jobmod_d0d15ec83992_ea2a0_spu_func_0000A798(ctx); spu_drain_call(ctx, 0x59F0);'
    assert source.count(before)==1
    source=source.replace(before,'{ void* _cull_capture=bces_geometry_capture_begin(ctx,1); bces_geometry_execute(ctx,1,jobmod_d0d15ec83992_ea2a0_spu_func_0000A798,0x59F0); bces_skinning_capture_end(_cull_capture,ctx); }')
    return '#include "Skinning.h"\n#include "GeometryKernels.h"\n'+source
