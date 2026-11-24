#!/usr/bin/env python3
"""Separate 70-unit iPhoneOS SPU inline variant; baseline objects untouched."""
import hashlib,json,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'out/bces-support-compile-iphoneos-spu-O2-copy.json';base=json.loads(B.read_text());assert base['result']=='PASS' and len(base['units'])==83
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer',TMPDIR=str(R/'build/tmp'))
O=R/'build/bces01229/support-compile/iphoneos-channel55';O.mkdir(exist_ok=True,parents=True);report_path=R/'out/bces-support-channel55.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(base['archive'])==base['archive_sha256']
header=R/'src/platform/SpuChannelInline.h';sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],env=env,text=True).strip()
identity=hashlib.sha256((sha(B)+sha(header)+sha(R/'src/platform/SpuChannelControl.h')+sdk+subprocess.check_output(['xcrun','clang','--version'],env=env,text=True)).encode()).hexdigest()
prior=json.loads(report_path.read_text()) if report_path.exists() else {}
old={u['source']:u for u in prior.get('units',[])} if prior.get('channel_cache_identity')==identity else {}
report={**base,'result':'BUILDING','archive':None,'units':[],'channel_inline':True,'channel_cache_identity':identity,'channel_inline_header':str(header),'channel_inline_header_sha256':sha(header),'channel_control_header_sha256':sha(R/'src/platform/SpuChannelControl.h'),'baseline_report_sha256':sha(B),'baseline_archive_sha256':sha(base['archive']),'compiler_jobs':1,'game_run':False}
def save():
 p=report_path.with_suffix('.tmp');p.write_text(json.dumps(report,indent=2)+'\n');p.replace(report_path)
save()
selected=0
for index,u in enumerate(base['units']):
 assert sha(u['source'])==u['sha256'] and sha(u['object'])==u['object_sha256']
 assert hashlib.sha256(subprocess.check_output(['ar','-p',base['archive'],Path(u['object']).name])).hexdigest()==u['object_sha256']
 if Path(u['source']).name!='spu_recomp.c':report['units'].append({**u,'baseline_reused':True});save();continue
 selected+=1;directory=O/'sources'/Path(u['source']).parent.name;directory.mkdir(exist_ok=True,parents=True)
 source=directory/'spu_recomp.c';text=Path(u['source']).read_text();marker='#include "spu_helpers.h"\n';assert text.count(marker)==1
 text=text.replace(marker,marker+'#include "'+str(header)+'"\n',1)
 if not source.exists() or source.read_text()!=text:source.write_text(text)
 generated_header=Path(u['source']).with_suffix('.h');(directory/'spu_recomp.h').write_bytes(generated_header.read_bytes())
 obj=O/Path(u['object']).name;log=obj.with_suffix('.log');cmd=list(u['command']);cmd[cmd.index('-isysroot')+1]=sdk
 cmd=[str(source) if x==u['source'] else str(obj) if x==u['object'] else x for x in cmd];assert cmd.count('-O2')==1
 cached=old.get(str(source),{});hit=cached.get('command')==cmd and cached.get('returncode')==0 and obj.exists() and sha(obj)==cached.get('object_sha256')
 if hit:item={**cached,'cached':True}
 else:
  print(f"building {index+1}/83 {Path(u['source']).parent.name}",flush=True)
  with log.open('w') as f:rc=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
  build=subprocess.check_output(['xcrun','vtool','-show-build',str(obj)],env=env,text=True) if rc==0 else ''
  item={**u,'source':str(source),'sha256':sha(source),'object':str(obj),'object_sha256':sha(obj) if rc==0 else None,'command':cmd,'log':str(log),'returncode':rc,'platform_verified':'platform IOS\n' in build,'cached':False,'original_channel_source':u['source'],'original_channel_source_sha256':u['sha256'],'generated_header_sha256':sha(generated_header)}
 report['units'].append(item);save()
 if item['returncode'] or not item['platform_verified']:report['result']='FAIL';save();raise SystemExit('Compile failed: '+str(log))
 print(f"done {index+1}/83 {'cached' if hit else 'compiled'}",flush=True)
assert selected==70 and len(report['units'])==83
archive=O/'libbces_support.a';subprocess.run(['xcrun','libtool','-static','-o',str(archive),*[u['object'] for u in report['units']]],env=env,check=True)
report.update(result='PASS',archive=str(archive),archive_sha256=sha(archive),channel_inline_units=70);save();print('PASS 70 SPU units inline-ready, 13 unchanged objects, original archive preserved',flush=True)
