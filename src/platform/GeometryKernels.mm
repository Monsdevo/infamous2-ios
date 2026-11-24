#import <Foundation/Foundation.h>
#include "GeometryKernels.h"
#include "GeometryMetalBatches.h"
#include <atomic>
#include <memory>
#include <chrono>
namespace {
using Clock=std::chrono::steady_clock;
uint64_t ns(Clock::time_point begin){return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin).count();}
struct Counters {
 std::atomic<unsigned> route{0},blocked{0},tickets[3]{};
 std::atomic<uint64_t> calls[3]{},entries[3]{},total[3]{},fallbacks{0},validations{0},mismatches{0},failures{0},trial{0},gpu{0},reference{0},unsupported{0};
 std::atomic<uint64_t> sampled{0},copy{0},execute{0},commit{0};
 std::atomic<uint64_t> candidates{0},gpu_batches{0},calibrations{0},small{0},busy{0},dependent{0},cost_rejected{0},cpu_only{0};
 std::atomic<uint64_t> input{0},submit{0},wait{0},output{0},input_bytes{0},output_bytes{0};
} counters[2];
struct Gate {std::atomic<unsigned> state{0},samples{0};std::atomic<uint64_t> cpu{0},gpu{0};};
// 0 unseen/collecting, 1 one calibration in progress, 2 admitted, 3 cost
// rejected, 4 unsupported dependency. Each PC and size bucket is independent.
Gate gates[2][21];
std::atomic<bool> validate_all{true};
std::atomic<unsigned> routes{0},revision{0};
struct Scratch {
 alignas(16) u128 r[128];alignas(16) uint8_t undo[SPU_LS_SIZE],validation_ls[SPU_LS_SIZE];uint32_t dirty[512];uint32_t pc;
};
struct BatchScratch {
 BCESBatchPlan plan;uint8_t expected_ls[SPU_LS_SIZE],actual_ls[SPU_LS_SIZE],undo[SPU_LS_SIZE];
 BCESBatchWrite outputs[BCES_BATCH_MAX_ITERATIONS*BCES_BATCH_MAX_WRITES];
};
thread_local std::unique_ptr<Scratch> scratch;
thread_local std::unique_ptr<BatchScratch> batch_scratch;
struct Job {Counters*n;unsigned kind;bool used_gpu=false;};
struct CallTime {
 Counters&n;unsigned route;Clock::time_point start=Clock::now();
 ~CallTime(){n.total[route]+=ns(start);}
};
void reference(spu_context*c,Counters&n,BCESGeometryReference fn,uint32_t ret){auto start=Clock::now();fn(c);spu_drain_call(c,ret);n.reference+=ns(start);n.calls[0]++;}
unsigned pc_index(uint32_t pc){switch(pc){case 0xD800:return 0;case 0xD5B0:return 1;case 0xDA28:return 2;case 0xDCE0:return 3;case 0xDF20:return 4;case 0x7030:return 5;case 0xA650:return 6;default:return 7;}}
void apply(const BCESBatchPlan&p,const BCESBatchWrite*out,uint8_t*ls,BCESGeometryExecution*e){for(unsigned i=0;i<p.iterations*p.writes_per_iteration;i++)bces_geometry_write(ls,out[i].address,out[i].value,e->dirty,e);}
void copy_changes(const uint8_t*source,uint8_t*ls,const uint32_t*dirty,BCESGeometryExecution*e){
 for(unsigned word=0;word<512;word++){uint32_t bits=dirty[word];while(bits){unsigned bit=__builtin_ctz(bits),a=(word*32+bit)*16;u128 v;for(unsigned lane=0;lane<4;lane++){uint32_t x;memcpy(&x,source+a+4*lane,4);v._u32[lane]=__builtin_bswap32(x);}bces_geometry_write(ls,a,v,e->dirty,e);bits&=bits-1;}}
}
int batch(BCESGeometryExecution*e,uint32_t*pc,u128*r,uint8_t*ls){
 auto&job=*(Job*)e->opaque;auto&n=*job.n;if(n.blocked.load()&4u)return 0;unsigned index=pc_index(*pc),count=bces_batch_count(*pc,r);
 if(index>=7||count<32){n.small++;return 0;}n.candidates++;
 unsigned bucket=count>=256?2:count>=128?1:0;Gate&gate=gates[job.kind][index*3+bucket];unsigned state=gate.state.load();
 if(state==3){n.cost_rejected++;return 0;}if(state==4){n.dependent++;return 0;}if(state==1){n.busy++;return 0;}
 bool calibration=state==0;
 if(calibration){unsigned expected=0;if(!gate.state.compare_exchange_strong(expected,1)){n.busy++;return 0;}}
 if(!batch_scratch)batch_scratch.reset(new(std::nothrow) BatchScratch);
 if(!batch_scratch){if(calibration)gate.state=0;n.busy++;return 0;}auto&s=*batch_scratch;
 auto plan_start=Clock::now();if(!bces_batch_plan(*pc,r,ls,&s.plan)){if(calibration)gate.state=4;n.dependent++;return 0;}uint64_t plan_ns=ns(plan_start);
 u128 expected_r[128];uint32_t expected_pc=0,expected_dirty[512]={0};uint64_t cpu_ns=0;
 if(calibration){
  memcpy(s.expected_ls,ls,SPU_LS_SIZE);memcpy(expected_r,r,2048);BCESGeometryExecution ref={};ref.dirty=expected_dirty;
  auto begin=Clock::now();bool okay=bces_batch_cpu(*pc,expected_r,s.expected_ls,&expected_pc,&ref);cpu_ns=ns(begin);
  if(!okay){gate.state=4;n.dependent++;return 0;}
 }
 BCESBatchCost cost={};u128 actual_r[128];auto begin=Clock::now();int okay=bces_batch_metal_run(&s.plan,r,ls,s.outputs,actual_r,&cost);uint64_t backend_ns=ns(begin);
 if(okay!=1){if(calibration)gate.state=0;if(okay==-1){n.failures++;n.blocked.fetch_or(4u);}else n.busy++;return 0;}
 n.gpu+=cost.gpu_ns;n.input+=cost.input_ns;n.submit+=cost.submit_ns;n.wait+=cost.wait_ns;n.output+=cost.output_ns;n.input_bytes+=cost.input_bytes;n.output_bytes+=cost.output_bytes;
 if(calibration){
  memcpy(s.actual_ls,ls,SPU_LS_SIZE);uint32_t dirty[512]={0};BCESGeometryExecution check={};check.backup=s.undo;check.dirty=dirty;
  begin=Clock::now();apply(s.plan,s.outputs,s.actual_ls,&check);uint32_t actual_pc=bces_batch_finish(*pc,actual_r,s.actual_ls);uint64_t commit_ns=ns(begin);
  bool equal=actual_pc==expected_pc&&!memcmp(actual_r,expected_r,2048)&&!memcmp(s.actual_ls,s.expected_ls,SPU_LS_SIZE);
  n.calibrations++;
  if(!equal){n.mismatches++;n.blocked.fetch_or(4u);gate.state=4;NSLog(@"Geometry batch mismatch PC=%x N=%u; GPU outputs discarded",*pc,count);return 0;}
  gate.cpu+=cpu_ns;gate.gpu+=plan_ns+backend_ns+commit_ns;unsigned samples=gate.samples.fetch_add(1)+1;
  if(samples>=3)gate.state=gate.gpu.load()*100<gate.cpu.load()*85?2:3;else gate.state=0;
  // Warmup uses the verified CPU result. GPU calibration does not count as
  // accepted GPU coverage in a performance measurement.
  copy_changes(s.expected_ls,ls,expected_dirty,e);memcpy(r,expected_r,2048);*pc=expected_pc;return 1;
 }
 apply(s.plan,s.outputs,ls,e);*pc=bces_batch_finish(*pc,actual_r,ls);memcpy(r,actual_r,2048);job.used_gpu=true;n.gpu_batches++;return 1;
}
}
extern "C" unsigned bces_geometry_metal_state(void){return bces_batch_metal_state();}
extern "C" void bces_geometry_set_routes(unsigned skin,unsigned cull){if(skin>=3||cull>=3)return;unsigned value=skin|(cull<<2);if(routes.exchange(value)!=value)revision++;if(skin==2||cull==2)bces_batch_metal_prepare();}
extern "C" void bces_geometry_set_route(unsigned kind,unsigned route){
 if(kind>=2||route>=3)return;unsigned old=routes.load(),value;
 do{value=(old&~(3u<<(kind*2)))|(route<<(kind*2));}while(!routes.compare_exchange_weak(old,value));if(value!=old)revision++;if(route==2)bces_batch_metal_prepare();
}
extern "C" unsigned bces_geometry_route(unsigned kind){return kind<2?(routes.load()>>(kind*2))&3u:0;}
extern "C" void bces_geometry_set_validation(int value){if(validate_all.exchange(value!=0)!=(value!=0))revision++;}
extern "C" int bces_geometry_validation_enabled(void){return validate_all.load();}
extern "C" unsigned bces_geometry_revision(void){return revision.load();}
extern "C" BCESGeometryGateStats bces_geometry_gate_stats(unsigned kind,unsigned index){
 BCESGeometryGateStats s={};if(kind>=2||index>=21)return s;const unsigned pcs[7]={0xD800,0xD5B0,0xDA28,0xDCE0,0xDF20,0x7030,0xA650};auto&g=gates[kind][index];s.pc=pcs[index/3];s.bucket=index%3;s.state=g.state;s.samples=g.samples;s.cpu_ns=g.cpu;s.gpu_ns=g.gpu;return s;
}
extern "C" BCESGeometryStats bces_geometry_stats(unsigned kind){
 BCESGeometryStats s={};if(kind>=2)return s;auto&n=counters[kind];s.requested_route=bces_geometry_route(kind);s.blocked_mask=n.blocked;
 for(unsigned i=0;i<3;i++){s.calls[i]=n.calls[i];s.entries[i]=n.entries[i];s.total_ns[i]=n.total[i];}
 s.fallbacks=n.fallbacks;s.validations=n.validations;s.mismatches=n.mismatches;s.failures=n.failures;s.trial_ns=n.trial;s.gpu_ns=n.gpu;s.reference_ns=n.reference;
 s.sampled_calls=n.sampled;s.copy_ns=n.copy;s.execute_ns=n.execute;s.commit_ns=n.commit;s.batch_candidates=n.candidates;s.gpu_batches=n.gpu_batches;s.calibration_batches=n.calibrations;s.cpu_small_batches=n.small;s.cpu_busy_batches=n.busy;s.cpu_dependency_batches=n.dependent;s.cpu_cost_rejected_batches=n.cost_rejected;s.cpu_only_calls=n.cpu_only;s.unsupported_calls=n.unsupported;
 s.input_ns=n.input;s.submit_ns=n.submit;s.wait_ns=n.wait;s.output_ns=n.output;s.input_bytes=n.input_bytes;s.output_bytes=n.output_bytes;
 for(unsigned i=0;i<21;i++){unsigned state=gates[kind][i].state.load();if(state==2)s.admitted_mask|=1u<<i;if(state==3||state==4)s.rejected_mask|=1u<<i;if(state==1)s.calibrating++;}
 return s;
}
extern "C" void bces_geometry_execute(spu_context*c,unsigned kind,BCESGeometryReference fn,uint32_t ret){
 if(kind>=2){fn(c);spu_drain_call(c,ret);return;}auto&n=counters[kind];unsigned route=bces_geometry_route(kind);CallTime timer{n,route};uint64_t sequence=n.entries[route].fetch_add(1);
 if(!route){reference(c,n,fn,ret);return;}
 if(route==2&&bces_batch_metal_state()!=2){n.fallbacks++;reference(c,n,fn,ret);return;}
 uint64_t fpcr;__asm__ volatile("mrs %0, fpcr":"=r"(fpcr));
 if((n.blocked.load()&(1u<<route))||c->ls!=c->ls_store||c->stop_request||!c->host_depth||g_spu_ls_dbg||g_spu_ls_watch_n>0||(fpcr&(3ull<<22))||(c->int_enable&&(spu_ev_get(c)&c->event_mask))){n.fallbacks++;reference(c,n,fn,ret);return;}
 if(!scratch)scratch.reset(new(std::nothrow) Scratch);if(!scratch){n.fallbacks++;reference(c,n,fn,ret);return;}auto&s=*scratch;
 bool validate=validate_all.load()||n.tickets[route].fetch_add(1)<8,detail=(sequence&63)==0;
 auto begin=Clock::now(),trial_start=begin;memcpy(s.r,c->gpr,2048);memset(s.dirty,0,sizeof s.dirty);
 uint8_t*ls=c->ls;if(validate){memcpy(s.validation_ls,c->ls,SPU_LS_SIZE);ls=s.validation_ls;}
 if(detail){n.sampled++;n.copy+=ns(begin);}
 Job job{&n,kind};BCESGeometryExecution execution={};execution.backup=validate?nullptr:s.undo;execution.dirty=s.dirty;execution.kind=kind;execution.batch=route==2?batch:nullptr;execution.opaque=&job;
 begin=Clock::now();bool okay=(kind?bces_geometry_cull_execute:bces_geometry_skin_execute)(s.r,ls,ret,&s.pc,s.dirty,&execution);if(detail)n.execute+=ns(begin);
 if(!okay||s.pc!=ret||c->stop_request||(c->int_enable&&(spu_ev_get(c)&c->event_mask))){
  if(!validate)bces_geometry_rollback(c->ls,&execution);n.trial+=ns(trial_start);n.fallbacks++;if(!okay)n.unsupported++;reference(c,n,fn,ret);return;
 }
#ifdef BCES_GEOMETRY_TEST_FAULT
 extern int bces_geometry_test_fault;if(bces_geometry_test_fault)s.r[7]._u32[0]^=1;
#endif
 if(validate){
  n.trial+=ns(trial_start);reference(c,n,fn,ret);n.validations++;
  bool equal=!memcmp(s.r,c->gpr,2048)&&!memcmp(ls,c->ls,SPU_LS_SIZE)&&c->pc==s.pc&&!c->tramp_fn;
  if(!equal){n.mismatches++;n.blocked.fetch_or(1u<<route);NSLog(@"Geometry mismatch kind=%u route=%u; reference retained",kind,route);}else n.calls[route]++;
  return;
 }
 begin=Clock::now();memcpy(c->gpr,s.r,2048);c->pc=s.pc;c->tramp_fn=nullptr;if(detail)n.commit+=ns(begin);
 n.trial+=ns(trial_start);n.calls[route]++;if(route==2&&!job.used_gpu)n.cpu_only++;
}
