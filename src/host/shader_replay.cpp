// Replay exactly one captured shader using the pinned host translation libs.
// 64 MiB per-allocation guard is a host diagnostic bound, not a game fix.
#include "rsx_shader_msl.h"
#include "ShaderDiagnostics.h"
#include <cstdio>
#include <cstdlib>
#include <new>
#include <vector>

void* operator new(size_t n) {
    if(n>64u*1024u*1024u) {
        std::fprintf(stderr,"host_allocation_guard requested_bytes=%zu\n",n);
        throw std::bad_alloc();
    }
    if(!n)n=1;
    for(;;) {
        if(void* p=std::malloc(n))return p;
        if(auto handler=std::get_new_handler())handler();else throw std::bad_alloc();
    }
}
void* operator new[](size_t n) { return ::operator new(n); }
int main(int argc,char** argv) {
    if(argc!=4){std::fprintf(stderr,"usage: shader-replay INPUT STAGE DIAGNOSTIC_DIR\n");return 2;}
    FILE* f=std::fopen(argv[1],"rb");if(!f)return 3;
    std::fseek(f,0,SEEK_END);long n=std::ftell(f);std::rewind(f);
    if(n<0 || n>512*1024){std::fclose(f);return 4;}
    std::vector<char> input(size_t(n)+1,0),out(512*1024),log(8192);
    if(std::fread(input.data(),1,size_t(n),f)!=size_t(n)){std::fclose(f);return 5;}std::fclose(f);
    bces_shader_diagnostics_configure(argv[3]);
    try {
        int rc=rsx_hlsl_to_msl(input.data(),std::atoi(argv[2]),out.data(),unsigned(out.size()),log.data(),unsigned(log.size()));
        std::printf("translation_result=%d log=%s\n",rc,log.data());
        if(!rc){std::printf("%s\n",out.data());return 0;}return 1;
    } catch(const std::exception& e){std::fprintf(stderr,"translation_exception=%s\n",e.what());return 6;}
}
