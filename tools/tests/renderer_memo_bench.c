#include "RendererMemo.h"
#include "VertexFetchMemo.h"
#include "rsx_vertex_compact.h"
#include "rsx_vertex_formats.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(void){
    // Synthetic workload shaped by measured draw/unique-vertex counts. It is
    // not a replay of the game, a device test, or an FPS prediction.
    enum {DRAWS=8500,VERTS=100};
    unsigned char*source=malloc(DRAWS*VERTS*16);unsigned char out[VERTS*48];
    assert(source);for(unsigned i=0;i<DRAWS*VERTS*16;i++)source[i]=(unsigned char)(i*79+(i>>11));
    rsx_vertex_ref refs[VERTS];for(unsigned i=0;i<VERTS;i++)refs[i]=(rsx_vertex_ref){i,0};
    rsx_vertex_fetch_plan p={0};p.layout.count=3;p.layout.stride=48;
    const unsigned types[3]={RSX_VTX_TYPE_SNORM16,RSX_VTX_TYPE_HALF,RSX_VTX_TYPE_CMP32};
    const unsigned sizes[3]={3,3,1},offsets[3]={0,6,12},bytes[3]={6,6,4};
    for(unsigned a=0;a<3;a++){p.layout.attrs[a]=a;p.attr[a].desc.type=types[a];p.attr[a].desc.size=sizes[a];p.attr[a].stride=16;p.attr[a].elem_size=bytes[a];p.attr[a].stable_last=VERTS-1;}
    volatile unsigned checksum=0;
    // Validation always returns the original live result, checking all 8500
    // memo-produced outputs before timing either path.
    for(unsigned trial=0;trial<7;trial++){
        unsigned mode=trial==0?2:(trial&1?0:1);bces_renderer_memo_set(BCES_MEMO_VERTEX,mode);
        double start=now();unsigned frames=trial?5:1;
        for(unsigned frame=0;frame<frames;frame++)for(unsigned draw=0;draw<DRAWS;draw++){
            for(unsigned a=0;a<3;a++)p.attr[a].stable_base=source+draw*VERTS*16+offsets[a];
            int ok=0;const u8*vertices=bces_vertex_fetch_borrow(&p,refs,VERTS,out,&ok);assert(ok);checksum+=vertices[(draw&15)*48];
        }
        bces_renderer_memo_publish();BCESMemoStats s=bces_renderer_memo_stats(BCES_MEMO_VERTEX);
        assert(!s.mismatches);
        printf("trial=%u mode=%u cpu_ms_per_synthetic_frame=%.3f calls=%llu hits=%llu resident=%llu\n",trial,mode,1000*(now()-start)/frames,(unsigned long long)s.calls,(unsigned long long)s.hits,(unsigned long long)s.resident_bytes);
    }
    printf("checksum=%u\n",checksum);bces_renderer_memo_clear(BCES_MEMO_VERTEX);free(source);
}
