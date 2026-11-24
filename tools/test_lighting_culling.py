#!/usr/bin/env python3
"""End-to-end mask regression against the original lifted SPU arithmetic.
Does not assert numerical identity of the shading approximation: reports it.
"""
import json,subprocess,argparse,struct,random,math
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--count',type=int,default=64);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=True)
 source=Path('out/lighting-cull-fixtures/point-dark-colour');original=(source/'before-ls.bin').read_bytes();gpr=(source/'before-gpr.bin').read_bytes();meta=json.loads((source/'metadata.json').read_text());l=meta['lights_lsa'];rng=random.Random(52700)
 base=struct.unpack_from('>3f',original,l)
 results=[]
 for i in range(a.count):
  folder=a.output/f'case-{i:03}';folder.mkdir(exist_ok=True);b=bytearray(original)
  pos=[base[k]+rng.uniform(-2000,2000) for k in range(3)];struct.pack_into('>3f',b,l,*pos)
  spot=i%2;struct.pack_into('>I',b,l+20,2 if spot else 1)
  radius=rng.uniform(100,2500);axis=[rng.uniform(-1,1) for _ in range(3)];r=math.sqrt(sum(q*q for q in axis));axis=[q/r for q in axis]
  struct.pack_into('>8e',b,l+32,0,radius,-2.5,.5,*axis,0)
  (folder/'before-ls.bin').write_bytes(b);(folder/'before-gpr.bin').write_bytes(gpr);(folder/'metadata.json').write_text(json.dumps(meta))
  subprocess.run(['build/bces01229/lighting-spu-fixture',str(folder/'before-ls.bin'),str(folder/'before-gpr.bin'),str(folder/'after-ls.bin')],check=True)
  subprocess.run(['build/bces01229/lighting-replay',str(folder),str((folder/'gpu').resolve())],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  sample=json.loads((folder/'gpu/lighting-validation/report.json').read_text())['samples'][0]
  okay=sample['status']=='compared' and all(c['bit_exact'] for c in sample.get('comparison',[]))
  results.append({'case':i,'type':'spot' if spot else 'point','pass':okay,'result':sample})
  if not okay:print('FAIL',i,sample,flush=True)
 summary={'cases':len(results),'passed':sum(r['pass'] for r in results),'results':results}
 (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('mask stress',summary['passed'],'/',len(results),flush=True)
 return 0 if all(r['pass'] for r in results) else 1
if __name__=='__main__':raise SystemExit(main())
