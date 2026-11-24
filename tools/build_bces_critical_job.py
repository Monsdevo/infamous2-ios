#!/usr/bin/env python3
"""Replace only the measured SPU module; preserve 82 baseline objects."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
from prepare_critical_job import patch,patch_wws,patch_logical
R=Path(__file__).resolve().parents[1];B=R/'out/bces-support-compile-iphoneos-spu-O2-copy.json'
base=json.loads(B.read_text());assert base['result']=='PASS' and len(base['units'])==83
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(base['archive'])==base['archive_sha256']
p=argparse.ArgumentParser();p.add_argument('--whole-jobs',action='store_true');p.add_argument('--logical-jobs',action='store_true');args=p.parse_args()
version='59' if args.logical_jobs else '58' if args.whole_jobs else '57'
registry=(R/'build/bces01229/spu/jobmods_register.c').read_text()
entries={name:int(entry,16) for name,entry in re.findall(r'(jobmod_\w+) entry (0x[0-9A-Fa-f]+)',registry)}
assert len(entries)==27
O=R/('build/bces01229/support-compile/iphoneos-critical'+version);O.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer',TMPDIR=str(R/'build/tmp'))
sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],env=env,text=True).strip()
result={**base,'result':'BUILDING','units':[],'archive':None,'critical_job_trace':True,'critical_job_whole_jobs':args.whole_jobs or args.logical_jobs,'critical_job_logical_jobs':args.logical_jobs,'critical_trace_header_sha256':sha(R/'src/platform/CriticalJobTrace.h'),'baseline_report_sha256':sha(B)}
selected=0
for u in base['units']:
 assert sha(u['source'])==u['sha256'] and sha(u['object'])==u['object_sha256']
 assert hashlib.sha256(subprocess.check_output(['ar','-p',base['archive'],Path(u['object']).name])).hexdigest()==u['object_sha256']
 is_wws='wwsjob_pm_at_00887100/spu_recomp.c' in u['source'] and args.whole_jobs and not args.logical_jobs
 module=Path(u['source']).parent.name
 logical=module in entries and Path(u['source']).name=='spu_recomp.c' and args.logical_jobs
 if 'jobmod_638a73a6476e_e60c0/spu_recomp.c' not in u['source'] and not is_wws and not logical:
  result['units'].append({**u,'baseline_reused':True});continue
 selected+=1;directory=O/Path(u['source']).parent.name;directory.mkdir(exist_ok=True)
 source=directory/'spu_recomp.c';text=Path(u['source']).read_text()
 if logical:text=patch_logical(text,module,entries[module])
 if 'jobmod_638a73a6476e_e60c0'==module:text=patch(text)
 if is_wws:text=patch_wws(text)
 source.write_text(text)
 shutil.copy2(Path(u['source']).with_suffix('.h'),directory/'spu_recomp.h')
 obj=O/Path(u['object']).name;cmd=list(u['command']);cmd[cmd.index('-isysroot')+1]=sdk
 cmd=[str(source) if x==u['source'] else str(obj) if x==u['object'] else x for x in cmd]
 first_include=next(i for i,x in enumerate(cmd) if x.startswith('-I'))
 cmd[first_include:first_include]=['-I'+str(R/'src/platform'),'-I'+str(R/'build/bces01229/ios-prepared/trace-include')]
 log=obj.with_suffix('.log')
 with log.open('w') as f:rc=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 if rc:raise RuntimeError('Compile failed: '+str(log))
 platform=subprocess.check_output(['xcrun','vtool','-show-build',str(obj)],env=env,text=True);assert 'platform IOS\n' in platform
 result['units'].append({**u,'source':str(source),'sha256':sha(source),'object':str(obj),'object_sha256':sha(obj),'command':cmd,'log':str(log),'platform_verified':True,'baseline_reused':False})
assert selected==(27 if args.logical_jobs else 2 if args.whole_jobs else 1)
archive=O/'libbces_support.a';subprocess.run(['xcrun','libtool','-static','-o',str(archive),*[u['object'] for u in result['units']]],env=env,check=True)
result.update(result='PASS',archive=str(archive),archive_sha256=sha(archive))
(R/('out/bces-support-critical'+version+'.json')).write_text(json.dumps(result,indent=2)+'\n')
print(f'PASS: {selected} SPU modules instrumented, {83-selected} original objects preserved; iPhoneOS only')
