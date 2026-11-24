#!/usr/bin/env python3
"""Preserve reset/IRQ/lookup semantics; opt-in existing fast dispatch for BCES WWS."""
from pathlib import Path
import hashlib
import json
ROOT=Path(__file__).resolve().parents[1]


def channels_source(source):
    marker='        s_stack_reset[s_stack_reset_count].entry = entry & SPU_LS_MASK;'
    assert source.count(marker)==1
    source=source.replace(marker,'''        __atomic_store_n(&bces_spu_reset_pages[(entry & SPU_LS_MASK)>>8],1,__ATOMIC_RELEASE);
'''+marker,1)
    start=source.index('void spu_indirect_branch(spu_context* ctx)\n{')
    marker='    const uint32_t pc = ctx->pc & SPU_LS_MASK;'
    at=source.index(marker,start)+len(marker)
    source=source[:at]+'''
    // Only this title's WWS context is admitted; all service/miss/diagnostic
    // guards below remain. The resolver's IRQ helper is a no-op except at an
    // interrupts-enabled return to irq_resume_pc, so retain that exact case.
    const int bces_shape=ctx->image_id==100 && !ctx->policy_mode && ctx->resident_ovl>=200;
    const int bces_fast=bces_shape && __atomic_load_n(&bces_spu_dispatch_fast,__ATOMIC_RELAXED);
    const int bces_count=bces_shape && __atomic_load_n(&bces_spu_dispatch_instrument,__ATOMIC_RELAXED);
    BCESDispatchCounters* bces_stats=&bces_spu_dispatch_counters[ctx->spu_id&15u];
    if(bces_count)__atomic_fetch_add(&bces_stats->eligible,1,__ATOMIC_RELAXED);
'''+source[at:]
    old='if (__atomic_load_n(&ctx->stop_request, __ATOMIC_RELAXED) || ctx->irq_saved ||'
    new='''if (__atomic_load_n(&ctx->stop_request, __ATOMIC_RELAXED) ||
        (ctx->irq_saved && (!bces_fast || (pc==(ctx->irq_resume_pc & SPU_LS_MASK) && ctx->int_enable))) ||'''
    assert source.count(old)==1;source=source.replace(old,new,1)
    old='ctx->image_id == SPU_RESOLVER_ONLY_IMAGE_ID || ctx->resident_ovl >= 200 ||'
    assert source.count(old)==1
    source=source.replace(old,'ctx->image_id == SPU_RESOLVER_ONLY_IMAGE_ID || (ctx->resident_ovl >= 200 && !bces_fast) ||',1)
    old='        ctx->resident_task = rt;\n        spu_check_stack_reset(ctx, fn);'
    assert source.count(old)==1
    source=source.replace(old,'''        ctx->resident_task = rt;
        if(bces_count)__atomic_fetch_add(&bces_stats->fast,1,__ATOMIC_RELAXED);
        spu_check_stack_reset(ctx, fn);''',1)
    old='slow:;\n#if defined(__clang__)'
    assert source.count(old)==1
    source=source.replace(old,'''slow:;
    if(bces_count)__atomic_fetch_add(&bces_stats->fallback,1,__ATOMIC_RELAXED);
#if defined(__clang__)''',1)
    return '#include "SpuDispatchControl.h"\n'+source


def drain_source(source):
    old='    spu_check_stack_reset(ctx, (void (*)(spu_context*))fn);'
    assert source.count(old)==1
    source=source.replace(old,'''    // The registration-maintained page map is a conservative negative test.
    // Every possibly matching PC still runs the original fn/image/TLS check.
    const int bces_check=!__atomic_load_n(&bces_spu_dispatch_fast,__ATOMIC_RELAXED) ||
       __atomic_load_n(&bces_spu_reset_pages[(ctx->pc & SPU_LS_MASK)>>8],__ATOMIC_ACQUIRE);
    if(__atomic_load_n(&bces_spu_dispatch_instrument,__ATOMIC_RELAXED)){
        BCESDispatchCounters* stats=&bces_spu_dispatch_counters[ctx->spu_id&15u];
        __atomic_fetch_add(bces_check?&stats->reset_checks:&stats->reset_bypasses,1,__ATOMIC_RELAXED);
    }
    if(bces_check)
        spu_check_stack_reset(ctx, (void (*)(spu_context*))fn);''',1)
    return '#include "SpuDispatchControl.h"\n'+source


def prepare(output,sdk):
    lock=json.loads((ROOT/'sources.lock.json').read_text())['ios_spu_dispatch']
    raw=(sdk/'runtime/spu/spu_drain.c').read_text()
    if hashlib.sha256(raw.encode()).hexdigest()!=lock['drain_sha256']:
        raise ValueError('SPU drain changed; review reset contract')
    path=output/'diagnostic_spu_channels.c';path.write_text(channels_source(path.read_text()))
    (output/'diagnostic_spu_drain.c').write_text(drain_source(raw))
