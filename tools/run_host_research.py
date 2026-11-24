#!/usr/bin/env python3
"""Bounded real Mac game session, all assets/saves/logs/temp on monssd."""
import argparse,hashlib,json,os,signal,subprocess,time,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def stop(proc):
 if proc.poll() is not None:return
 os.killpg(proc.pid,signal.SIGTERM)
 try:proc.wait(timeout=3)
 except subprocess.TimeoutExpired:
  os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=3)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--label',required=True)
 p.add_argument('--seconds',type=int,default=1800)
 p.add_argument('--install-template',type=Path,help='COW-clone only a previous research session game-install cache; saves are never copied')
 a=p.parse_args()
 if not a.label.replace('-','').isalnum() or not 30<=a.seconds<=3600:p.error('invalid label/duration')
 run=ROOT/'out/host-research'/a.label;run.mkdir(parents=True,exist_ok=False)
 profile=json.loads((ROOT/'profiles/BCES01229-01.00.json').read_text())
 elf=ROOT/'data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf'
 assert hashlib.sha256(elf.read_bytes()).hexdigest()==profile['elf_sha256']
 vfs=run/'vfs';vfs.mkdir();(vfs/'PS3_GAME').symlink_to(ROOT/'data/game/BCES01229',target_is_directory=True)
 for n in ('dev_hdd0','gamedata'):(vfs/n).mkdir()
 (run/'shaders').mkdir()
 if a.install_template:
  template=a.install_template.resolve();saved=json.loads((template/'session.json').read_text())
  assert template.is_relative_to(ROOT/'out/host-research') and saved['environment']['PS3_BOOT_PATH']=='/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN'
  cache=template/'vfs/dev_hdd0/game'
  if cache.is_dir():subprocess.run(['cp','-cR',str(cache),str(vfs/'dev_hdd0/game')],check=True)
 (run/'pad.txt').write_text('');(run/'cpu-profile-control.txt').write_text('idle\n');(run/'frame-trace-control.txt').write_text('idle\n')
 env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer',TMPDIR=str(ROOT/'build/tmp'),
  BCES_RESEARCH_DIR=str(run),BCES_BOOT_SECONDS=str(a.seconds),BCES_BOOT_PHYSICAL_LIMIT_MIB='2500',
  PS3_VFS_ROOT=str(vfs),PS3_HDD0_ROOT=str(vfs/'dev_hdd0'),PS3_GAMEDATA_ROOT=str(vfs/'gamedata'),
  PS3_DEV_FLASH=str(ROOT/'data/firmware/dev_flash'),PS3_BOOT_PATH='/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN',PS3_LANG='en',
  HEADLESS='1',PS3RECOMP_METAL_HEADLESS='1',PS3_VERBOSE='0',GCM_SEMA_ACQUIRE='1',GCM_SEMA_ACQUIRE_MS='200',GCM_PARK_GRACE_MS='1000',
  PS3RECOMP_ENG_GPU_LIGHT='06FF3B80:07377B80',PS3RECOMP_ENG_GPU_SSAO='1',PS3RECOMP_ENG_SKIP_FP='',
  PS3RECOMP_METAL_SHADER_DUMP=str(run/'shaders'),PS3RECOMP_ENG_SHADER_DUMP=str(run/'shaders'),
  PS3_PAD_FILE=str(run/'pad.txt'),PS3RECOMP_METAL_FRAME_DUMP=str(run/'frame.ppm'),
  PS3RECOMP_METAL_FRAME_DUMP_TRIGGER=str(run/'frame-request.txt'),PS3RECOMP_ENG_WORLD_MARK=str(run/'world-mark.txt'))
 for n in ('PS3RECOMP_METAL_HEADLESS_SYNC','PAD_AUTOPRESS','PAD_SCRIPT','PAD_FILE','PAD_STICK','PAD_SWEEP','PS3RECOMP_ENG_GPU_LIGHT_NOWB'):env.pop(n,None)
 binary=ROOT/'build/bces01229/host-research/Infamous2Research';metadata=dict(binary=str(binary),sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),environment={k:v for k,v in env.items() if k.startswith(('PS3','BCES','GCM','HEADLESS','TMPDIR'))},device_performance_claim=False)
 uuid=re.search(r'UUID: ([0-9A-Fa-f-]+)',subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],env=env,text=True)).group(1)
 symbols=ROOT/'build/bces01229/symbols'/uuid;symbols.mkdir(exist_ok=True);symbol_binary=symbols/binary.name
 if not symbol_binary.exists():subprocess.run(['cp','-c',str(binary),str(symbol_binary)],check=True)
 assert hashlib.sha256(symbol_binary.read_bytes()).hexdigest()==metadata['sha256']
 metadata.update(uuid=uuid,symbol_binary=str(symbol_binary))
 with (run/'boot.log').open('wb') as log:
  proc=subprocess.Popen([str(binary),str(elf)],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  metadata.update(pid=proc.pid,state='running');(run/'session.json').write_text(json.dumps(metadata,indent=2)+'\n');print(json.dumps(dict(pid=proc.pid,run=str(run)),indent=2),flush=True)
  start=time.monotonic()
  try:
   while proc.poll() is None:
    if time.monotonic()-start>a.seconds+10:
     stop(proc);break
    time.sleep(1)
   proc.wait(timeout=5)
  except BaseException:
   stop(proc)
   raise
  finally:
   metadata.update(state='stopped',returncode=proc.poll(),elapsed=time.monotonic()-start);(run/'session.json').write_text(json.dumps(metadata,indent=2)+'\n')
if __name__=='__main__':main()
