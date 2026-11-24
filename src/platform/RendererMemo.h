#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { BCES_MEMO_VERTEX=0, BCES_MEMO_TEXTURE=1, BCES_MEMO_KINDS=2,
       BCES_MEMO_INPUTS=17 };
typedef struct { const void* data; size_t bytes; } BCESMemoInput;
typedef struct {
    unsigned mode, hit, slot, count;
    uint64_t generation;
    const void* inputs[BCES_MEMO_INPUTS];
    void* output;
} BCESMemoTicket;
typedef struct {
    uint64_t calls,lookups,hits,misses,bypasses,evictions,validations,mismatches;
    uint64_t compared_bytes,snapshot_bytes,output_bytes,resident_bytes;
    unsigned mode;
} BCESMemoStats;
// Mode 0 = reference, 1 = exact-input memo, 2 = reference-output validation.
// Only mode is written by the control/UI thread. All storage belongs to the
// serialized renderer. No pointer-only or probabilistic content acceptance.
void bces_renderer_memo_set(unsigned kind,unsigned mode);
unsigned bces_renderer_memo_mode(unsigned kind);
void bces_renderer_memo_note_call(unsigned kind);
int bces_renderer_memo_begin(unsigned kind,const void* key,size_t key_bytes,
    const BCESMemoInput* inputs,unsigned count,size_t output_bytes,BCESMemoTicket* ticket);
void bces_renderer_memo_commit(unsigned kind,const BCESMemoTicket* ticket,int valid);
void bces_renderer_memo_validation(unsigned kind,const BCESMemoTicket* ticket,int equal);
void bces_renderer_memo_publish(void);
BCESMemoStats bces_renderer_memo_stats(unsigned kind);
// Renderer-only cleanup, after all callers stopped; also used by host tests.
void bces_renderer_memo_clear(unsigned kind);
#ifdef __cplusplus
}
#endif
