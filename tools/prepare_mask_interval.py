#!/usr/bin/env python3
"""Build an isolated replay source from the exact current SPU helper prefix."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 s=(ROOT/'build/bces01229/host-research-prepared/renderer-overlay/libs/video/rsx_metal_backend.m').read_text();a=s.index('"struct GLight {');b=s.index('/* inFAMOUS 2\'s SSAO job',a)
 m=''.join(ast.literal_eval(q.strip()) for q in s[a:b].splitlines() if q.startswith('"'));p=ROOT/'build/bces01229/gain40-mask-empty/test-interval.metal'
 p.write_text('#include <metal_stdlib>\nusing namespace metal;\n'+m[:m.index('\nstruct GLOut')]+(ROOT/'src/host/LightMaskInterval.metal').read_text());print(p)
if __name__=='__main__':main()
