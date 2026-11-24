"""Full fast-resolver result cache with conservative sidecar residency snapshot.
No context ABI change, no task-table caching, no changes to slow-path routing.
"""
def patch(s):
 marker='static uint32_t s_registry_count = 0;'
 assert s.count(marker)==1
 s=s.replace(marker,marker+'\nstatic uint64_t bces_ib_registry_generation;')
 for marker in ('            s_registry[i].fn = fn;','    s_hash_tail[h] = i + 1;','        s_reloc_img[image_id] = 1;'):
  assert s.count(marker)==1,marker
  s=s.replace(marker,marker+'\n    __atomic_add_fetch(&bces_ib_registry_generation,1,__ATOMIC_RELEASE);')
 marker='void spu_indirect_branch(spu_context* ctx)\n{'
 assert s.count(marker)==1
 declarations='''
/* Per native thread, but keyed by context identity and ALL resident descriptors.
 * A reused pointer with identical state has identical resolution semantics.
 * Registry generation also changes on function replacement/reloc registration.
 * Dynamic task tables and diagnostics are never bypassed. */
typedef struct {uint32_t pc;int image,ovl,task;uint64_t generation;spu_fn fn;
 int set_base;uint32_t base;} BCESIBEntry;
static _Thread_local struct {
 const spu_context* context;
 unsigned char resident[sizeof(((spu_context*)0)->resident_code)];
 BCESIBEntry entries[256];
} bces_ib_local;
'''
 s=s.replace(marker,declarations+'\n'+marker)
 start=s.index(marker);a=s.index('        spu_fn fn = NULL;',start);b=s.index('        ctx->pc = pc;',a)
 original=s[a:b]
 assert original.count('if (!fn) goto slow;')==1
 intro='''        unsigned ib_mode=__atomic_load_n(&bces_ib_mode,__ATOMIC_ACQUIRE);
        BCESIBEntry* ib_entry=NULL;spu_fn ib_expected=NULL;uint32_t ib_expected_base=0;
        int ib_expected_set_base=0;
        BCESIBCounts* ib_stats=&bces_ib_counts[ctx->spu_id&15u];
        uint64_t ib_generation=__atomic_load_n(&bces_ib_registry_generation,__ATOMIC_ACQUIRE);
        if(ib_mode && !(pc>=SPU_TASKSET_TASK_LO && (s_task_elf_count || s_task_entry_count))){
            if(bces_ib_local.context!=ctx || memcmp(bces_ib_local.resident,ctx->resident_code,sizeof(ctx->resident_code))){
                memset(bces_ib_local.entries,0,sizeof(bces_ib_local.entries));
                bces_ib_local.context=ctx;
                memcpy(bces_ib_local.resident,ctx->resident_code,sizeof(ctx->resident_code));
            }
            ib_entry=&bces_ib_local.entries[(pc>>2)&255u];
            if(ib_entry->fn && ib_entry->pc==pc && ib_entry->image==ctx->image_id &&
               ib_entry->ovl==ctx->resident_ovl && ib_entry->task==ctx->resident_task &&
               ib_entry->generation==ib_generation){
                ib_expected=ib_entry->fn;ib_expected_base=ib_entry->base;
                ib_expected_set_base=ib_entry->set_base;
                __atomic_fetch_add(&ib_stats->hit,1,__ATOMIC_RELAXED);
                if(ib_mode==1){
                    if(ib_expected_set_base)ctx->code_base=ib_expected_base;
                    ctx->pc=pc;ctx->resident_task=rt;
                    if(bces_count)__atomic_fetch_add(&bces_stats->fast,1,__ATOMIC_RELAXED);
                    spu_check_stack_reset(ctx,ib_expected);
                    ib_expected(ctx);return;
                }
            }else __atomic_fetch_add(&ib_stats->miss,1,__ATOMIC_RELAXED);
        }
'''
 # Keep tail-call behavior on cached hits: no new native stack growth.
 intro=intro.replace('                    ib_expected(ctx);return;', '''#if defined(__clang__)
                    __attribute__((musttail)) return ib_expected(ctx);
#else
                    ib_expected(ctx);return;
#endif''')
 body=original.replace('        int code_owner = 0;','        int code_owner = 0;int ib_set_base=0;')
 body=body.replace('                    ctx->code_base = ctx->resident_code[slot].lsa;','                    {ctx->code_base = ctx->resident_code[slot].lsa;ib_set_base=1;}')
 assert 'ib_set_base=1' in body
 body=body.replace('        if (!fn) goto slow;', '''        if (!fn) {if(ib_expected){__atomic_fetch_add(&ib_stats->fault,1,__ATOMIC_RELAXED);bces_ib_set(0);} goto slow;}''')
 tail='''        if(ib_expected){
            __atomic_fetch_add(&ib_stats->validated,1,__ATOMIC_RELAXED);
            if(fn!=ib_expected || ib_set_base!=ib_expected_set_base || (ib_set_base && ctx->code_base!=ib_expected_base)){
                __atomic_fetch_add(&ib_stats->fault,1,__ATOMIC_RELAXED);
                bces_ib_set(0);ib_entry=NULL;
            }
        }
        if(ib_entry){*ib_entry=(BCESIBEntry){.pc=pc,.image=ctx->image_id,.ovl=ctx->resident_ovl,
            .task=ctx->resident_task,.generation=ib_generation,.fn=fn,.set_base=ib_set_base,.base=ctx->code_base};}
'''
 s=s[:a]+intro+body+tail+s[b:]
 return '#include "HostIBCache.h"\n'+s
