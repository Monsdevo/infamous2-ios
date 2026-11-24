"""ABI-preserving MFC slot hint; original scan/claim/release stay intact."""
WRAPPER='''
/* The slot array lives for the process lifetime. TLS holds one last slot,
 * never a guest context field; switching contexts simply causes a miss.
 * Every hit rechecks the atomic owner. No counters in performance modes. */
static _Thread_local spu_mfc_slot* bces_mfc_last_slot;
static inline mfc_engine* mfc_for(spu_context* ctx)
{
    unsigned mode=__atomic_load_n(&bces_mfc_hint_mode,__ATOMIC_RELAXED);
    if (!mode) return mfc_for_scan(ctx);
    spu_mfc_slot* hint=bces_mfc_last_slot;
    mfc_engine* e=NULL;
    int hit=hint && __atomic_load_n(&hint->ctx,__ATOMIC_ACQUIRE)==ctx;
    if (hit) e=&hint->mfc;
    else {
        e=mfc_for_scan(ctx);
        uintptr_t address=(uintptr_t)e;
        uintptr_t first=(uintptr_t)&s_mfc_slots[0].mfc;
        uintptr_t stride=sizeof(spu_mfc_slot);
        if(address>=first && (address-first)/stride<SPU_MAX_CONTEXTS && (address-first)%stride==0)
            bces_mfc_last_slot=&s_mfc_slots[(address-first)/stride];
        else bces_mfc_last_slot=NULL; /* original shared-overflow fallback */
    }
    if(mode==2){
        mfc_engine* oracle=mfc_for_scan(ctx);
        __atomic_fetch_add(&bces_mfc_hint_checks,1,__ATOMIC_RELAXED);
        if(hit)__atomic_fetch_add(&bces_mfc_hint_hits,1,__ATOMIC_RELAXED);
        if(e!=oracle){
            __atomic_fetch_add(&bces_mfc_hint_mismatches,1,__ATOMIC_RELAXED);
            bces_mfc_hint_set(0);return oracle;
        }
    }
    return e;
}
'''
def patch(source):
    needle='static mfc_engine* mfc_for(spu_context* ctx)\n'
    assert source.count(needle)==1
    source=source.replace(needle,'static mfc_engine* mfc_for_scan(spu_context* ctx)\n',1)
    marker='/* Give the slot `ctx` holds back to the table, called when its context is done.'
    assert source.count(marker)==1
    return '#include "MfcHintControl.h"\n'+source.replace(marker,WRAPPER+'\n'+marker,1)
