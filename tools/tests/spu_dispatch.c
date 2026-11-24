/* Included after the actual upstream fixture; its syscall/service stubs apply. */
#include "SpuDispatchControl.h"
extern void spu_overlay_register_region_reloc(uint32_t,uint32_t,int);
static void dispatch_base(spu_context*c){c->gpr[3]=spu_il(100);}
static void dispatch_overlay(spu_context*c){c->gpr[3]=spu_il(230);}
static void dispatch_owner(spu_context*c){c->gpr[3]=spu_il(231);}
static void dispatch_task(spu_context*c){c->gpr[3]=spu_il(232);}
static int dispatch_equivalence(int expect_fast){
    spu_begin_image(100);spu_register_function(0x4500,dispatch_base);spu_register_function(0xA70,dispatch_base);
    spu_begin_image(230);spu_register_function(0x4500,dispatch_overlay);spu_register_function(0x5500,dispatch_overlay);
    spu_begin_image(231);spu_register_function(0x5500,dispatch_owner);
    spu_begin_image(232);spu_register_function(0x5500,dispatch_task);spu_begin_image(0);
    spu_begin_image(233);spu_register_function(0x200,dispatch_owner);spu_begin_image(0);
    spu_overlay_register_region_reloc(0x500000,0x1000,233);
    spu_context*ref=calloc(1,sizeof(*ref));spu_context*fast=calloc(1,sizeof(*fast));
    if(!ref||!fast)return 1;
    for(unsigned trial=0;trial<512;trial++){
        spu_context_init(ref,0x2000);ref->image_id=100;ref->resident_ovl=230;ref->host_depth=1;
        ref->pc=trial&1?0x4500:0x80004500;ref->code_base=0x1234;ref->spu_id=0x2000;
        if(trial&2){ref->irq_saved=1;ref->irq_resume_pc=0x9000;ref->int_enable=1;}
        if(trial&4){ref->pc=0x5500;ref->resident_code[0].image_id=231;ref->resident_code[0].lsa=0x5000;ref->resident_code[0].size=0x1000;}
        if(trial&8){ref->pc=0x5500;ref->resident_task=232;ref->resident_code[0].image_id=0;}
        if(trial&16){ref->pc=0xA70;ref->irq_saved=0;ref->resident_task=0;ref->resident_code[0].image_id=0;}
        if(trial&32){ref->irq_saved=1;ref->irq_resume_pc=ref->pc;ref->int_enable=1;ref->host_depth=0;ref->irq_gpr[4]=spu_il(123);}
        if(trial&64){ref->policy_mode=1;ref->irq_saved=0;}
        if(trial&128){ref->pc=0x6200;ref->resident_code[0].image_id=233;ref->resident_code[0].lsa=0x6000;ref->resident_code[0].size=0x1000;ref->resident_code[0].reloc=1;}
        if((trial&32)&&ref->irq_saved)ref->irq_resume_pc=ref->pc;
        if(trial&256)ref->int_enable=0;
        memcpy(fast,ref,sizeof(*fast));
        fast->ls=fast->ls_store;
        bces_spu_dispatch_set(0,1);spu_indirect_branch(ref);
        bces_spu_dispatch_set(1,1);spu_indirect_branch(fast);
        uint8_t* local_store=fast->ls;fast->ls=ref->ls;
        if(memcmp(ref,fast,sizeof(*ref))){fprintf(stderr,"Dispatch context mismatch trial%u\n",trial);return 1;}
        fast->ls=local_store;
    }
    BCESDispatchStats stats=bces_spu_dispatch_stats();
    if(expect_fast && !stats.fast){fprintf(stderr,"No candidate fast dispatch admitted\n");return 1;}
    free(ref);free(fast);printf("PASS512 actual-resolver full-context differential cases; fast=%llu fallback=%llu\n",(unsigned long long)stats.fast,(unsigned long long)stats.fallback);return 0;
}
