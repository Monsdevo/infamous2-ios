#include "EdgeGeometry.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "EdgeGeometrySnapshot.h"
static _Atomic(EdgeSnapshot*) failure_snapshot;
void* bces_edge_snapshot_input(const void* opaque,unsigned block){
    const spu_context*c=opaque;EdgeSnapshot*s=calloc(1,sizeof *s);if(!s)return NULL;
    s->magic=0x45444745;s->context_size=sizeof *c;s->ls_size=SPU_LS_SIZE;s->block=block;
    __asm__ volatile("mrs %0, fpcr":"=r"(s->fpcr));
    memcpy(&s->input,c,sizeof *c);memcpy(s->input_ls,c->ls,SPU_LS_SIZE);return s;
}
void bces_edge_snapshot_finish(void* opaque,const void* reference,const void* actual,const void* reference_ls,int equal){
    EdgeSnapshot*s=opaque;if(!s)return;if(equal){free(s);return;}
    memcpy(&s->reference,reference,sizeof s->reference);memcpy(&s->actual,actual,sizeof s->actual);
    memcpy(s->reference_ls,reference_ls,SPU_LS_SIZE);memcpy(s->actual_ls,((const spu_context*)actual)->ls,SPU_LS_SIZE);
    EdgeSnapshot*expected=NULL;
    if(!atomic_compare_exchange_strong_explicit(&failure_snapshot,&expected,s,memory_order_release,memory_order_relaxed))free(s);
}
void bces_edge_flush_capture(const char* directory){
    EdgeSnapshot*s=atomic_exchange_explicit(&failure_snapshot,NULL,memory_order_acquire);if(!s)return;
    char path[1200];snprintf(path,sizeof path,"%s/edge-failure.bin",directory);
    FILE*f=fopen(path,"wb");if(f){fwrite(s,sizeof *s,1,f);fclose(f);}free(s);
}
static char control_directory[1024],last_token[80];
static _Atomic int enabled;
static _Atomic uint64_t calls[3];
static _Atomic unsigned validation_slots[3];
static _Atomic uint64_t validations,mismatches;
void bces_edge_set_enabled(int value) { atomic_store_explicit(&enabled,!!value,memory_order_relaxed); }
int bces_edge_enabled(void) { return atomic_load_explicit(&enabled,memory_order_relaxed); }
uint64_t bces_edge_calls(unsigned block) { return block<3 ? atomic_load_explicit(&calls[block],memory_order_relaxed) : 0; }
void bces_edge_note_call(unsigned block) { if(block<3) atomic_fetch_add_explicit(&calls[block],1,memory_order_relaxed); }
int bces_edge_validate_next(unsigned block) {
    if(block>=3)return 0;
    unsigned n=atomic_load_explicit(&validation_slots[block],memory_order_relaxed);
    while(n<8){if(atomic_compare_exchange_weak_explicit(&validation_slots[block],&n,n+1,memory_order_relaxed,memory_order_relaxed))return 1;}
    return 0;
}
void bces_edge_validation_result(int equal) {
    atomic_fetch_add_explicit(&validations,1,memory_order_relaxed);
    if(!equal){atomic_fetch_add_explicit(&mismatches,1,memory_order_relaxed);bces_edge_set_enabled(0);}
}
uint64_t bces_edge_validations(void){return atomic_load_explicit(&validations,memory_order_relaxed);}
uint64_t bces_edge_mismatches(void){return atomic_load_explicit(&mismatches,memory_order_relaxed);}
void bces_edge_control_configure(const char* directory){if(directory)snprintf(control_directory,sizeof control_directory,"%s",directory);}
void bces_edge_control_poll(void){
    if(!control_directory[0])return;
    char path[1200],mode[8]={0},token[80]={0};
    snprintf(path,sizeof path,"%s/edge-control.txt",control_directory);
    FILE*f=fopen(path,"r");if(!f)return;
    int n=fscanf(f,"%7s %79s",mode,token);fclose(f);
    if(n!=2 || (strcmp(mode,"on")&&strcmp(mode,"off")) || !strcmp(token,last_token))return;
    for(char*p=token;*p;p++)if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_'))return;
    strcpy(last_token,token);
    // A discrepancy latches the experiment off for the rest of this process.
    bces_edge_set_enabled(!strcmp(mode,"on") && !bces_edge_mismatches());
}
