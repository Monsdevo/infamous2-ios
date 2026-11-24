#!/usr/bin/env python3
"""Narrow iOS FIFO adapter; never changes the pinned processor or Mac target."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def instrument(gcm,sdk):
 lock=json.loads((ROOT/'sources.lock.json').read_text())['ios_rsx_legacy_fastpath']
 for key in ('source','header'):
  if hashlib.sha256((sdk/lock[key]).read_bytes()).hexdigest()!=lock[key+'_sha256']:
   raise ValueError('Legacy RSX source/header changed: audit the state-only whitelist again')
 header='#include "RSXLegacyFastPath.h"\n'
 marker='''                { static int eng = -1;
                  if (eng < 0) eng = rsx_draw_engine_enabled();
                  if (eng) rsx_draw_engine_method((subch << 13) | m, dw); }'''
 replacement='''                int bces_dispatch_active;
                { static int eng = -1;
                  if (eng < 0) eng = rsx_draw_engine_enabled();
                  bces_dispatch_active=eng;
                  if (eng) rsx_draw_engine_method((subch << 13) | m, dw); }'''
 old='                    rsx_process_method(&s_state, m, dw);'
 drain='    gcm_rsx_process_fifo_unlocked();\n    ReleaseSRWLockExclusive(&s_gcm_fifo_lock);'
 for part in (marker,old,drain):
  if gcm.count(part)!=1:raise ValueError('GCM fastpath patch location changed')
 return header+gcm.replace(marker,replacement).replace(old,
  '                    bces_rsx_legacy_method(&s_state, m, dw, bces_dispatch_active);').replace(drain,
  '    gcm_rsx_process_fifo_unlocked();\n    bces_rsx_legacy_publish();\n    ReleaseSRWLockExclusive(&s_gcm_fifo_lock);')
