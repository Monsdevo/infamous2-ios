#include "RendererMemo.h"
#include "VertexFetchMemo.h"
#include "rsx_vertex_compact.h"
#include "rsx_vertex_formats.h"
#include <stdint.h>
#include <string.h>
#include <stddef.h>

// The working runtime archive supplies rsx_vertex_fetch_all unchanged.
typedef struct {uintptr_t start,end;} Range;
typedef struct {
    uint64_t source;
    u32 attr,type,size,frequency,stride,elem_size,first,last,defaults[4];
} AttrKey;
typedef struct {u32 count,stride,slots,base,divider;AttrKey attrs[16];} FetchKey;
_Static_assert(sizeof(FetchKey)<=1024,"memo key bound");
static int memo_rounding_supported(void){
#if defined(__aarch64__)
    uint64_t control;__asm__ volatile("mrs %0, fpcr":"=r"(control));
    // Numeric normalization is admitted only with round-to-nearest and
    // masked FP traps. Other callers retain the original decoder directly.
    return !(control&((3ull<<22)|0x9f00u));
#else
    return 0;
#endif
}

static int fetch_memo(const rsx_vertex_fetch_plan*plan,const rsx_vertex_ref*refs,u32 count,u8*out,const u8**borrowed){
    if(borrowed)*borrowed=out;
    if(!bces_renderer_memo_mode(BCES_MEMO_VERTEX))return rsx_vertex_fetch_all(plan,refs,count,out);
    bces_renderer_memo_note_call(BCES_MEMO_VERTEX);
    if(!memo_rounding_supported()||!plan||!refs||!out||!count||
       !plan->layout.count||plan->layout.count>16||plan->layout.stride!=16u*plan->layout.count)
        return rsx_vertex_fetch_all(plan,refs,count,out);
    FetchKey key;Range ranges[16];unsigned nr=0;
    size_t key_bytes=offsetof(FetchKey,attrs)+plan->layout.count*sizeof(AttrKey);
    memset(&key,0,key_bytes);
    key.count=count;key.stride=plan->layout.stride;key.slots=plan->layout.count;
    key.base=plan->base_offset;key.divider=plan->divider_mask;
    for(unsigned slot=0;slot<plan->layout.count;slot++){
        unsigned attr=plan->layout.attrs[slot];if(attr>=16)goto reference;
        const rsx_vertex_fetch_attr*f=&plan->attr[attr];AttrKey*k=&key.attrs[slot];
        *k=(AttrKey){.source=(uintptr_t)f->stable_base,.attr=attr,.type=f->desc.type,
            .size=f->desc.size,.frequency=f->desc.frequency,.stride=f->stride,
            .elem_size=f->elem_size,.first=f->stable_first,.last=f->stable_last};
        memcpy(k->defaults,f->default_value,16);
        if(!f->desc.type||!f->desc.size)continue;
        // Restrict to mappings which the reference actually reads without
        // invoking the guest resolver. Malformed, sparse/unmapped and missing
        // inline attributes retain the original behavior, including failures.
        if(!f->stable_base||!f->elem_size||f->stable_last<f->stable_first)goto reference;
        uint64_t bytes=(uint64_t)(f->stable_last-f->stable_first)*f->stride+f->elem_size;
        uintptr_t begin=(uintptr_t)f->stable_base;
        if(!bytes||bytes>8u*1024u*1024u||begin>UINTPTR_MAX-bytes)goto reference;
        ranges[nr++]=(Range){begin,begin+(uintptr_t)bytes};
    }
    // Interleaved attributes often map overlapping ranges. Snapshot their
    // union once rather than retaining one entire stream per attribute.
    for(unsigned i=1;i<nr;i++){Range r=ranges[i];unsigned j=i;while(j&&ranges[j-1].start>r.start){ranges[j]=ranges[j-1];j--;}ranges[j]=r;}
    unsigned merged=0;
    for(unsigned i=0;i<nr;i++){
        if(merged&&ranges[i].start<=ranges[merged-1].end){if(ranges[i].end>ranges[merged-1].end)ranges[merged-1].end=ranges[i].end;}
        else ranges[merged++]=ranges[i];
    }
    BCESMemoInput inputs[BCES_MEMO_INPUTS];inputs[0]=(BCESMemoInput){refs,(size_t)count*sizeof(*refs)};
    for(unsigned i=0;i<merged;i++)inputs[i+1]=(BCESMemoInput){(const void*)ranges[i].start,ranges[i].end-ranges[i].start};
    uint64_t output_bytes=(uint64_t)count*plan->layout.stride;if(output_bytes>SIZE_MAX)goto reference;
    BCESMemoTicket ticket;
    if(!bces_renderer_memo_begin(BCES_MEMO_VERTEX,&key,key_bytes,
        inputs,merged+1,(size_t)output_bytes,&ticket))goto reference;
    if(!ticket.hit){
        // On a hit the exact same refs and metadata were already admitted.
        // Only misses need the per-reference mapping proof. Check the owned
        // snapshot which will actually be decoded, not a changing live span.
        const rsx_vertex_ref* saved_refs=ticket.inputs[0];
        for(unsigned slot=0;slot<plan->layout.count;slot++){
            unsigned attr=plan->layout.attrs[slot];const rsx_vertex_fetch_attr*f=&plan->attr[attr];
            if(!f->desc.type||!f->desc.size)continue;
            for(u32 i=0;i<count;i++){
                u32 element=rsx_vertex_element_index(saved_refs[i].vertex_id,saved_refs[i].base_index,
                    f->desc.frequency,(plan->divider_mask>>attr)&1u);
                if(element<f->stable_first||element>f->stable_last){bces_renderer_memo_commit(BCES_MEMO_VERTEX,&ticket,0);goto reference;}
            }
        }
        rsx_vertex_fetch_plan snapshot=*plan;
        snapshot.guest_ptr=NULL;snapshot.guest_user=NULL;
        // An inline plan may retain its marker, but every active reference
        // was proved to use stable_base; no inline fallback is consulted.
        for(unsigned slot=0;slot<plan->layout.count;slot++){
            unsigned attr=plan->layout.attrs[slot];uintptr_t address=(uintptr_t)plan->attr[attr].stable_base;
            if(!plan->attr[attr].desc.type||!plan->attr[attr].desc.size)continue;
            for(unsigned i=0;i<merged;i++)if(address>=ranges[i].start&&address<ranges[i].end){
                snapshot.attr[attr].stable_base=(const u8*)ticket.inputs[i+1]+address-ranges[i].start;break;
            }
        }
        int ok=rsx_vertex_fetch_all(&snapshot,ticket.inputs[0],count,ticket.output);
        bces_renderer_memo_commit(BCES_MEMO_VERTEX,&ticket,ok);
        if(!ok)goto reference;
    }
    if(ticket.mode==2){
        int ok=rsx_vertex_fetch_all(plan,refs,count,out);
        bces_renderer_memo_validation(BCES_MEMO_VERTEX,&ticket,ok&&!memcmp(out,ticket.output,(size_t)output_bytes));
        return ok; // Validation always renders the live original result.
    }
    if(borrowed)*borrowed=ticket.output;
    else memcpy(out,ticket.output,(size_t)output_bytes);
    return 1;
reference:
    return rsx_vertex_fetch_all(plan,refs,count,out);
}
int bces_vertex_fetch_copy(const rsx_vertex_fetch_plan*p,const rsx_vertex_ref*r,u32 n,u8*out){return fetch_memo(p,r,n,out,NULL);}
const u8* bces_vertex_fetch_borrow(const rsx_vertex_fetch_plan*p,const rsx_vertex_ref*r,u32 n,u8*out,int*ok){
    const u8* borrowed=out;*ok=fetch_memo(p,r,n,out,&borrowed);return borrowed;
}
