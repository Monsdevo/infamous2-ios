#import <Foundation/Foundation.h>
#include "GeometryMetalBatches.h"
#include "SkinningSnapshot.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <thread>
#include <memory>
#include <vector>
#include <atomic>
struct Replay {uint32_t pc;u128 r[128],expected[128];uint8_t ls[SPU_LS_SIZE],output[SPU_LS_SIZE];};
std::unique_ptr<Replay> replay[2];
struct Check {
 BCESBatchPlan plan;uint8_t expected[SPU_LS_SIZE];BCESBatchWrite outputs[BCES_BATCH_MAX_ITERATIONS*BCES_BATCH_MAX_WRITES];
 unsigned batches=0,mask=0,declined=0;bool alias_tested=false;
};
static int batch(BCESGeometryExecution*e,uint32_t*pc,u128*r,uint8_t*ls){
 auto&c=*(Check*)e->opaque;uint32_t entry=*pc;unsigned n=bces_batch_count(entry,r);
 if(!bces_batch_plan(entry,r,ls,&c.plan)){c.declined++;printf("DECLINED independent plan PC=%x N=%u reason=%u address=%x read=%u write=%u r5=%x r24=%x r22=%x r31=%x,%x,%x,%x\n",entry,n,c.plan.rejection,c.plan.address,c.plan.read_stamp,c.plan.write_stamp,r[5]._u32[0],r[24]._u32[0],r[22]._u32[0],r[31]._u32[0],r[31]._u32[1],r[31]._u32[2],r[31]._u32[3]);return 0;}
 if(entry==0xDCE0&&n>=32&&!c.alias_tested){u128 alias[128];memcpy(alias,r,2048);alias[33]=alias[42];for(unsigned lane=0;lane<4;lane++)alias[33]._u32[lane]+=192;
  BCESBatchPlan*p=new BCESBatchPlan;assert(!bces_batch_plan(entry,alias,ls,p));delete p;c.alias_tested=true;puts("PASS read-after-write alias rejected before GPU");}
 unsigned replay_kind=entry==0xA650;std::unique_ptr<Replay> candidate; if(!replay[replay_kind]){candidate=std::make_unique<Replay>();candidate->pc=entry;memcpy(candidate->r,r,2048);memcpy(candidate->ls,ls,SPU_LS_SIZE);}
 memcpy(c.expected,ls,SPU_LS_SIZE);u128 expected[128];memcpy(expected,r,2048);uint32_t dirty[512]={0},expected_pc;
 BCESGeometryExecution reference={};reference.dirty=dirty;
 auto begin=std::chrono::steady_clock::now();assert(bces_batch_cpu(entry,expected,c.expected,&expected_pc,&reference));double cpu=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 u128 actual[128];BCESBatchCost cost={};begin=std::chrono::steady_clock::now();int okay=bces_batch_metal_run(&c.plan,r,ls,c.outputs,actual,&cost);
 if(okay!=1){fprintf(stderr,"GPU batch failed PC=%x N=%u result=%d\n",entry,n,okay);exit(4);}
 double total=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
 for(unsigned i=0;i<c.plan.iterations*c.plan.writes_per_iteration;i++)bces_geometry_write(ls,c.outputs[i].address,c.outputs[i].value,e->dirty,e);
 uint32_t actual_pc=bces_batch_finish(entry,actual,ls);
 if(actual_pc!=expected_pc||memcmp(expected,actual,2048)||memcmp(c.expected,ls,SPU_LS_SIZE)){
  for(unsigned i=0;i<128;i++)if(memcmp(expected+i,actual+i,16))fprintf(stderr,"GPR %u expected=%08x actual=%08x\n",i,expected[i]._u32[0],actual[i]._u32[0]);
  unsigned count=0;for(unsigned i=0;i<SPU_LS_SIZE;i++)if(c.expected[i]!=ls[i]){if(count++<8)fprintf(stderr,"LS %x expected=%02x actual=%02x\n",i,c.expected[i],ls[i]);}fprintf(stderr,"PC %x/%x LS-diff=%u\n",expected_pc,actual_pc,count);exit(5);
 }
 if(candidate){memcpy(candidate->expected,actual,2048);memcpy(candidate->output,ls,SPU_LS_SIZE);replay[replay_kind]=std::move(candidate);}
 memcpy(r,actual,2048);*pc=actual_pc;c.batches++;c.mask|=1u<<(entry==0xA650?6:entry==0x7030?5:entry==0xD800?0:entry==0xD5B0?1:entry==0xDA28?2:entry==0xDCE0?3:4);
 printf("PASS GPU PC=%x N=%u sparse_in=%llu out=%llu CPU_ref_ms=%.3f GPU_ms=%.3f backend_ms=%.3f (Mac host check; not iPhone FPS)\n",entry,n,cost.input_bytes,cost.output_bytes,cpu,cost.gpu_ns/1e6,total);return 1;
}
int main(int argc,char**argv){@autoreleasepool{
 bool allow_unsupported=argc>1&&!strcmp(argv[1],"--allow-unsupported");int first=allow_unsupported?2:1;assert(argc>first);bces_batch_metal_prepare();for(unsigned i=0;bces_batch_metal_state()==1&&i<600;i++)std::this_thread::sleep_for(std::chrono::milliseconds(100));
 if(bces_batch_metal_state()!=2){fprintf(stderr,"Metal unavailable state=%u stage=%u\n",bces_batch_metal_state(),bces_batch_metal_compile_stage());return 2;}
 auto c=std::make_unique<Check>();uint8_t*ls=(uint8_t*)malloc(SPU_LS_SIZE),*undo=(uint8_t*)malloc(SPU_LS_SIZE);assert(ls&&undo);
 unsigned unsupported=0,checked=0;for(int a=first;a<argc;a++){
  FILE*f=fopen(argv[a],"rb");assert(f);auto s=std::make_unique<SkinningSnapshot>();assert(fread(s.get(),sizeof *s,1,f)==1);fclose(f);assert(s->magic==0x534b494e&&(s->version==1||s->version==2)&&s->context_size==sizeof(spu_context));unsigned kind=s->version==2;
  memcpy(ls,s->input_ls,SPU_LS_SIZE);u128 r[128];memcpy(r,s->input.gpr,2048);uint32_t dirty[512]={0},pc=0;BCESGeometryExecution e={};e.backup=undo;e.dirty=dirty;e.kind=kind;e.batch=batch;e.opaque=c.get();
  bool supported=(kind?bces_geometry_cull_execute:bces_geometry_skin_execute)(r,ls,kind?0x59F0:0x5980,&pc,dirty,&e);
  if(!supported){bces_geometry_rollback(ls,&e);assert(!memcmp(ls,s->input_ls,SPU_LS_SIZE));if(!allow_unsupported){fprintf(stderr,"Unsupported full graph %s\n",argv[a]);return 6;}unsupported++;printf("SKIP unsupported graph with verified rollback %s\n",argv[a]);continue;}checked++;
  assert(pc==s->output.pc&&!memcmp(r,s->output.gpr,2048)&&!memcmp(ls,s->output_ls,SPU_LS_SIZE));
  bces_geometry_rollback(ls,&e);assert(!memcmp(ls,s->input_ls,SPU_LS_SIZE));printf("PASS whole graph GPU integration and journal rollback %s\n",argv[a]);
 }
 printf("PASS batches=%u PC-mask=%x declined=%u\n",c->batches,c->mask,c->declined);if(!allow_unsupported)assert(c->batches&&c->mask&(1u<<6));printf("Checked=%u unsupported=%u native-math=%d\n",checked,unsupported,bces_batch_native_math_enabled());
 std::atomic<unsigned> success{0},busy{0};std::vector<std::thread> workers;for(unsigned worker=0;worker<4;worker++)workers.emplace_back([&,worker]{for(unsigned k=0;k<8;k++){auto&q=replay[(worker+k)%2];if(!q)continue;auto plan=std::make_unique<BCESBatchPlan>();assert(bces_batch_plan(q->pc,q->r,q->ls,plan.get()));auto output=std::make_unique<BCESBatchWrite[]>(BCES_BATCH_MAX_ITERATIONS*BCES_BATCH_MAX_WRITES);u128 result[128];BCESBatchCost cost={};int okay=bces_batch_metal_run(plan.get(),q->r,q->ls,output.get(),result,&cost);if(okay==-2){busy++;std::this_thread::yield();continue;}assert(okay==1);auto actual=std::make_unique<uint8_t[]>(SPU_LS_SIZE);memcpy(actual.get(),q->ls,SPU_LS_SIZE);uint32_t dirty[512]={0};BCESGeometryExecution e={};e.dirty=dirty;for(unsigned i=0;i<plan->iterations*plan->writes_per_iteration;i++)bces_geometry_write(actual.get(),output[i].address,output[i].value,dirty,&e);bces_batch_finish(q->pc,result,actual.get());assert(!memcmp(result,q->expected,2048)&&!memcmp(actual.get(),q->output,SPU_LS_SIZE));success++;}});for(auto&t:workers)t.join();if(c->batches)assert(success);printf("PASS concurrent worker isolation GPU=%u nonblocking-busy=%u\n",success.load(),busy.load());
 free(ls);free(undo);return 0;
}}
