#!/usr/bin/env python3
"""Compile local batch integration checks; no device install or connection.
Run the returned binary separately where Mac Metal access is available.
"""
import hashlib,json,subprocess,sys,shlex
from pathlib import Path
from prepare_geometry_kernels import prepare as kernels
from geometry_batches import prepare as batches
from skinning_ir import ROOT
work=kernels();batches();sanitized='--release' not in sys.argv;suffix='asan' if sanitized else 'release'
inc=['-I'+str(p) for p in (ROOT/'src/platform',ROOT/'src/game',work,ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu')]
common=['-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT']+(['-fsanitize=address,undefined'] if sanitized else [])
objects=[]
for source in (work/'geometry_execute.c',work/'geometry_batches.c',ROOT/'src/platform/GeometryMathProbe.c'):
 obj=work/(source.stem+'-'+suffix+'.o');command=['clang','-std=gnu17',*common,*inc,'-c',str(source),'-o',str(obj)]
 depfile=obj.with_suffix('.d');command+=['-MMD','-MF',str(depfile)]
 stamp=obj.with_suffix('.fingerprint');old={}
 try:old=json.loads(stamp.read_text())
 except (ValueError,FileNotFoundError):pass
 def fingerprint(deps):
  return hashlib.sha256(json.dumps(command).encode()+source.read_bytes()+b''.join(Path(p).read_bytes() for p in deps)).hexdigest()
 deps=old.get('deps',[])
 valid=obj.exists() and deps and all(Path(p).exists() for p in deps) and old.get('hash')==fingerprint(deps)
 if not valid:
  subprocess.run(command,check=True)
  deps=shlex.split(depfile.read_text().replace('\\\n',' ').split(':',1)[1])
  stamp.write_text(json.dumps({'deps':deps,'hash':fingerprint(deps)}))
 objects.append(str(obj))
binary=work/('batch-check-'+suffix)
subprocess.run(['clang++','-std=c++20','-fobjc-arc',*common,*inc,str(ROOT/'src/platform/GeometryMetalBatches.mm'),str(ROOT/'src/host/GeometryBatchCheck.mm'),*objects,'-framework','Foundation','-framework','Metal','-o',str(binary)],check=True)
print(binary,flush=True)
