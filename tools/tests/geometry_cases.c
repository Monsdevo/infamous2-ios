#define main skinning_replay_main
#include "skinning_replay.c"
#undef main
#include "EdgeGeometrySnapshot.h"
#include "spu_helpers.h"
int bces_geometry_skin_arm64(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*);
int bces_geometry_cull_arm64(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*);
int bces_geometry_skin_parallel(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*);
int bces_geometry_skin_flat(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*);
int bces_geometry_cull_flat(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*);
static void original(spu_context*c,unsigned root,uint32_t ret){c->pc=root;c->tramp_fn=NULL;skin_dispatch(c);spu_drain_call(c,ret);}
int main(int argc,char**argv){
    assert(argc==3);FILE*f=fopen(argv[1],"rb");assert(f);EdgeSnapshot*seed=malloc(sizeof *seed);assert(seed&&fread(seed,sizeof *seed,1,f)==1);fclose(f);
    assert(seed->magic==0x45444745&&seed->context_size==sizeof(spu_context));
    unsigned attributes=seed->input.gpr[97]._u32[0],available=(seed->input.gpr[101]._u32[0]-seed->input.gpr[100]._u32[0])/(16*attributes);assert(attributes&&attributes<=3&&available>0&&available<=1024);
    unsigned cases[]={4,8,16,32,available};unsigned index=0;
    for(unsigned sample=0;sample<5;sample++){
        SkinningSnapshot*s=calloc(1,sizeof *s);assert(s);s->magic=0x534b494e;s->version=1;s->context_size=sizeof(spu_context);s->index=index;
        memcpy(&s->input,&seed->input,sizeof s->input);memcpy(s->input_ls,seed->input_ls,SPU_LS_SIZE);
        s->input.gpr[0]=spu_link(0x5980);s->input.gpr[1]=spu_ai(seed->input.gpr[1],816);
        s->input.gpr[3]=seed->input.gpr[90];s->input.gpr[4]=seed->input.gpr[100];s->input.gpr[5]=spu_il(cases[sample]);s->input.gpr[6]=seed->input.gpr[101];
        s->input.host_depth=1;s->input.pc=0xD0A8;s->input.tramp_fn=NULL;
        uint32_t context=s->input.gpr[3]._u32[0]&SPU_LS_MASK;
        // The seed was captured mid-call: clear only the entry's processed bit
        // if needed, so derived cases exercise computation rather than skip.
        spu_context probe=s->input;probe.ls=s->input_ls;
        if(spu_andi(spu_rotqbyi(spu_ls_read128(&probe,context),13),16)._u32[0]){
            for(unsigned b=0;b<16;b++){
                uint8_t old=s->input_ls[context+b];s->input_ls[context+b]&=~16u;
                if(!spu_andi(spu_rotqbyi(spu_ls_read128(&probe,context),13),16)._u32[0])break;
                s->input_ls[context+b]=old;
            }
        }
        spu_context*c=malloc(sizeof *c);assert(c);memcpy(c,&s->input,sizeof *c);c->ls=malloc(SPU_LS_SIZE);assert(c->ls);memcpy(c->ls,s->input_ls,SPU_LS_SIZE);
        uint64_t before_steps=steps;original(c,0xD0A8,0x5980);memcpy(&s->output,c,sizeof *c);memcpy(s->output_ls,c->ls,SPU_LS_SIZE);
        assert(steps-before_steps>5);printf("skin executed blocks=%llu\n",steps-before_steps);
        uint8_t*flat=malloc(SPU_LS_SIZE);u128 r[128];uint32_t dirty[512]={0},pc=0;assert(flat);memcpy(flat,s->input_ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,sizeof r);
        assert(bces_geometry_skin_flat(r,flat,0x5980,&pc,dirty));assert(!memcmp(r,s->output.gpr,sizeof r)&&!memcmp(flat,s->output_ls,SPU_LS_SIZE)&&pc==0x5980);
        memcpy(flat,s->input_ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,sizeof r);memset(dirty,0,sizeof dirty);
        assert(bces_geometry_skin_parallel(r,flat,0x5980,&pc,dirty));
        if(memcmp(r,s->output.gpr,sizeof r)||memcmp(flat,s->output_ls,SPU_LS_SIZE)){
          for(unsigned j=0;j<128;j++)if(memcmp(r+j,s->output.gpr+j,16))fprintf(stderr,"parallel reg %u %x != %x\n",j,r[j]._u32[0],s->output.gpr[j]._u32[0]);
          unsigned diff=0;for(unsigned j=0;j<SPU_LS_SIZE;j++)if(flat[j]!=s->output_ls[j]){if(diff++<8)fprintf(stderr,"parallel LS %x\n",j);}fprintf(stderr,"parallel diff %u\n",diff);return 3;
        }
        printf("PASS parallel-loop simulation full GPR/LS\n");
        memcpy(flat,s->input_ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,sizeof r);memset(dirty,0,sizeof dirty);
        uint64_t fpcr,fpsr,after_fpcr,after_fpsr;__asm__ volatile("mrs %0, fpcr":"=r"(fpcr));__asm__ volatile("mrs %0, fpsr":"=r"(fpsr));
        assert(bces_geometry_skin_arm64(r,flat,0x5980,&pc,dirty));
        __asm__ volatile("mrs %0, fpcr":"=r"(after_fpcr));__asm__ volatile("mrs %0, fpsr":"=r"(after_fpsr));assert(fpcr==after_fpcr&&fpsr==after_fpsr);
        assert(!memcmp(r,s->output.gpr,sizeof r)&&!memcmp(flat,s->output_ls,SPU_LS_SIZE)&&pc==0x5980);
        printf("PASS whole-function ARM64 RZ, full GPR/LS + FPCR/FPSR preservation\n");
        char path[1200];snprintf(path,sizeof path,"%s/skin-%02u.bin",argv[2],index++);f=fopen(path,"wb");assert(f&&fwrite(s,sizeof *s,1,f)==1);fclose(f);
        printf("PASS native full skinning N=%u, full GPR/LS; derived mid-call seed, not original entry capture\n",cases[sample]);
        if(sample==4){
            for(unsigned mode=1;mode<=3;mode++){
                memcpy(&s->input,c,sizeof *c);memcpy(s->input_ls,c->ls,SPU_LS_SIZE);s->input.gpr[0]=spu_link(0x59F0);s->input.gpr[3]=seed->input.gpr[90];s->input.gpr[4]=spu_il(mode);s->input.gpr[5]=spu_zero();s->input.host_depth=1;
                spu_context*d=malloc(sizeof *d);assert(d);memcpy(d,&s->input,sizeof *d);d->ls=malloc(SPU_LS_SIZE);assert(d->ls);memcpy(d->ls,s->input_ls,SPU_LS_SIZE);original(d,0xA798,0x59F0);
                memcpy(&s->output,d,sizeof *d);memcpy(s->output_ls,d->ls,SPU_LS_SIZE);s->version=2;
                memcpy(flat,s->input_ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,sizeof r);memset(dirty,0,sizeof dirty);
                assert(bces_geometry_cull_flat(r,flat,0x59F0,&pc,dirty));assert(!memcmp(r,s->output.gpr,sizeof r)&&!memcmp(flat,s->output_ls,SPU_LS_SIZE)&&pc==0x59F0);
                memcpy(flat,s->input_ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,sizeof r);memset(dirty,0,sizeof dirty);
                assert(bces_geometry_cull_arm64(r,flat,0x59F0,&pc,dirty));assert(!memcmp(r,s->output.gpr,sizeof r)&&!memcmp(flat,s->output_ls,SPU_LS_SIZE)&&pc==0x59F0);
                snprintf(path,sizeof path,"%s/cull-%u.bin",argv[2],mode);f=fopen(path,"wb");assert(f&&fwrite(s,sizeof *s,1,f)==1);fclose(f);printf("PASS native full culling mode=%u output=%u\n",mode,r[3]._u32[0]);free(d->ls);free(d);
            }
        }
        free(c->ls);free(c);free(flat);free(s);
    }
    for(unsigned i=0;i<65536;i++)free(first[i]);free(seed);return 0;
}
