#pragma once
#include "FullRuntimeProbe.h"
#include <functional>

// One outstanding batch. The handoff mutex establishes guest-memory visibility;
// a second producer/unsynchronised shared GCM register is deliberately excluded.
bool runtime_renderer_start(FullRuntimeControl*, std::function<void()> idle,
                            std::function<void()> shutdown);
bool runtime_render_call(FullRuntimeControl*, std::function<void()>);
bool runtime_ppu_checkpoint(FullRuntimeControl*, unsigned delay_ms = 0);
void runtime_renderer_finish(FullRuntimeControl*);
void runtime_ppu_begin(FullRuntimeControl*);
void runtime_ppu_end(FullRuntimeControl*);
