#include "ShaderDiagnostics.h"
#include <cassert>
#include <cstdio>
#include <limits>
#include <new>
int main(int argc,char** argv) {
    assert(argc==2);
    bces_shader_diagnostics_configure(argv[1]);
    bces_shader_trace_begin("float4 main():SV_Target{return 1;}\n",1);
    volatile size_t impossible=std::numeric_limits<size_t>::max();
    bool caught=false;
    try { void* p=::operator new(impossible);::operator delete(p); }
    catch(const std::bad_alloc&){caught=true;}
    assert(caught);bces_shader_trace_end(-1);
    bces_shader_diagnostics_configure(nullptr);
    std::puts("PASS: failure tracing preserves bad_alloc and records input");
}
