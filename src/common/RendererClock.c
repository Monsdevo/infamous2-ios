#include <time.h>
// The real game supplies this through cellGcmSys.c. Only diagnostic targets
// use this monotonic clock; do not link this file alongside cellGcmSys.c.
unsigned long long ps3_ms_now(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (unsigned long long)now.tv_sec * 1000 + (unsigned long long)now.tv_nsec / 1000000;
}
