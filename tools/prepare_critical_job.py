"""Bracket whole guest calls, including drain and image restoration."""
import re
TARGETS=(0x6B90,0x68D8,0x5A98)
def patch(source):
    assert 'bces_critical_begin' not in source
    for target in TARGETS:
        pattern=r'^        ctx->gpr\[0\] = spu_link\(0x([0-9A-F]+)\); \{[^\n]* jobmod_638a73a6476e_e60c0_spu_func_'+f'{target:08X}'+r'\(ctx\);[^\n]* \}$'
        matches=list(re.finditer(pattern,source,re.M));assert len(matches)==1,(hex(target),len(matches))
        m=matches[0];call=m.group();ret=int(m.group(1),16)
        replacement='''        if (__atomic_load_n(&bces_critical_job_enabled,__ATOMIC_RELAXED) &&
            __atomic_load_n(&g_ps3_ft.on,__ATOMIC_RELAXED)==2) {
            BCESCriticalSpan bces_scope=bces_critical_begin(ctx,TARGET,RETURN_PC);
CALL
            bces_critical_end(bces_scope,ctx);
        } else {
CALL
        }'''.replace('TARGET',hex(target)).replace('RETURN_PC',hex(ret)).replace('CALL',call)
        source=source[:m.start()]+replacement+source[m.end():]
    return '#include "CriticalJobTrace.h"\n#include "ps3emu/ps3_ftrace.h"\n'+source

def patch_wws(source):
    call='        { uint32_t _tg = ctx->gpr[5]._u32[0]; ctx->gpr[0] = spu_link(0x3218); int32_t _si = (int32_t)ctx->image_id; ctx->int_enable = 1; ctx->pc = _tg; ctx->host_depth++; spu_indirect_branch(ctx); spu_drain_call(ctx, 0x3218); ctx->host_depth--; spu_img_restore(ctx, _si); }'
    assert source.count(call)==1 and 'bces_critical_begin' not in source
    replacement='''        if (__atomic_load_n(&bces_critical_job_enabled,__ATOMIC_RELAXED) &&
            __atomic_load_n(&g_ps3_ft.on,__ATOMIC_RELAXED)==2) {
            BCESCriticalSpan bces_scope=bces_critical_begin(ctx,0x80000000u|(ctx->gpr[5]._u32[0]&SPU_LS_MASK),0x3218);
CALL
            bces_critical_end(bces_scope,ctx);
        } else {
CALL
        }'''.replace('CALL',call)
    return '#include "CriticalJobTrace.h"\n#include "ps3emu/ps3_ftrace.h"\n'+source.replace(call,replacement,1)

def patch_logical(source,module,entry):
    signature=f'void {module}_spu_func_{entry:08X}(spu_context* ctx) {{'
    exit='        ctx->int_enable = 0; SPU_RET(ctx);'
    assert source.count(signature)==1 and source.count(exit)==1
    guard='__atomic_load_n(&bces_critical_job_enabled,__ATOMIC_RELAXED) && __atomic_load_n(&g_ps3_ft.on,__ATOMIC_RELAXED)==2'
    source=source.replace(signature,signature+'\n    if('+guard+')bces_critical_logical_begin(ctx,'+hex(entry)+');',1)
    source=source.replace(exit,'        if('+guard+')bces_critical_logical_end(ctx);\n'+exit,1)
    return '#include "CriticalJobTrace.h"\n#include "ps3emu/ps3_ftrace.h"\n'+source
