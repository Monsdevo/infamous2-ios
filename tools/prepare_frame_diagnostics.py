#!/usr/bin/env python3
"""Build-only diagnostics overlay of pinned, already-patched runtime sources."""
from pathlib import Path
import hashlib
import json
from prepare_rsx_legacy import instrument as instrument_rsx_legacy

ROOT=Path(__file__).resolve().parents[1]


def put(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.read_text()!=text:path.write_text(text)


def prepare(output,sdk,metal):
    lock=json.loads((ROOT/'sources.lock.json').read_text())['ios_frame_diagnostics']
    for name,expected in lock['source_sha256'].items():
        if hashlib.sha256((sdk/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Diagnostic source changed: '+name)
    h=(sdk/'include/ps3emu/ps3_ftrace.h').read_text()
    h=h.replace('    char names[PS3_FT_TIDS][28];','    char names[PS3_FT_TIDS][28];\n    uint32_t writers, names_lock;')
    h=h.replace('PS3_FT_SHARED ps3_ft_state g_ps3_ft = { 0 };','extern ps3_ft_state g_ps3_ft;')
    start=h.index('static inline void ps3_ft_span(')
    end=h.index('/* sys_timer_usleep polls',start)
    h=h[:start]+'''static inline void ps3_ft_span(int kind, uint32_t who, uint32_t a, uint32_t b,
                               uint64_t t0, uint64_t t1)
{
    ps3_ft_state* s=&g_ps3_ft;
    if (__atomic_load_n(&s->on,__ATOMIC_ACQUIRE)!=2) return;
    __atomic_add_fetch(&s->writers,1,__ATOMIC_ACQ_REL);
    if (__atomic_load_n(&s->on,__ATOMIC_ACQUIRE)==2 && t1>=s->start && t0<=s->end && t1>=t0) {
        uint32_t i=__atomic_fetch_add(&s->n,1,__ATOMIC_RELAXED);
        if(i<s->cap) { ps3_ft_rec r={t0,t1,a,b,who,(uint32_t)kind};s->buf[i]=r; }
        else __atomic_add_fetch(&s->dropped,1,__ATOMIC_RELAXED);
    }
    __atomic_sub_fetch(&s->writers,1,__ATOMIC_RELEASE);
}

'''+h[end:]
    start=h.index('static inline void ps3_ft_usleep(')
    end=h.index('/* A PPU thread',start)
    h=h[:start]+'''void bces_progress_trace_ppu(uint32_t,uint32_t,uint64_t,uint64_t);
static inline void ps3_ft_usleep(uint32_t tid, uint32_t lr, uint64_t t0, uint64_t t1)
{
    if(t1>=t0 && t1-t0>=g_ps3_ft.min) {
        ps3_ft_span(PS3_FT_USLEEP,tid,1,lr,t0,t1);
        bces_progress_trace_ppu(tid,lr,t0,t1);
    }
}

'''+h[end:]
    start=h.index('static inline void ps3_ft_name(')
    end=h.index('#ifdef __cplusplus',start)
    h=h[:start]+'''static inline void ps3_ft_name(uint32_t tid,const char* name)
{
    if(tid>=PS3_FT_TIDS || !name)return;
    while(__atomic_exchange_n(&g_ps3_ft.names_lock,1,__ATOMIC_ACQUIRE)) {}
    snprintf(g_ps3_ft.names[tid],sizeof g_ps3_ft.names[tid],"%s",name);
    __atomic_store_n(&g_ps3_ft.names_lock,0,__ATOMIC_RELEASE);
}

'''+h[end:]
    # Control/flush belongs to our UI timer, never the guest/render hot thread.
    # The legacy auto-dump is unreachable from the replacement span/usleep.
    put(output/'trace-include/ps3emu/ps3_ftrace.h',h)
    channels=(sdk/'runtime/spu/spu_channels.c').read_text()
    marker='    const uint64_t t1 = ps3_ft_now();\n    if (t1 - t0 < ps3_ft_min_ns()) return;'
    assert channels.count(marker)==1
    channels=channels.replace(marker,'''    const uint64_t t1 = ps3_ft_now();
    static __thread uint64_t mapped_window;
    if(t1>=g_ps3_ft.start && t1<=g_ps3_ft.end && mapped_window!=g_ps3_ft.start) {
        uint64_t tid=0;pthread_threadid_np(NULL,&tid);
        ps3_ft_span(18,ctx->spu_id|0x80000000u,(uint32_t)tid,(uint32_t)(tid>>32),t1,t1);
        mapped_window=g_ps3_ft.start;
    }
    if (t1 - t0 < ps3_ft_min_ns()) return;
''')
    assert channels.count('#include "spu_dma.h"')==1
    channels=channels.replace('#include "spu_dma.h"','#include "diagnostic_spu_dma.h"')
    channels='#include "ProgressTrace.h"\n'+channels
    marker='    uint64_t llm = 0;\n'
    assert channels.count(marker)==1
    channels=channels.replace(marker,marker+'    uint64_t progress_t0=0,progress_t1=0;\n')
    marker='gm_copy_to(mem, ls, MFC_ATOMIC_LINE);'
    assert channels.count(marker)==2
    channels=channels.replace(marker,'''if(PS3_FT_ON() && bces_progress_trace_watched(ea,MFC_ATOMIC_LINE))progress_t0=ps3_ft_now();
            '''+marker+'''
            if(progress_t0)progress_t1=ps3_ft_now();''')
    callback='''if(progress_t0)bces_progress_trace_dma(ctx->spu_id,ctx->image_id,ctx->pc,
            ctx->gpr[0]._u32[0],ea,lsa,MFC_ATOMIC_LINE,ls,ctx->ls,cmd,progress_t0,progress_t1);
        '''
    marker='        if (ctx->atomic_stat == 0 && g_spu_line_commit_hook)'
    assert channels.count(marker)==1
    channels=channels.replace(marker,'        '+callback+marker.lstrip(),1)
    marker='        if (g_spu_line_commit_hook) g_spu_line_commit_hook(ea & ~127u);'
    assert channels.count(marker)==1
    channels=channels.replace(marker,'        '+callback+marker.lstrip(),1)
    put(output/'diagnostic_spu_channels.c',channels)
    dma=(sdk/'runtime/spu/spu_dma.h').read_text()
    dma=dma.replace('#include "spu_context.h"','#include "spu_context.h"\n#include "FrameDependency.h"\n#include "ProgressTrace.h"\n#include "EdgeFlow.h"\n#include "ps3emu/ps3_ftrace.h"\nextern uint32_t ppu_hle_inject_base;')
    copy='gm_copy_to((uint8_t*)ea_ptr, ls_ptr, size);'
    assert dma.count(copy)==2
    put_branch='    } else if (mfc_is_put(cmd)) {'
    assert dma.count(put_branch)==1
    dma=dma.replace(put_branch,put_branch+'''
        const uint32_t diagnostic_base=ppu_hle_inject_base;
        const int diagnostic_label=PS3_FT_ON() && bces_trace_label_range(ea,size,diagnostic_base);
        const int diagnostic_progress=PS3_FT_ON() && bces_progress_trace_watched(ea,size);
        const int diagnostic_watch=diagnostic_label || diagnostic_progress;
        uint64_t diagnostic_t0=0,diagnostic_t1=0;''')
    dma=dma.replace(copy,'''if(diagnostic_watch) diagnostic_t0=ps3_ft_now();
                '''+copy+'''
                if(diagnostic_watch) diagnostic_t1=ps3_ft_now();''')
    marker='        /* Tell whoever is listening where this PUT landed.'
    assert dma.count(marker)==1
    dma=dma.replace(marker,'''        // Trace ancestry only AFTER releasing coherence locks and notifications.
        if(diagnostic_t0 && diagnostic_label) bces_frame_trace_dma(spu->spu_id,spu->image_id,
            spu->pc,spu->gpr[0]._u32[0],ea,lsa,size,ls_ptr,diagnostic_base,
            diagnostic_t0,diagnostic_t1);
        if(diagnostic_t0 && diagnostic_progress)bces_progress_trace_dma(spu->spu_id,spu->image_id,
            spu->pc,spu->gpr[0]._u32[0],ea,lsa,size,ls_ptr,spu->ls,cmd,
            diagnostic_t0,diagnostic_t1);
'''+marker)
    end='    return 0;\n}\n\n/*\n * Execute a DMA list command'
    assert dma.count(end)==1
    dma=dma.replace(end,'    if(PS3_FT_ON())bces_edge_flow_dma(spu,ea,lsa,size,cmd);\n'+end)
    put(output/'diagnostic_spu_dma.h',dma)
    gcm=(sdk/'libs/video/cellGcmSys.c').read_text()
    direct='#include "../../include/ps3emu/ps3_ftrace.h"'
    assert gcm.count(direct)==1
    gcm=gcm.replace(direct,'#include "ps3emu/ps3_ftrace.h"')
    # BCES links command segments by patching a self-JUMP. Hardware does not
    # discard the intervening commands after an arbitrary wall-clock timeout.
    # A slow frame can exceed the grace even when put has moved legitimately.
    # Keep the consumer parked; all other malformed-FIFO recovery stays intact.
    old='''                          s_park_off = 0; s_park_since = 0;
                          gcm_fifo_dump_around(s_fifo_getoff);
                          gcm_fifo_resync_why("jump-park", &s_fifo_getoff, put);'''
    assert gcm.count(old)==1
    gcm=gcm.replace(old,'''                          static unsigned bces_park_logs;
                          if (bces_park_logs++ < 64)
                              fprintf(stderr,"[bces GCM] preserving self-JUMP at 0x%08X put=0x%08X waited=%llu ms; no commands discarded\\n",
                                      s_fifo_getoff,put,now-s_park_since);
                          grace_since = now;''')
    gcm=instrument_rsx_legacy(gcm,sdk)
    put(output/'diagnostic_cellGcmSys.c',gcm)
    m=metal.read_text()
    # An explicit trigger captures just the current displayed game surface.
    # No periodic GPU readbacks are added to performance windows. The token
    # in the PPM header lets the host reject stale/partially copied captures.
    old='''    static unsigned frame;
    if ((++frame % 120) != 0) return;'''
    new='''    static unsigned frame;
    ++frame;
    char bces_capture_token[65]={};
    const char* bces_trigger=getenv("PS3RECOMP_METAL_FRAME_DUMP_TRIGGER");
    if(bces_trigger && *bces_trigger) {
        FILE* request=fopen(bces_trigger,"rb");if(!request)return;
        int read=fscanf(request,"%64s",bces_capture_token);fclose(request);
        unlink(bces_trigger);
        if(read!=1)return;
        for(unsigned i=0;bces_capture_token[i];i++)
            if(!((bces_capture_token[i]>='a'&&bces_capture_token[i]<='z')||
                 (bces_capture_token[i]>='A'&&bces_capture_token[i]<='Z')||
                 (bces_capture_token[i]>='0'&&bces_capture_token[i]<='9')||
                 bces_capture_token[i]=='-'||bces_capture_token[i]=='_'))return;
    } else if ((frame % 120) != 0) return;'''
    if m.count(old)!=1:raise ValueError('One-shot display capture entry changed')
    m=m.replace(old,new,1)
    old='''        fprintf(f, "P6\\n%zu %zu\\n255\\n", w, h);'''
    new='''        fprintf(f, "P6\\n");
        if(bces_capture_token[0])fprintf(f,"# bces-request=%s frame=%u\\n",bces_capture_token,frame);
        fprintf(f, "%zu %zu\\n255\\n", w, h);'''
    if m.count(old)!=1:raise ValueError('One-shot display capture header changed')
    m=m.replace(old,new,1)
    commits=m.count('[cb commit]')+m.count('[fence commit]')
    waits=m.count('[cb waitUntilCompleted]')+m.count('[fence waitUntilCompleted]')
    assert commits>=10 and waits>=8
    for var in ('cb','fence'):
        m=m.replace('['+var+' commit]',f'diagnostic_commit({var}, __LINE__)')
        m=m.replace('['+var+' waitUntilCompleted]',f'diagnostic_wait({var}, __LINE__)')
    helpers='''// Opt-in all-backend command-buffer timestamps. No new GPU waits.
static void diagnostic_commit(id<MTLCommandBuffer> buffer,uint32_t line)
{
    if(PS3_FT_ON()) {
        static uint32_t sequence;
        const uint32_t tag=__atomic_add_fetch(&sequence,1,__ATOMIC_RELAXED);
        const uint64_t now=ps3_ft_now();
        const int64_t offset=(int64_t)now-(int64_t)(CACurrentMediaTime()*1e9);
        ps3_ft_span(16,tag,line,0,now,now);
        [buffer addCompletedHandler:^(id<MTLCommandBuffer> finished) {
            if(finished.GPUStartTime>0 && finished.GPUEndTime>=finished.GPUStartTime) {
                uint64_t a=(uint64_t)((int64_t)(finished.GPUStartTime*1e9)+offset);
                uint64_t b=(uint64_t)((int64_t)(finished.GPUEndTime*1e9)+offset);
                ps3_ft_span(15,tag,line,(uint32_t)finished.status,a,b);
            }
            uint64_t t=ps3_ft_now();ps3_ft_span(19,tag,line,(uint32_t)finished.status,t,t);
        }];
    }
    [buffer commit];
}
static void diagnostic_wait(id<MTLCommandBuffer> buffer,uint32_t line)
{
    uint64_t t=PS3_FT_ON()?ps3_ft_now():0;
    [buffer waitUntilCompleted];
    if(t)ps3_ft_span(PS3_FT_GPU_WAIT,0,3,line,t,ps3_ft_now());
}

'''
    marker='static void surface_track_submission('
    assert m.count(marker)==1
    m=m.replace(marker,helpers+marker)
    marker='        if (game_telemetry_present) game_telemetry_present(shown.presentedTime);'
    assert m.count(marker)==1
    m=m.replace(marker,marker+'''
        if(PS3_FT_ON()) {
            int64_t offset=(int64_t)ps3_ft_now()-(int64_t)(CACurrentMediaTime()*1e9);
            uint64_t t=(uint64_t)((int64_t)(shown.presentedTime*1e9)+offset);
            ps3_ft_span(20,(uint32_t)sequence,0,0,t,t);
        }''')
    put(metal,m)
    put(output/'diagnostic-coverage.json',json.dumps({'metal_commit_sites':commits,'metal_wait_sites':waits,
         'backend_queues':['s_queue'],'gpu_light_ssao':'disabled in BCES configuration',
         'spu_busy_definition':'wall time between blocking channel waits, NOT job CPU time',
         'source_sha256':lock['source_sha256']},indent=2)+'\n')
