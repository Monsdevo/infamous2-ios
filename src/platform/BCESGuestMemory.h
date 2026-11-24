#pragma once
#include <stddef.h>
#include <stdint.h>
#include <sys/mman.h>

// Preserve the original guest range and zero-fill semantics. Anonymous VM is
// demand-backed, with no malloc zone retaining this multi-GiB reservation.
static const size_t BCES_GUEST_MEMORY_SIZE = 0xE0000000ull;
static inline uint8_t* bces_guest_memory_allocate(void) {
    void* p = mmap(NULL, BCES_GUEST_MEMORY_SIZE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANON, -1, 0);
    return p == MAP_FAILED ? NULL : (uint8_t*)p;
}
static inline int bces_guest_memory_release(uint8_t* p) {
    return munmap(p, BCES_GUEST_MEMORY_SIZE);
}
