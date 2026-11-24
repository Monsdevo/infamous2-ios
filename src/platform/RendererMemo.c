#include "RendererMemo.h"
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

// Associative lookup, with global LRU eviction for the byte budget.
// Source snapshots, keys and outputs all count towards the 128 MiB/kind cap.
// There is no unbounded allocation and no retained guest pointer ownership.
enum { MAX_KEY=1024,MAX_ENTRY=8*1024*1024 };
static const size_t budget=128u*1024u*1024u;
typedef struct {
    uint8_t* allocation;
    size_t bytes,key_bytes,output_bytes;
    BCESMemoInput source[BCES_MEMO_INPUTS];
    unsigned count,ready;
    int prev,next;
    uint64_t hash,generation;
} Entry;
typedef struct {Entry* entries;size_t used;int head,tail;uint64_t generation;BCESMemoStats stats;} Cache;
static Cache caches[BCES_MEMO_KINDS];
static _Atomic unsigned modes[BCES_MEMO_KINDS];
static _Atomic unsigned faulted[BCES_MEMO_KINDS];
static _Atomic unsigned sequence;
static _Atomic uint64_t published[BCES_MEMO_KINDS][12];
static size_t aligned(size_t bytes){return (bytes+15u)&~(size_t)15u;}
static unsigned sets_for(unsigned kind){return kind==BCES_MEMO_VERTEX?4096:512;}
static unsigned ways_for(unsigned kind){return kind==BCES_MEMO_VERTEX?8:4;}
static unsigned slots_for(unsigned kind){return sets_for(kind)*ways_for(kind);}

