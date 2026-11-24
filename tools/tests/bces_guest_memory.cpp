#include "BCESGuestMemory.h"
#include <cassert>
#include <cstdio>
int main() {
    for (int pass=0; pass<2; ++pass) {
        volatile uint8_t* arena=bces_guest_memory_allocate();
        assert(arena);
        const size_t offsets[]={0,0x0feff000u,0x30000000u,0xd0000000u,0xdffff000u,BCES_GUEST_MEMORY_SIZE-1};
        for(size_t address:offsets) { assert(arena[address]==0);arena[address]=0xa5;assert(arena[address]==0xa5); }
        assert(bces_guest_memory_release(const_cast<uint8_t*>(arena))==0);
    }
    puts("PASS: 3.5 GiB anonymous guest VM, sparse endpoints, release and zero-filled reallocation");
}
