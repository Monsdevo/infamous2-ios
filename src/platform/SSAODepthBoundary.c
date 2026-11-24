/* Applies only inside the GPU route's synchronous original-depth call.
 * The guard reads the just-GETLLAR reservation snapshot, not a racy guest load.
 * A concurrent pass advance invalidates PUTLLC and forces another GETLLAR. */
#include "SSAODepthBoundary.h"
#include "spu_context.h"
#if BCES_HALF_DEPTH_PROBE
#include "HalfDepthProbe.h"
#endif
#include <stdio.h>
#include <string.h>
static SPU_THREAD_LOCAL BCESSSAODepthScope scope;
static int enabled=1;
static uint64_t calls,boundaries;
static char control_directory[1024],last_token[80];
void bces_ssao_depth_cleanup_set_enabled(int value){__atomic_store_n(&enabled,!!value,__ATOMIC_RELAXED);}
int bces_ssao_depth_cleanup_enabled(void){return __atomic_load_n(&enabled,__ATOMIC_RELAXED);}
BCESSSAODepthScope bces_ssao_depth_enter(void* context,uint32_t state_ea){
 BCESSSAODepthScope previous=scope;scope=(BCESSSAODepthScope){context,state_ea};
 __atomic_add_fetch(&calls,1,__ATOMIC_RELAXED);return previous;
}
void bces_ssao_depth_leave(BCESSSAODepthScope previous){scope=previous;}
void bces_ssao_depth_reset_scope(void* context){
 // A halted/longjmp-unwound depth call must not constrain a later fallback.
 if(scope.context==context)scope=(BCESSSAODepthScope){0,0};
}
unsigned bces_ssao_depth_trace_active(const void* context){
 return scope.context==context;
}
int bces_ssao_depth_claim_guard(void* opaque){
 if(!bces_ssao_depth_cleanup_enabled() || scope.context!=opaque)return 0;
 const spu_context* c=opaque;const uint8_t* p=c->ls+0x6420;
 uint32_t state=(uint32_t)p[0]<<24|(uint32_t)p[1]<<16|(uint32_t)p[2]<<8|p[3];
 if(state!=scope.state_ea)return 0;
 p=c->ls+0x6480+(state&0x78u);
 uint32_t pass=(uint32_t)p[0]<<8|p[1];
 if(pass==0 || pass==0xffffu)return 0; // Original depth and terminal semantics.
 #if BCES_HALF_DEPTH_PROBE
 bces_half_depth_reference(state);
 #endif
 __atomic_add_fetch(&boundaries,1,__ATOMIC_RELAXED);return 1;
}
uint64_t bces_ssao_depth_calls(void){return __atomic_load_n(&calls,__ATOMIC_RELAXED);}
uint64_t bces_ssao_depth_boundaries(void){return __atomic_load_n(&boundaries,__ATOMIC_RELAXED);}
void bces_ssao_depth_control_configure(const char* directory){
 if(directory)snprintf(control_directory,sizeof control_directory,"%s",directory);
}
void bces_ssao_depth_control_poll(void){
 // Opt-in UI-thread control. Switching affects future atomic claims only;
 // already-claimed work finishes normally. It never cancels a completion.
 if(!control_directory[0])return;
 char path[1200],mode[8]={0},token[80]={0};
 snprintf(path,sizeof path,"%s/ssao-depth-control.txt",control_directory);
 FILE* f=fopen(path,"r");if(!f)return;
 int count=fscanf(f,"%7s %79s",mode,token);fclose(f);
 if(count!=2 || (strcmp(mode,"on") && strcmp(mode,"off")) || !strcmp(token,last_token))return;
 for(char* p=token;*p;p++)if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_'))return;
 strcpy(last_token,token);bces_ssao_depth_cleanup_set_enabled(!strcmp(mode,"on"));
}
