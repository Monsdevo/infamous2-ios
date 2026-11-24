#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_edge_set_enabled(int enabled);
int bces_edge_enabled(void);
uint64_t bces_edge_calls(unsigned block);
void bces_edge_note_call(unsigned block);
int bces_edge_validate_next(unsigned block);
void bces_edge_validation_result(int equal);
uint64_t bces_edge_validations(void);
uint64_t bces_edge_mismatches(void);
void bces_edge_control_configure(const char* directory);
void bces_edge_control_poll(void);
void* bces_edge_snapshot_input(const void* context,unsigned block);
void bces_edge_snapshot_finish(void* snapshot,const void* reference,const void* actual,const void* reference_ls,int equal);
void bces_edge_flush_capture(const char* directory);
#ifdef __cplusplus
}
#endif
