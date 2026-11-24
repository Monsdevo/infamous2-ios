#ifndef DMA_TEST_HEADER
#define DMA_TEST_HEADER "diagnostic_spu_dma.h"
#endif
#include DMA_TEST_HEADER
#include "DmaPoisonControl.h"
#include <assert.h>
uint8_t memory[2<<20];uint8_t* vm_base=memory;uint8_t g_vm_page_bitmap[8192];
uint32_t ppu_hle_inject_base,g_barrier_sync_watch;int g_cri_video_dma;
ps3_ft_state g_ps3_ft={0};
void (*g_spu_put_hook)(uint32_t,uint32_t);
static uint64_t fingerprint=1469598103934665603ull;
static void digest(const void*p,size_t n){const unsigned char*b=p;while(n--){fingerprint^=*b++;fingerprint*=1099511628211ull;}}

uint32_t g_spu_image_ls_start,g_spu_image_span,g_spu_image_src_ea,g_ydkj_real_taskset_ea;
spu_context* volatile g_spu_oracle_trace_ctx;long g_spu_oracle_trace_left;volatile unsigned g_wws_batch_gets;
static unsigned reserved,locks,notifications;
LPVOID VirtualAlloc(LPVOID a,SIZE_T s,DWORD t,DWORD p){(void)a;(void)s;(void)t;(void)p;abort();}
SIZE_T VirtualQuery(LPCVOID a,PMEMORY_BASIC_INFORMATION b,SIZE_T n){(void)a;(void)b;(void)n;abort();}
unsigned long long ps3_ms_now(void){return 0;}
void spu_ch_wake(spu_context*c){(void)c;}
void spu_halt(spu_context*c){(void)c;abort();}
int spu_coh_is_reserved(uint32_t a){(void)a;return reserved;}
void spu_coh_notify_write_except(uint32_t a,const void*c){(void)a;(void)c;assert(locks);notifications++;}
uint64_t spu_lockline_mask_ea(uint32_t a){(void)a;return 1;}
uint64_t spu_lockline_mask_range(uint32_t a,uint32_t n){(void)a;(void)n;return 1;}
void spu_lockline_lock_mask(uint64_t a){(void)a;assert(!locks);locks++;}
void spu_lockline_unlock_mask(uint64_t a){(void)a;assert(locks==1);locks--;}
void spu_lockguard_check(spu_context*c,uint32_t a,const uint8_t*p,uint32_t n,const char*kind){(void)c;(void)a;(void)p;(void)n;(void)kind;}
unsigned* spu_ls_watch_list(int*n){*n=0;return NULL;}
int spu_ls_watch_ring_dma(spu_context*c,uint32_t l,uint32_t e,uint32_t n,const uint8_t*p){(void)c;(void)l;(void)e;(void)n;(void)p;return 0;}
void spu_overlay_note_get(spu_context*c,uint32_t e,const uint8_t*p,uint32_t n){(void)c;(void)e;(void)p;(void)n;}
unsigned spu_sn_defer_ticks(void){return 0;}
int bces_progress_trace_watched(uint64_t a,uint32_t n){(void)a;(void)n;return 0;}
void bces_progress_trace_dma(uint32_t a,int b,uint32_t c,uint32_t d,uint64_t e,uint32_t f,uint32_t g,const uint8_t*h,const uint8_t*i,uint32_t j,uint64_t k,uint64_t l){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;(void)j;(void)k;(void)l;}
void bces_frame_trace_dma(uint32_t a,int b,uint32_t c,uint32_t d,uint64_t e,uint32_t f,uint32_t g,const uint8_t*h,uint32_t i,uint64_t j,uint64_t k){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;(void)j;(void)k;}
void bces_edge_flow_dma(void*c,uint64_t e,uint32_t l,uint32_t n,uint32_t cmd){(void)c;(void)e;(void)l;(void)n;(void)cmd;}
int main(int argc,char**argv){
 bces_dma_poison_configure();bces_dma_poison_set(argc>1);
 memset(g_vm_page_bitmap,255,sizeof g_vm_page_bitmap);
 spu_context*c=calloc(1,sizeof *c);spu_context_init(c,100);c->spu_id=0;
 for(unsigned i=0;i<sizeof memory;i++)memory[i]=(uint8_t)(i*17+3);
 for(unsigned i=0;i<SPU_LS_SIZE;i++)c->ls[i]=(uint8_t)(i*7+11);
 c->ls[0x1000]=0xC7;c->ls[0x1001]=0x08;c->ls[0x1002]=0xC7;c->ls[0x1003]=0x08;
 mfc_engine m;mfc_engine_init(&m);
 const unsigned sizes[]={1,2,4,8,16,32,128,1024,16384};
 for(unsigned j=0;j<1000;j++)for(unsigned i=0;i<9;i++){
  reserved=j%4==0;
  unsigned n=sizes[i],cmd=(j&1)?0x40:0x20;cmd|=(j%3==1)?1:(j%3==2)?2:0;
  c->mfc_lsa=0x1000;c->mfc_eah=0;c->mfc_eal=0x10000+(j%16)*0x4000;c->mfc_size=n;c->mfc_tag=j%32;
  int rc=mfc_submit(&m,c,cmd);assert(rc==0);assert(m.tag_completed&(1u<<(j%32)));
  if(cmd&0x40)assert(!memcmp(c->ls+0x1000,memory+c->mfc_eal,n));else assert(!memcmp(memory+c->mfc_eal,c->ls+0x1000,n));
  digest(c->ls+0x1000,n);digest(memory+c->mfc_eal,n);digest(&m.tag_completed,sizeof m.tag_completed);
 }
 digest(&notifications,sizeof notifications);assert(!locks);
 uint64_t counts[4];bces_dma_poison_totals(counts);fprintf(stderr,"scanned=%llu skipped=%llu bytes-skipped=%llu\n",(unsigned long long)counts[0],(unsigned long long)counts[1],(unsigned long long)counts[3]);
 printf("fingerprint=%llu\n",(unsigned long long)fingerprint);free(c);return 0;
}
