#!/usr/bin/env python3
"""Piecewise integer proof that the pinned GPU SPU reciprocal is monotone.

Within each exponent/LUT segment, FI's unsigned mantissa is affine with a
nonpositive slope. Its one-step normalization/truncation is monotone provided
2**31 <= mantissa < 2**33. Checking every segment join then covers every
normal positive input bit pattern, not a random float sample.
"""
import argparse,hashlib,json,re
from pathlib import Path
def check(source):
 a=source.index('constant uint bces_frest');b=source.index('constant uint bces_frsqrt',a)
 table=[int(v,16) for v in re.findall(r'0x[0-9a-fA-F]+',source[a:b])];assert len(table)==32
 def reciprocal(x):
  e=(x>>23)&255;est=((0 if e>=253 else 253-e)<<23)|table[(x>>18)&31];e=(est>>23)&255
  if not e:return 0
  m=((8192|((est>>10)&8191))<<19)-(est&1023)*(x&0x7ffff)
  if m<1<<32:
   m<<=1;e-=1
   if not e:return 0
  return (e<<23)|((m>>9)&0x7fffff)
 ranges=[]
 for k,t in enumerate(table):
  slope=t&1023;base=(8192|((t>>10)&8191))<<19;lo=(k&1)<<18;hi=lo+(1<<18)-1
  minimum,maximum=base-slope*hi,base-slope*lo
  assert 1<<31<=minimum<=maximum<1<<33,(k,minimum,maximum)
  ranges.append(dict(index=k,slope=slope,minimum=minimum,maximum=maximum))
 joins=0
 for e in range(1,256):
  for k in range(32):
   lo=(e<<23)|(k<<18);hi=lo+(1<<18)-1
   assert reciprocal(lo)>=reciprocal(hi),(e,k,'within segment')
   if hi<0x7fffffff:
    assert reciprocal(hi)>=reciprocal(hi+1),(e,k,'join');joins+=1
 return dict(valid=True,lut_segments=32,exponent_segments=255*32,joins_checked=joins,integer_mantissa_ranges=ranges,source_sha256=hashlib.sha256(source.encode()).hexdigest(),scope='All normal positive SPU encodings, including exponent255 extended finite values; exponent-zero is SPU zero and must be handled separately. Negative domain follows sign symmetry. Monotonicity alone is not a tile-bound or FPS proof.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=check(a.source.read_text());a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='integer_mantissa_ranges'},indent=2))
