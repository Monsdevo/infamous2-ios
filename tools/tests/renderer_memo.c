#include "RendererMemo.h"
#include "TextureHashMemo.h"
#include "VertexFetchMemo.h"
#include "rsx_vertex_compact.h"
#include "rsx_vertex_formats.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fenv.h>
static unsigned hash_calls;
static uint64_t hash_a(const uint8_t*p,uint32_t n){hash_calls++;uint64_t h=42;for(unsigned i=0;i<n;i++)h=(h^p[i])*1099511628211ull;return h;}
static uint64_t hash_b(const uint8_t*p,uint32_t n){return hash_a(p,n)^123;}
static void texture_test(void){
    uint8_t bytes[79];for(unsigned i=0;i<sizeof bytes;i++)bytes[i]=(uint8_t)i;
    bces_renderer_memo_set(BCES_MEMO_TEXTURE,1);
    uint64_t expected=hash_a(bytes,sizeof bytes);hash_calls=0;
    assert(bces_texture_hash_memo(bytes,sizeof bytes,hash_a)==expected);assert(hash_calls==1);
    assert(bces_texture_hash_memo(bytes,sizeof bytes,hash_a)==expected);assert(hash_calls==1);
    bytes[78]^=7;expected=hash_a(bytes,sizeof bytes);hash_calls=0;
    assert(bces_texture_hash_memo(bytes,sizeof bytes,hash_a)==expected);assert(hash_calls==1);
    assert(bces_texture_hash_memo(bytes,sizeof bytes,hash_b)==(expected^123));assert(hash_calls==2);
    bces_renderer_memo_set(BCES_MEMO_TEXTURE,2);
    assert(bces_texture_hash_memo(bytes,sizeof bytes,hash_a)==expected);assert(hash_calls==3);
    bces_renderer_memo_publish();BCESMemoStats s=bces_renderer_memo_stats(BCES_MEMO_TEXTURE);
    assert(s.hits>=2&&s.misses>=3&&s.validations==1&&s.mismatches==0);
    bces_renderer_memo_clear(BCES_MEMO_TEXTURE);
}
static uint8_t source[16384];
static const u8* resolve(void*unused,u32 location,u32 offset,u32 count){(void)unused;(void)location;return offset+count<=sizeof source?source+offset:NULL;}
static unsigned cases;
static void compare(rsx_vertex_fetch_plan*p,rsx_vertex_ref*refs,unsigned n){
    uint8_t a[128*256],b[128*256];memset(a,0xa5,sizeof a);memset(b,0xa5,sizeof b);
    int ar=rsx_vertex_fetch_all(p,refs,n,a),br=bces_vertex_fetch_copy(p,refs,n,b);
    assert(ar==br);assert(!memcmp(a,b,sizeof a));cases++;
}
static void vertex_test(void){
    for(unsigned i=0;i<sizeof source;i++)source[i]=(uint8_t)(i*137+(i>>7));
    rsx_vertex_ref refs[128];for(unsigned i=0;i<128;i++)refs[i]=(rsx_vertex_ref){(i*79)&127,0};
    rsx_vertex_fetch_plan p={0};p.layout.count=3;p.layout.stride=48;p.guest_ptr=resolve;
    for(unsigned k=0;k<3;k++){p.layout.attrs[k]=k;p.attr[k].default_value[3]=1;}
    for(unsigned mode=0;mode<3;mode++){
        bces_renderer_memo_set(BCES_MEMO_VERTEX,mode);
        for(unsigned type=0;type<=8;type++)for(unsigned size=0;size<=5;size++)for(unsigned freq=0;freq<=3;freq++){
            p.divider_mask=(freq&1)?7:0;
            for(unsigned k=0;k<3;k++){
                rsx_vertex_fetch_attr*f=&p.attr[k];f->desc.type=type;f->desc.size=size;f->desc.frequency=freq;
                f->stride=32;f->elem_size=20;f->stable_base=source+k*2;f->stable_first=0;f->stable_last=127;
            }
            compare(&p,refs,128);compare(&p,refs,128);
            source[16]^=1;compare(&p,refs,128);source[16]^=1;
            refs[59].vertex_id^=3;compare(&p,refs,128);refs[59].vertex_id^=3;
            p.attr[1].default_value[0]=2;compare(&p,refs,128);p.attr[1].default_value[0]=0;
        }
    }
    bces_renderer_memo_set(BCES_MEMO_VERTEX,2);
    p.attr[0].stable_base=NULL;p.attr[0].desc.offset=20000;p.attr[0].desc.type=2;p.attr[0].desc.size=3;
    compare(&p,refs,128); // Invalid ATTR0 retains failure and partial-write behavior.
    p.inline_data=source;compare(&p,refs,128); // Missing inline source stays on reference.
    p=(rsx_vertex_fetch_plan){0};p.layout.count=1;p.layout.stride=16;
    p.attr[0].desc.type=2;p.attr[0].desc.size=3;p.attr[0].stride=16;p.attr[0].elem_size=12;
    p.attr[0].stable_base=source;p.attr[0].stable_last=127;
    uint8_t owned[128*16],expected[128*16];int ok;
    assert(rsx_vertex_fetch_all(&p,refs,128,expected));
    const u8*borrowed=bces_vertex_fetch_borrow(&p,refs,128,owned,&ok);assert(ok&&borrowed==owned&&!memcmp(borrowed,expected,sizeof expected));
    bces_renderer_memo_set(BCES_MEMO_VERTEX,1);
    borrowed=bces_vertex_fetch_borrow(&p,refs,128,owned,&ok);assert(ok&&borrowed!=owned&&!memcmp(borrowed,expected,sizeof expected));
    int rounding=fegetround();p.attr[0].desc.type=RSX_VTX_TYPE_SNORM16;
    assert(!fesetround(FE_UPWARD));compare(&p,refs,128);
    assert(!fesetround(FE_DOWNWARD));compare(&p,refs,128);
    assert(!fesetround(rounding));
    // Texture work between preparation and backend staging has separate storage.
    (void)bces_texture_hash_memo(source,1024,hash_a);assert(!memcmp(borrowed,expected,sizeof expected));
    bces_renderer_memo_publish();BCESMemoStats s=bces_renderer_memo_stats(BCES_MEMO_VERTEX);
    assert(s.hits&&s.misses&&s.validations&&s.mismatches==0);
    bces_renderer_memo_clear(BCES_MEMO_VERTEX);
}
static void guard_and_budget_test(void){
    size_t page=(size_t)sysconf(_SC_PAGESIZE);uint8_t*mem=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    assert(mem!=MAP_FAILED);assert(!mprotect(mem+page,page,PROT_NONE));
    uint8_t*edge=mem+page-6;memset(edge,7,6);BCESMemoInput input={edge,6};BCESMemoTicket t;uint32_t key=1;
    bces_renderer_memo_set(BCES_MEMO_TEXTURE,1);
    assert(bces_renderer_memo_begin(BCES_MEMO_TEXTURE,&key,sizeof key,&input,1,17,&t));
    assert(!((uintptr_t)t.inputs[0]&15)&&!((uintptr_t)t.output&15));memset(t.output,5,17);bces_renderer_memo_commit(BCES_MEMO_TEXTURE,&t,1);
    assert(bces_renderer_memo_begin(BCES_MEMO_TEXTURE,&key,sizeof key,&input,1,17,&t)&&t.hit);
    // One input byte changes at the same address; pointer equality is insufficient.
    edge[5]++;assert(bces_renderer_memo_begin(BCES_MEMO_TEXTURE,&key,sizeof key,&input,1,17,&t)&&!t.hit);bces_renderer_memo_commit(BCES_MEMO_TEXTURE,&t,0);
    assert(!munmap(mem,page*2));bces_renderer_memo_clear(BCES_MEMO_TEXTURE);
    const size_t size=1024*1024;uint8_t*large=malloc(size);assert(large);memset(large,3,size);input=(BCESMemoInput){large,size};
    for(key=1;key<=150;key++){
        assert(bces_renderer_memo_begin(BCES_MEMO_TEXTURE,&key,sizeof key,&input,1,1,&t));*(uint8_t*)t.output=4;bces_renderer_memo_commit(BCES_MEMO_TEXTURE,&t,1);
    }
    bces_renderer_memo_publish();BCESMemoStats s=bces_renderer_memo_stats(BCES_MEMO_TEXTURE);
    assert(s.resident_bytes<=128u*1024u*1024u&&s.evictions>0);
    bces_renderer_memo_validation(BCES_MEMO_TEXTURE,&t,0);assert(bces_renderer_memo_mode(BCES_MEMO_TEXTURE)==0);
    bces_renderer_memo_clear(BCES_MEMO_TEXTURE);free(large);
}
int main(void){texture_test();vertex_test();guard_and_budget_test();printf("PASS %u decoder comparisons; exact byte mutation, reference/validation modes, callback identity, guard-page bounds, alignment, bounded LRU and mismatch fallback\n",cases);}