void bces_renderer_memo_set(unsigned kind,unsigned mode){if(kind<BCES_MEMO_KINDS&&mode<=2&&(!mode||!atomic_load_explicit(&faulted[kind],memory_order_acquire)))atomic_store_explicit(&modes[kind],mode,memory_order_release);}
unsigned bces_renderer_memo_mode(unsigned kind){return kind<BCES_MEMO_KINDS?atomic_load_explicit(&modes[kind],memory_order_acquire):0;}
void bces_renderer_memo_note_call(unsigned kind){if(kind<BCES_MEMO_KINDS)caches[kind].stats.calls++;}
static uint64_t hash_bytes(uint64_t h,const void* data,size_t n){
    const uint8_t*p=data;
    while(n>=8){uint64_t word;memcpy(&word,p,8);h=(h^word)*1099511628211ull;p+=8;n-=8;}
    while(n--){h^=*p++;h*=1099511628211ull;}return h;
}
static void unlink_entry(Cache*c,int i){
    Entry*e=&c->entries[i];
    if(e->prev>=0)c->entries[e->prev].next=e->next;else c->head=e->next;
    if(e->next>=0)c->entries[e->next].prev=e->prev;else c->tail=e->prev;
}
static void touch(Cache*c,int i){
    Entry*e=&c->entries[i];e->prev=-1;e->next=c->head;
    if(c->head>=0)c->entries[c->head].prev=i;else c->tail=i;
    c->head=i;
}
static void discard(Cache*c,int i){
    Entry*e=&c->entries[i];if(!e->allocation)return;
    unlink_entry(c,i);c->used-=e->bytes;free(e->allocation);memset(e,0,sizeof(*e));c->stats.evictions++;
}
static void fill_ticket(Entry*e,unsigned i,unsigned mode,unsigned hit,BCESMemoTicket*t){
    memset(t,0,sizeof(*t));t->mode=mode;t->hit=hit;t->slot=i;t->generation=e->generation;t->count=e->count;
    const uint8_t*p=e->allocation+aligned(e->key_bytes);
    for(unsigned k=0;k<e->count;k++){t->inputs[k]=p;p+=aligned(e->source[k].bytes);}
    t->output=(void*)p;
}
int bces_renderer_memo_begin(unsigned kind,const void*key,size_t key_bytes,
    const BCESMemoInput*inputs,unsigned count,size_t output_bytes,BCESMemoTicket*t){
    if(kind>=BCES_MEMO_KINDS||!t)return 0;
    unsigned mode=bces_renderer_memo_mode(kind);if(!mode)return 0;
    Cache*c=&caches[kind];c->stats.lookups++;
    size_t bytes=aligned(key_bytes);
    if(!key||!key_bytes||key_bytes>MAX_KEY||!inputs||!count||count>BCES_MEMO_INPUTS||!output_bytes)goto bypass;
    for(unsigned k=0;k<count;k++){
        if(!inputs[k].data||!inputs[k].bytes||inputs[k].bytes>MAX_ENTRY||bytes>MAX_ENTRY-aligned(inputs[k].bytes))goto bypass;
        bytes+=aligned(inputs[k].bytes);
    }
    if(output_bytes>MAX_ENTRY||bytes>MAX_ENTRY-output_bytes)goto bypass;
    bytes+=output_bytes;
    if(!c->entries){c->entries=calloc(slots_for(kind),sizeof(Entry));if(!c->entries)goto bypass;c->used=slots_for(kind)*sizeof(Entry);c->head=c->tail=-1;}
    uint64_t hash=hash_bytes(1469598103934665603ull,key,key_bytes);
    for(unsigned k=0;k<count;k++){
        uintptr_t address=(uintptr_t)inputs[k].data;
        hash=hash_bytes(hash,&address,sizeof(address));hash=hash_bytes(hash,&inputs[k].bytes,sizeof(size_t));
    }
    // Avalanche aligned/regularly spaced source addresses before choosing a
    // set. Full keys and input bytes still decide equality, never this hash.
    uint64_t bucket=hash;bucket^=bucket>>33;bucket*=0xff51afd7ed558ccdull;
    bucket^=bucket>>33;bucket*=0xc4ceb9fe1a85ec53ull;bucket^=bucket>>33;
    unsigned ways=ways_for(kind),set=(unsigned)bucket&(sets_for(kind)-1),chosen=UINT_MAX,stale=UINT_MAX;uint64_t oldest;
    for(unsigned way=0;way<ways;way++){
        unsigned i=set*ways+way;Entry*e=&c->entries[i];
        if(!e->allocation){chosen=i;continue;}
        if(e->hash!=hash||e->key_bytes!=key_bytes||e->count!=count||e->output_bytes!=output_bytes||!e->ready||memcmp(e->allocation,key,key_bytes))continue;
        const uint8_t*p=e->allocation+aligned(key_bytes);int equal=1;
        for(unsigned k=0;k<count;k++){
            if(e->source[k].data!=inputs[k].data||e->source[k].bytes!=inputs[k].bytes){equal=0;break;}
            c->stats.compared_bytes+=inputs[k].bytes;
            if(memcmp(p,inputs[k].data,inputs[k].bytes)){equal=0;break;}p+=aligned(inputs[k].bytes);
        }
        if(!equal){stale=i;continue;}
        unlink_entry(c,i);touch(c,i);e->generation=++c->generation;
        c->stats.hits++;fill_ticket(e,i,mode,1,t);return 1;
    }
    if(stale!=UINT_MAX)chosen=stale;
    if(chosen==UINT_MAX){
        oldest=UINT64_MAX;
        for(unsigned way=0;way<ways;way++){unsigned i=set*ways+way;if(c->entries[i].generation<oldest){oldest=c->entries[i].generation;chosen=i;}}
    }
    discard(c,(int)chosen);
    while(c->used>budget-bytes&&c->tail>=0)discard(c,c->tail);
    Entry*e=&c->entries[chosen];uint8_t*allocation=malloc(bytes);if(!allocation)goto bypass;
    *e=(Entry){.allocation=allocation,.bytes=bytes,.key_bytes=key_bytes,.output_bytes=output_bytes,
               .count=count,.hash=hash,.generation=++c->generation};
    memcpy(allocation,key,key_bytes);uint8_t*p=allocation+aligned(key_bytes);
    for(unsigned k=0;k<count;k++){e->source[k]=inputs[k];memcpy(p,inputs[k].data,inputs[k].bytes);p+=aligned(inputs[k].bytes);c->stats.snapshot_bytes+=inputs[k].bytes;}
    c->used+=bytes;touch(c,(int)chosen);c->stats.misses++;fill_ticket(e,chosen,mode,0,t);return 1;
bypass:c->stats.bypasses++;return 0;
}
void bces_renderer_memo_commit(unsigned kind,const BCESMemoTicket*t,int valid){
    if(kind>=BCES_MEMO_KINDS||!t||t->slot>=slots_for(kind))return;Cache*c=&caches[kind];if(!c->entries)return;
    Entry*e=&c->entries[t->slot];if(!e->allocation||e->generation!=t->generation)return;
    if(valid){e->ready=1;c->stats.output_bytes+=e->output_bytes;}else discard(c,(int)t->slot);
}
void bces_renderer_memo_validation(unsigned kind,const BCESMemoTicket*t,int equal){
    if(kind>=BCES_MEMO_KINDS)return;Cache*c=&caches[kind];c->stats.validations++;
    if(!equal){c->stats.mismatches++;bces_renderer_memo_commit(kind,t,0);atomic_store_explicit(&faulted[kind],1,memory_order_release);bces_renderer_memo_set(kind,0);}
}
void bces_renderer_memo_clear(unsigned kind){
    if(kind>=BCES_MEMO_KINDS)return;Cache*c=&caches[kind];
    if(c->entries){for(unsigned i=0;i<slots_for(kind);i++)free(c->entries[i].allocation);free(c->entries);}
    memset(c,0,sizeof(*c));c->head=c->tail=-1;atomic_store_explicit(&faulted[kind],0,memory_order_release);
}
void bces_renderer_memo_publish(void){
    atomic_fetch_add_explicit(&sequence,1,memory_order_acq_rel);
    for(unsigned k=0;k<BCES_MEMO_KINDS;k++){
        Cache*c=&caches[k];uint64_t values[]={c->stats.calls,c->stats.lookups,c->stats.hits,c->stats.misses,c->stats.bypasses,c->stats.evictions,c->stats.validations,c->stats.mismatches,c->stats.compared_bytes,c->stats.snapshot_bytes,c->stats.output_bytes,c->used};
        for(unsigned i=0;i<12;i++)atomic_store_explicit(&published[k][i],values[i],memory_order_relaxed);
    }
    atomic_fetch_add_explicit(&sequence,1,memory_order_release);
}
BCESMemoStats bces_renderer_memo_stats(unsigned kind){
    BCESMemoStats s={0};if(kind>=BCES_MEMO_KINDS)return s;uint64_t values[12];
    for(;;){unsigned a=atomic_load_explicit(&sequence,memory_order_acquire);if(a&1)continue;
        for(unsigned i=0;i<12;i++)values[i]=atomic_load_explicit(&published[kind][i],memory_order_relaxed);
        if(a==atomic_load_explicit(&sequence,memory_order_acquire))break;
    }
    s=(BCESMemoStats){values[0],values[1],values[2],values[3],values[4],values[5],values[6],values[7],values[8],values[9],values[10],values[11],bces_renderer_memo_mode(kind)};return s;
}
