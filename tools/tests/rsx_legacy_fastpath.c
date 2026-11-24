#include "RSXLegacyFastPath.h"
#include "rsx_commands.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern uint32_t g_rsx_last_reference;
uint32_t ppu_hle_inject_base=0x03000000;
typedef struct Event {uint32_t kind,a,b,c,d;} Event;
static Event events[32768],expected[32768];static unsigned event_count;
static _Atomic int finished;
static void event(unsigned k,unsigned a,unsigned b,unsigned c,unsigned d) {
    assert(event_count<sizeof events/sizeof events[0]);events[event_count++]=(Event){k,a,b,c,d};
}
void vm_write32(uint32_t a,uint32_t v){event(1,a,v,0,0);}
void rsx_snap_event(int which,uint32_t off){event(2,(unsigned)which,off,0,0);}
void ps3_ms(const char*key){assert(!strcmp(key,"rsx:draw_arrays")||!strcmp(key,"rsx:draw_indexed"));event(!strcmp(key,"rsx:draw_arrays")?3:4,0,0,0,0);}
unsigned long long ps3_ms_now(void){return 1;}
static void state_event(unsigned kind,const rsx_state*s) {
    const unsigned char*p=(const unsigned char*)s;uint32_t hash=2166136261u;
    for(unsigned i=0;i<sizeof *s;i++)hash=(hash^p[i])*16777619u;
    event(kind,hash,0,0,0);
}
#define STATE_CALLBACK(name,kind) static void name(void*u,const rsx_state*s){(void)u;state_event(kind,s);}
STATE_CALLBACK(rt,10) STATE_CALLBACK(viewport,11) STATE_CALLBACK(blend,12)
STATE_CALLBACK(depth,13) STATE_CALLBACK(color,14) STATE_CALLBACK(alpha,15)
STATE_CALLBACK(shader,16) STATE_CALLBACK(vertex,17)
static void bind(void*u,uint32_t unit,const rsx_texture_state*t){(void)u;event(18,unit,t->offset,t->format,t->control0);}
static void clear(void*u,uint32_t flags,uint32_t c,float d,uint8_t stencil){(void)u;uint32_t bits;memcpy(&bits,&d,4);event(19,flags,c,bits,stencil);}
static void arrays(void*u,uint32_t primitive,uint32_t first,uint32_t count){(void)u;event(20,primitive,first,count,0);}
static void indices(void*u,uint32_t primitive,uint32_t first,uint32_t count){(void)u;event(21,primitive,first,count,0);}
static rsx_backend backend={.set_render_target=rt,.set_viewport=viewport,.set_blend=blend,
    .set_depth_stencil=depth,.set_color_mask=color,.set_alpha_test=alpha,.set_shader=shader,
    .set_vertex_attribs=vertex,.bind_texture=bind,.clear=clear,.draw_arrays=arrays,.draw_indexed=indices};

static void send(rsx_state*s,int adapted,int engine,uint32_t m,uint32_t d) {
    if(adapted)bces_rsx_legacy_method(s,m,d,engine);else (void)rsx_process_method(s,m,d);
}
static unsigned stream(rsx_state*s,int adapted,int engine,unsigned seed) {
    rsx_state_init(s);g_rsx_last_reference=0;event_count=0;unsigned n=0;
    #define SEND(m,d) do{send(s,adapted,engine,m,d);n++;}while(0)
    SEND(0x1D6C,0);
    // Every canonical FIFO method, including unknown holes. Constrain load
    // cursors to valid bounds; these are state/side-effect tests, not shaders.
    for(unsigned m=0;m<0x2000;m+=4) {seed=seed*1664525u+1013904223u;SEND(m,(seed>>16)&255u);}
    for(unsigned i=0;i<64;i++) {
        SEND(NV4097_SET_TRANSFORM_CONSTANT_LOAD,i);
        for(unsigned k=0;k<32;k++)SEND(NV4097_SET_TRANSFORM_CONSTANT+k*4,0x3F800000u+k);
        SEND(NV4097_SET_BEGIN_END,5);SEND(NV4097_DRAW_ARRAYS,0x03000002);
        SEND(NV4097_DRAW_INDEX_ARRAY,0x05000001);SEND(NV4097_SET_BEGIN_END,0);
        SEND(0x1D6C,0x870u+(i&1u)*0x20u);SEND(0x1D70,0x12345678u+i);
        SEND(0x1D74,0xABCDEF00u+i);SEND(0x50,i);
    }
    #undef SEND
    return n;
}

