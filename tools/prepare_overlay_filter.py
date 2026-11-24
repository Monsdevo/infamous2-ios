"""Conservative upstream signature/page rejection, preserving eviction order."""
def function_span(source,name):
    start=source.index('void '+name+'(');brace=source.index('{',start);depth=1;i=brace+1
    # Selected functions contain no braces in string literals/comments.
    while depth:
        if source[i]=='{':depth+=1
        elif source[i]=='}':depth-=1
        i+=1
    return start,brace,i

FILTER=r'''
__attribute__((constructor)) static void bces_overlay_filter_available(void){bces_overlay_filter_compiled=1;}
/* Registration is rare; serialize publication and snapshot rebuilds. Each
 * reader owns its summary, so SPU threads never race writing shared bitsets.
 * Version invalidation includes metadata written after source_count grows. */
static SRWLOCK bces_overlay_registry_lock=SRWLOCK_INIT;
static uint64_t bces_overlay_generation=2;
static _Thread_local unsigned bces_overlay_registration_depth;
static void bces_overlay_registration_enter(void){
    if(!bces_overlay_registration_depth++){
        AcquireSRWLockExclusive(&bces_overlay_registry_lock);
        __atomic_fetch_add(&bces_overlay_generation,1,__ATOMIC_ACQ_REL);
    }
}
static void bces_overlay_registration_leave(void){
    if(!--bces_overlay_registration_depth){
        __atomic_store_n(&s_ovl_summary_n,-1,__ATOMIC_RELEASE);
        __atomic_fetch_add(&bces_overlay_generation,1,__ATOMIC_RELEASE);
        ReleaseSRWLockExclusive(&bces_overlay_registry_lock);
    }
}
typedef struct {uint64_t version,ea[64],sig[64],pages[4];} BCESOverlaySummary;
static _Thread_local BCESOverlaySummary bces_overlay_summary;
static int bces_overlay_candidate(uint32_t ea,const uint8_t* ls,uint32_t lsa,uint32_t size){
    uint64_t version=__atomic_load_n(&bces_overlay_generation,__ATOMIC_ACQUIRE);
    if(version&1u)return 0;
    BCESOverlaySummary* s=&bces_overlay_summary;
    if(s->version!=version){
        AcquireSRWLockShared(&bces_overlay_registry_lock);
        memset(s,0,sizeof *s);
        for(int i=0;i<s_ovl_src_count;i++){
            const spu_ovl_src* o=&s_ovl_src[i];
            if(o->has_sig){uint32_t w;memcpy(&w,o->sig,4);unsigned h=ovl_ea_hash(w);s->sig[h>>6]|=1ull<<(h&63);}
            else {unsigned h=ovl_ea_hash(o->src_ea);s->ea[h>>6]|=1ull<<(h&63);}
            if(o->lift_lsa && o->span){
                uint64_t last=((uint64_t)o->lift_lsa+o->span-1)>>10;
                for(uint64_t page=o->lift_lsa>>10;page<=last && page<256;page++)s->pages[page>>6]|=1ull<<(page&63);
            }
        }
        s->version=__atomic_load_n(&bces_overlay_generation,__ATOMIC_ACQUIRE);
        ReleaseSRWLockShared(&bces_overlay_registry_lock);version=s->version;
    }
    if(lsa>=SPU_LS_SIZE || (uint64_t)lsa+size>SPU_LS_SIZE)return 0;
    if(size>=512){uint32_t w;memcpy(&w,ls,4);unsigned h=ovl_ea_hash(w);if(s->sig[h>>6]&(1ull<<(h&63)))return 0;}
    unsigned h=ovl_ea_hash(ea);if(s->ea[h>>6]&(1ull<<(h&63)))return 0;
    if(size)for(uint32_t page=lsa>>10;page<=((lsa+size-1)>>10);page++)if(s->pages[page>>6]&(1ull<<(page&63)))return 0;
    return __atomic_load_n(&bces_overlay_generation,__ATOMIC_ACQUIRE)==version;
}
/* Exact possible-match predicate from the original source walk. A rejection
 * is allowed only when no source can match. Used only in validation mode. */
static int bces_overlay_exact_match(uint32_t ea,const uint8_t* ls,uint32_t lsa,uint32_t size){
    for(int i=0;i<s_ovl_src_count;i++){
        const spu_ovl_src* o=&s_ovl_src[i];
        if(!o->lift_lsa){if(o->has_sig?(size>=512 && !memcmp(ls,o->sig,16)):(o->src_ea==ea))return 1;continue;}
        uint32_t lo=lsa>o->lift_lsa?lsa:o->lift_lsa;
        uint32_t hi=lsa+size<o->lift_lsa+o->span?lsa+size:o->lift_lsa+o->span;
        if(lo<hi && (hi-lo>=128 || hi-lo==size) && gm_equal(vm_base+o->src_ea+(lo-o->lift_lsa),ls+(lo-lsa),hi-lo)){
            for(uint32_t k=0;k<hi-lo;k++)if(ls[lo-lsa+k])return 1;
        }
    }
    return 0;
}
static inline int bces_overlay_cannot_match(uint32_t ea,const uint8_t* ls,uint32_t lsa,uint32_t size){
    unsigned mode=__atomic_load_n(&bces_overlay_filter_mode,__ATOMIC_RELAXED);
    if(!mode)return ovl_cannot_match(ea,lsa,size);
    int reject=bces_overlay_candidate(ea,ls,lsa,size);
    if(mode==2){
        __atomic_fetch_add(&bces_overlay_checks,1,__ATOMIC_RELAXED);
        if(reject){
            __atomic_fetch_add(&bces_overlay_rejects,1,__ATOMIC_RELAXED);
            if(!ovl_cannot_match(ea,lsa,size))__atomic_fetch_add(&bces_overlay_extra_rejects,1,__ATOMIC_RELAXED);
            AcquireSRWLockShared(&bces_overlay_registry_lock);
            int match=bces_overlay_exact_match(ea,ls,lsa,size);
            ReleaseSRWLockShared(&bces_overlay_registry_lock);
            if(match){__atomic_fetch_add(&bces_overlay_mismatches,1,__ATOMIC_RELAXED);bces_overlay_filter_set(0);return 0;}
        }
    }
    return reject;
}
'''

