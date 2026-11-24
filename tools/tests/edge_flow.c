#include "EdgeFlow.h"
#include "spu_context.h"
#include "ps3emu/ps3_ftrace.h"
#include <assert.h>
ps3_ft_state g_ps3_ft={0};
uint8_t* vm_base;
int main(void){
    spu_context*c=calloc(1,sizeof *c),*saved=malloc(sizeof *c);assert(c&&saved);
    c->ls=c->ls_store;c->spu_id=3;c->image_id=123;c->host_depth=2;
    c->gpr[4]._u32[0]=SPU_LS_SIZE-64;
    c->gpr[7]._u32[0]=SPU_LS_SIZE-64;
    for(unsigned i=0;i<SPU_LS_SIZE;++i)c->ls[i]=(uint8_t)i;
    memcpy(saved,c,sizeof *c);vm_base=calloc(1,4096);assert(vm_base);
    g_ps3_ft.cap=4096;g_ps3_ft.buf=calloc(g_ps3_ft.cap,sizeof *g_ps3_ft.buf);assert(g_ps3_ft.buf);
    g_ps3_ft.on=3;bces_edge_flow_enable(1);bces_edge_job_begin(c);bces_edge_job_end(c);assert(!g_ps3_ft.n);
    uint64_t now=ps3_ft_now();g_ps3_ft.start=now-1000000;g_ps3_ft.end=now+5000000000;g_ps3_ft.on=2;
    bces_edge_job_begin(c);BCESEdgeSpan call=bces_edge_span_begin(c,0x6170,0x5740);assert(call.id);
    bces_edge_flow_dma(c,0x100,0x400,64,0x40);
    bces_edge_flow_dma(c,0x200,0x800,64,0x20);
    bces_edge_flow_reader(vm_base+0x210,32,1,0,0x210);
    bces_edge_span_end(call,c);bces_edge_job_end(c);
    assert(!memcmp(saved,c,sizeof *c));
    unsigned n=g_ps3_ft.n;bces_edge_flow_dma(c,0x300,0,16,0x20);assert(g_ps3_ft.n==n);
    bces_edge_flow_enable(0);bces_edge_job_begin(c);bces_edge_job_end(c);assert(g_ps3_ft.n==n);
    bces_edge_flow_enable(1);call=bces_edge_span_begin(c,0,0xE2A0);assert(call.id);g_ps3_ft.start++;bces_edge_span_end(call,c);assert(g_ps3_ft.n==n);
    unsigned spans=0,cpu=0,dmarecords=0,readers=0,descriptor=0;
    printf("# {\"token\":\"host-edge-flow-test\",\"start\":%.9f,\"end\":%.9f,\"rows\":%u,\"dropped\":0}\n",(now-1000000)/1e9,(now+5000000000)/1e9,n);
    puts("kind,who,a,b,start_s,end_s");
    for(unsigned i=0;i<n;++i){ps3_ft_rec*r=&g_ps3_ft.buf[i];
        spans+=r->kind==200;cpu+=r->kind==201;dmarecords+=r->kind==211;readers+=r->kind==220;descriptor+=r->kind==209;
        printf("%u,%u,%u,%u,%.9f,%.9f\n",r->kind,r->who,r->a,r->b,r->t0/1e9,r->t1/1e9);
    }
    assert(spans==2&&cpu==2&&dmarecords==2&&readers==1&&descriptor==32);
    fprintf(stderr,"PASS: context unchanged; job/child CPU+wall; wrapping descriptor; DMA/reader ranges; disabled/end/epoch guards\n");
    free(g_ps3_ft.buf);g_ps3_ft.cap=32768;g_ps3_ft.buf=calloc(g_ps3_ft.cap,sizeof *g_ps3_ft.buf);assert(g_ps3_ft.buf);g_ps3_ft.n=0;
    for(unsigned i=0;i<1000;++i){bces_edge_job_begin(c);BCESEdgeSpan s=bces_edge_span_begin(c,0x6170,0x5740);bces_edge_span_end(s,c);bces_edge_job_end(c);}
    for(unsigned i=0;i<10000;++i)bces_edge_flow_reader(vm_base+0x210,32,1,0,0x210);
    unsigned roots=0,children=0,reader_samples=0;
    for(unsigned i=0;i<g_ps3_ft.n;++i){ps3_ft_rec*r=&g_ps3_ft.buf[i];roots+=r->kind==200&&r->a==0xE2A0;children+=r->kind==200&&r->a==0x5740;reader_samples+=r->kind==220;}
    assert(roots==1000&&children>30&&children<120&&reader_samples>80&&reader_samples<300&&!g_ps3_ft.dropped);
    assert(!memcmp(saved,c,sizeof *c));
    fprintf(stderr,"PASS: all 1000 job spans retained; sampled child jobs=%u/1000, reader requests=%u/10000; no dropped records\n",children,reader_samples);
    free(c);free(saved);free(vm_base);free(g_ps3_ft.buf);return 0;
}
