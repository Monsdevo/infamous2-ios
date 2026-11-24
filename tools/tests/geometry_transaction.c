#include "SkinningSnapshot.h"
#include "GeometryExecution.h"
#include <assert.h>
#include <stdio.h>
int main(int argc,char**argv){
 assert(argc>1);uint8_t*ls=malloc(SPU_LS_SIZE),*undo=malloc(SPU_LS_SIZE);assert(ls&&undo);
 for(int a=1;a<argc;a++){
  FILE*f=fopen(argv[a],"rb");assert(f);SkinningSnapshot*s=malloc(sizeof *s);assert(s&&fread(s,sizeof *s,1,f)==1);fclose(f);
  assert(s->magic==0x534b494e);unsigned kind=s->version==2;uint32_t ret=kind?0x59F0:0x5980,pc=0,dirty[512]={0};u128 r[128];
  memcpy(ls,s->input_ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,2048);memset(undo,0xa5,SPU_LS_SIZE);
  BCESGeometryExecution e={.backup=undo,.dirty=dirty,.kind=kind};
  int okay=(kind?bces_geometry_cull_execute:bces_geometry_skin_execute)(r,ls,ret,&pc,dirty,&e);
  assert(okay&&pc==ret&&!memcmp(r,s->output.gpr,2048)&&!memcmp(ls,s->output_ls,SPU_LS_SIZE));
  unsigned quads=0;for(unsigned w=0;w<512;w++)quads+=__builtin_popcount(dirty[w]);
  bces_geometry_rollback(ls,&e);assert(!memcmp(ls,s->input_ls,SPU_LS_SIZE));
  printf("PASS %s journal execute + exact rollback; backed up %u bytes of 262144\n",argv[a],quads*16);
  free(s);
 }
 // Deliberate unsupported/asserting descriptor: prologue writes must undo.
 FILE*f=fopen(argv[1],"rb");assert(f);SkinningSnapshot*s=malloc(sizeof *s);assert(s&&fread(s,sizeof *s,1,f)==1);fclose(f);
 memcpy(ls,s->input_ls,SPU_LS_SIZE);u128 r[128];memcpy(r,s->input.gpr,2048);
 uint32_t base=r[3]._u32[0]&0x3fff0;
 // Zero flag byte is a forbidden signed header for nonempty skinning.
 ls[base+2]=0; // Search a single byte that selects the error path, below.
 uint8_t*input=malloc(SPU_LS_SIZE);assert(input);int found=0;
 for(unsigned byte=0;byte<16&&!found;byte++)for(unsigned value=0;value<256&&!found;value++){
  memcpy(ls,s->input_ls,SPU_LS_SIZE);ls[base+byte]=(uint8_t)value;memcpy(input,ls,SPU_LS_SIZE);memcpy(r,s->input.gpr,2048);
  uint32_t dirty[512]={0},pc;BCESGeometryExecution e={.backup=undo,.dirty=dirty};
  if(!bces_geometry_skin_execute(r,ls,0x5980,&pc,dirty,&e)){bces_geometry_rollback(ls,&e);assert(!memcmp(ls,input,SPU_LS_SIZE));found=1;}
 }
 assert(found);puts("PASS unsupported input restores all journaled writes");free(input);free(s);free(ls);free(undo);return 0;
}