def patch(source):
    original=source
    marker='typedef struct { uint32_t src_ea; int image_id; uint8_t sig[16]; int has_sig; uint32_t span; uint32_t lift_lsa; int reloc; } spu_ovl_src;'
    assert source.count(marker)==1
    source=source.replace(marker,'static void bces_overlay_registration_enter(void);\nstatic void bces_overlay_registration_leave(void);\n'+marker,1)
    functions=[('spu_overlay_register_source','uint32_t content_ea, int image_id','content_ea,image_id'),('spu_overlay_register_region','uint32_t content_ea, uint32_t span, int image_id','content_ea,span,image_id'),('spu_overlay_register_region_at','uint32_t content_ea, uint32_t lsa, uint32_t span, int image_id','content_ea,lsa,span,image_id'),('spu_overlay_register_region_reloc','uint32_t content_ea, uint32_t span, int image_id','content_ea,span,image_id'),('spu_overlay_register_sig','const uint8_t sig[16], int image_id','sig,image_id')]
    for name,args,call in functions:
        start,brace,end=function_span(source,name)
        body=source[start:end].replace('void '+name+'(','static void '+name+'_impl(',1)
        wrapper='\nvoid '+name+'('+args+'){bces_overlay_registration_enter();'+name+'_impl('+call+');bces_overlay_registration_leave();}\n'
        source=source[:start]+body+wrapper+source[end:]
    marker='void spu_overlay_note_get(spu_context* ctx, uint32_t ea, const uint8_t* ls, uint32_t size)'
    assert source.count(marker)==1
    source=source.replace(marker,FILTER+'\n'+marker,1)
    needle='    if (ovl_cannot_match(ea, lsa, size)) return;'
    assert source.count(needle)==1
    source=source.replace(needle,'    if (bces_overlay_cannot_match(ea, ls, lsa, size)) return;',1)
    # The whole note_get body, including eviction and source ordering, is
    # byte-identical apart from that single predicate substitution.
    old=original[function_span(original,'spu_overlay_note_get')[0]:function_span(original,'spu_overlay_note_get')[2]]
    new=source[function_span(source,'spu_overlay_note_get')[0]:function_span(source,'spu_overlay_note_get')[2]]
    assert new.replace('bces_overlay_cannot_match(ea, ls, lsa, size)','ovl_cannot_match(ea, lsa, size)',1)==old
    return '#include "OverlayFilterControl.h"\n'+source
