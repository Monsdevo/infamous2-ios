#!/usr/bin/env python3
"""Produce bounded arithmetic fixtures using original lifted SPU tile code.
Inputs stay under out/; never include game bytes in source control.
"""
import argparse,json,struct,subprocess,math
from pathlib import Path

def make(source,output,harness):
    original=bytearray((source/'before-ls.bin').read_bytes());gpr=(source/'before-gpr.bin').read_bytes();meta=json.loads((source/'metadata.json').read_text())
    f=meta['frame_lsa'];l=meta['lights_lsa'];n=meta['normal_lsa'];z=meta['depth_lsa'];w=meta['width'];h=meta['height'];i=(h//2)*w+w//2
    m=struct.unpack_from('>16f',original,f+16);zz=int.from_bytes(original[z+4*i:z+4*i+3],'big')/16777216
    v=[(meta['x']*w+w//2)/meta['full_width'],(meta['y']*h+h//2)/meta['full_height'],zz,1]
    p=[sum(v[r]*m[4*r+c] for r in range(4)) for c in range(4)];p=[a/p[3] for a in p[:3]]
    normal=[original[n+4*i+k]*2/255-1 for k in (1,2,3)];length=math.sqrt(sum(a*a for a in normal));normal=[a/length for a in normal]
    cases=['point-lit','point-backface','point-dark-colour','point-far','spot-lit','spot-away','zero-lights','all-sky','mixed-sky']
    output.mkdir(parents=True,exist_ok=True)
    for case in cases:
        folder=output/case;folder.mkdir(exist_ok=True);b=bytearray(original)
        struct.pack_into('>I',b,f+0x90,0 if case=='zero-lights' else 1)
        sign=-1 if case=='point-backface' else 1
        pos=[p[k]+sign*100*normal[k] for k in range(3)]
        if case=='point-far':pos=[a+200000 for a in pos]
        b[l:l+48]=bytes(48);struct.pack_into('>3f',b,l,*pos);struct.pack_into('>3e',b,l+12,*((0,0,0) if case=='point-dark-colour' else (.5,.25,.125)))
        struct.pack_into('>I',b,l+20,2 if case.startswith('spot') else 1)
        struct.pack_into('>8e',b,l+32,0,500,-2.5,.5,*[a*(1 if case=='spot-away' else -1) for a in normal],0)
        if case=='all-sky':b[z:z+w*h*4]=bytes([255,255,255,0])*(w*h)
        if case=='mixed-sky':b[z:z+w*(h//2)*4]=bytes([255,255,255,0])*(w*(h//2))
        (folder/'before-ls.bin').write_bytes(b);(folder/'before-gpr.bin').write_bytes(gpr)
        info=dict(meta,lights=0 if case=='zero-lights' else 1,fixture_kind='synthetic light on captured BCES geometry',case=case)
        (folder/'metadata.json').write_text(json.dumps(info,indent=2)+'\n')
        subprocess.run([str(harness),str(folder/'before-ls.bin'),str(folder/'before-gpr.bin'),str(folder/'after-ls.bin')],check=True)
        after=(folder/'after-ls.bin').read_bytes();a=after[meta['diffuse_lsa']:meta['diffuse_lsa']+w*h*4]
        print(case,'alpha-nonzero',sum(a[i]!=0 for i in range(0,len(a),4)),'rgb-nonzero',sum(a[i]!=0 for i in range(len(a)) if i%4))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--harness',type=Path,required=True);a=p.parse_args();make(a.source,a.output,a.harness)