static void* writer(void*opaque) {
    rsx_state*s=opaque;
    for(unsigned i=0;i<50000;i++) {
        bces_rsx_legacy_method(s,NV4097_SET_TRANSFORM_CONSTANT,(i&255u),1);
        if((i&255u)==0)bces_rsx_legacy_publish();
    }
    bces_rsx_legacy_publish();atomic_store(&finished,1);return NULL;
}

int main(int argc,char**argv) {
    assert(argc==5);int requested=atoi(argv[1]),engine=atoi(argv[2]),legacy=atoi(argv[3]),debug=atoi(argv[4]);
    if(debug)setenv("RSX_TRACE","1",1);
    bces_rsx_legacy_configure(requested);bces_rsx_legacy_configure(!requested); // Frozen until restart.
    rsx_set_backend(legacy?&backend:NULL);
    rsx_state*a=malloc(sizeof *a),*b=malloc(sizeof *b);assert(a&&b);
    unsigned total=0;
    for(unsigned seed=1;seed<=8;seed++) {
        unsigned n=stream(a,0,engine,seed),count=event_count;uint32_t ref=g_rsx_last_reference;
        memcpy(expected,events,count*sizeof(Event));assert(stream(b,1,engine,seed)==n);total+=n;
        assert(event_count==count&&!memcmp(events,expected,count*sizeof(Event))&&g_rsx_last_reference==ref);
        if(!requested||!engine||legacy||debug)assert(!memcmp(a,b,sizeof *a));
        else {
            // These fields feed retained functional/logging methods.
            assert(a->color_clear_value==b->color_clear_value&&a->zstencil_clear_value==b->zstencil_clear_value);
            assert(a->primitive_type==b->primitive_type&&a->begin_epoch==b->begin_epoch&&a->in_begin_end==b->in_begin_end);
            assert(a->index_array_offset==b->index_array_offset&&a->index_array_dma==b->index_array_dma);
        }
    }
    bces_rsx_legacy_publish();BCESRSXLegacyStats stats=bces_rsx_legacy_stats();
    assert(stats.configured&&stats.requested==requested&&stats.methods==total);
    assert(stats.methods==stats.state_skipped+stats.legacy_forwarded);
    assert(stats.sync_forwarded==8u*(1u+4u+64u*4u));assert(stats.draw_forwarded==8u*(2u+64u*2u));
    assert(stats.debug_fallback==!!(requested&&debug));
    assert((stats.state_skipped>0)==!!(requested&&engine&&!legacy&&!debug));
    // Original semaphore byteswap, release address and draw milestone path
    // were compared as real observable events, not duplicated mock logic.
    printf("PASS request=%d engine=%d legacy=%d debug=%d methods=%llu skipped=%llu: VM labels/snapshots/references/milestones/backend callbacks identical\n",
        requested,engine,legacy,debug,(unsigned long long)stats.methods,(unsigned long long)stats.state_skipped);
    event_count=0;pthread_t worker;assert(!pthread_create(&worker,NULL,writer,b));
    uint64_t previous=stats.methods;
    while(!atomic_load(&finished)) {
        BCESRSXLegacyStats s=bces_rsx_legacy_stats();assert(s.methods>=previous);
        assert(s.methods==s.state_skipped+s.legacy_forwarded&&s.sync_forwarded<=s.legacy_forwarded&&s.draw_forwarded<=s.legacy_forwarded);previous=s.methods;
    }
    assert(!pthread_join(worker,NULL));assert(bces_rsx_legacy_stats().methods==total+50000);
    puts("PASS coherent per-drain publication during concurrent UI reads");free(a);free(b);return 0;
}
