#include "FrameTrace.h"
#include "FrameDependency.h"
#include "ps3emu/ps3_ftrace.h"
#include <cassert>
#include <unistd.h>
int main(int argc,char** argv) {
    assert(argc==2);const uint32_t base=0x100000;
    assert(bces_trace_label_range(base+0x870,4,base));
    assert(bces_trace_label_range(base+0x880,4,base));
    assert(!bces_trace_label_range(base+0x870,3,base));
    assert(!bces_trace_label_range(base+0x874,4,base));
    assert(bces_trace_label_range(base+0x860,64,base));
    assert(!bces_trace_covers_word(0xfffffff0ull,32,0));
    bces_frame_trace_configure(argv[1]);
    char path[1200];snprintf(path,sizeof path,"%s/frame-trace-control.txt",argv[1]);
    FILE* f=fopen(path,"w");assert(f);fputs("start dependency_host 1\n",f);fclose(f);
    bces_frame_trace_poll();usleep(300000);
    uint8_t source[64]={};source[16]=0x12;source[17]=0x34;source[18]=0x56;source[19]=0x78;
    source[48]=0x87;source[49]=0x65;source[50]=0x43;source[51]=0x21;
    source[32]=0x11;source[33]=0x22;source[34]=0x33;source[35]=0x44;
    uint64_t t=ps3_ft_now();
    bces_frame_trace_dma(8192,234,0x7320,0x7210,base+0x860,0x100,64,source,base,t,t+1000);
    bces_frame_trace_dma(8192,234,0x7320,0x7210,base+0x870,0x100,3,source,base,t,t+1000);
    unsigned writes=0,context=0;
    for(unsigned i=0;i<g_ps3_ft.n;++i) {
        const auto& r=g_ps3_ft.buf[i];
        if(r.kind==21) {++writes;assert((r.a==0x870 && r.b==0x12345678)||(r.a==0x880 && r.b==0x11223344)||(r.a==0x890 && r.b==0x87654321));}
        if(r.kind==22){++context;assert(r.a==8192 && r.b==234);}
    }
    assert(writes==3 && context==3);
    for(int i=0;i<200 && bces_frame_trace_state()!=3;++i){usleep(10000);bces_frame_trace_poll();}
    assert(bces_frame_trace_state()==3 && !g_ps3_ft.dropped);
    puts("PASS: full-word filtering, range boundaries, big-endian values, three-label provenance and flush");
}
