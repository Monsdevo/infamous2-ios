#!/usr/bin/env python3
"""Separate Mac research target; shared current overlays, SDK-matched archives."""
from pathlib import Path
import hashlib,json,shutil,subprocess,argparse
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,s):
 p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists() or p.read_text()!=s:p.write_text(s)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--spu-local-registers',action='store_true');args=parser.parse_args()
 work=ROOT/'build/bces01229';out=work/'host-research-prepared';out.mkdir(exist_ok=True)
 # Consume a text-only snapshot, never an iPhone object/archive.
 current=work/'ios-prepared';copied={}
 for p in current.rglob('*'):
  if p.is_file() and p.suffix in ('.c','.cpp','.h','.m','.inc'):
   relative=p.relative_to(current);q=out/relative;put(q,p.read_text());copied[str(relative)]=sha(p)
 from prepare_host_ibcache import patch as ib_patch
 channels=out/'diagnostic_spu_channels.c';put(channels,ib_patch(channels.read_text()))
 backend=out/'renderer-overlay/libs/video/rsx_metal_backend.m'
 from prepare_host_normals_writeback import patch as normals_patch
 engine=out/'renderer-overlay/libs/video/rsx_draw_engine.c'
 light=out/'gpu_light.c';ssao=out/'gpu_ssao.c'
 for path,source in zip((engine,light,ssao),normals_patch(engine.read_text(),light.read_text(),ssao.read_text())):put(path,source)
 s=backend.read_text();marker='        if (drawable) { fps_track_drawable(drawable); surface_track_submission(cb, drawable); [cb presentDrawable:drawable]; }'
 assert s.count(marker)==2
 # Count completed offscreen GAME present command buffers, not render-loop
 # iterations or submissions. No additional GPU fence/readback is introduced.
 start=s.index('static void eng_encode_and_commit(');pos=s.index(marker,start)
 s=s[:pos]+'''#if !TARGET_OS_IPHONE
        if(present_dst && s_headless) {
            [cb addCompletedHandler:^(id<MTLCommandBuffer> done) {
                bces_host_gpu_done(CACurrentMediaTime(),done.GPUEndTime-done.GPUStartTime,
                                   done.status==MTLCommandBufferStatusError);
            }];
        }
#endif
'''+s[pos:]
 s='extern void bces_host_gpu_done(double,double,int);\n'+s;put(backend,s)
 # Pipeline telemetry was UIKit-gated in the iOS overlay. Observe the same
 # actual compile calls on Mac so warm-window rejection is effective.
 start=s.index('static id<MTLRenderPipelineState> ios_profiled_pipeline(')
 end=s.index('\n}',start)+2
 body=s[start:end].replace('#if TARGET_OS_IPHONE\n','').replace('#endif\n','')
 s=s[:start]+body+s[end:];put(backend,s)
 from prepare_host_pass_probe import patch as pass_probe
 put(backend,pass_probe(s))
 from prepare_lighting_far_reject import ensure_backend as far_reject
 put(backend,far_reject(backend.read_text()))
 from prepare_host_depth_only import patch as depth_only
 put(backend,depth_only(backend.read_text()))
 from prepare_light_mask_empty import patch as empty_mask
 put(backend,empty_mask(backend.read_text()))
 support=json.loads((ROOT/'out/bces-support-compile-macosx-spu-O2.json').read_text())
 assert support['result']=='PASS' and support['sdk']=='macosx'
 assert sha(support['archive'])==support['archive_sha256']
 derived=out/'libbces_support.a';shutil.copyfile(support['archive'],derived)
 replaced=[]
 for u in support['units']:
  assert sha(u['source'])==u['sha256'] and sha(u['object'])==u['object_sha256']
  if any(x in u['source'] for x in ('jobmod_c6e7383dc013_e5400/','jobmod_e6fe749031f8_e2060/')):replaced.append(Path(u['object']).name)
 assert len(replaced)==2
 from prepare_host_spu_math import prepare as prepare_math
 replaced.append(prepare_math(out,args.spu_local_registers))
 subprocess.run(['ar','-d',str(derived),*replaced],check=True);subprocess.run(['ranlib',str(derived)],check=True)
 original=ROOT/'build/host/libps3recomp_full_runtime.a'
 snapshot=json.loads((ROOT/'out/bces-support-host-build.json').read_text())
 assert any(Path(i['path'])==original and sha(original)==i['sha256'] for i in snapshot['inputs'])
 runtime=out/'libps3recomp_game_runtime.a';shutil.copyfile(original,runtime)
 excluded=['rsx_metal_backend.m.o','rsx_shader_msl.cpp.o','sys_ppu_thread.c.o','spu_channels.c.o','spu_drain.c.o','cellGcmSys.c.o','rsx_draw_engine.c.o']
 members=subprocess.check_output(['ar','-t',str(original)],text=True).splitlines()
 assert all(members.count(n)==1 for n in excluded)
 subprocess.run(['ar','-d',str(runtime),*excluded],check=True);subprocess.run(['ranlib',str(runtime)],check=True)
 # Reuse the complete already-built macOS PPU lift, with explicit inventory
 # and platform checks; neither recompilation nor iOS object reuse is needed.
 manifest=json.loads((ROOT/'out/bces-codegen-manifest.json').read_text())
 objects=[]
 for source in sorted((work/'recompiled').glob('ppu_recomp_*.cpp')):
  assert sha(source)==manifest['source_sha256'][source.name]
  obj=work/'host/CMakeFiles/Infamous2BCES.dir'/source.relative_to('/')
  obj=Path(str(obj)+'.o');assert obj.exists(),obj
  info=subprocess.check_output(['vtool','-show-build',str(obj)],text=True)
  assert 'platform MACOS' in info,info
  objects.append(obj)
 assert len(objects)==164
 title=out/'libbces_title.a'
 subprocess.run(['xcrun','libtool','-static','-o',str(title),*map(str,objects)],check=True)
 deps=[]
 for i in snapshot['inputs']:
  p=Path(i['path'])
  if p.suffix=='.a' and p not in (original,Path(snapshot.get('support_archive','/missing'))) and p.name!='libbces_support.a':
   assert sha(p)==i['sha256'];deps.append(p)
 lines=[f'set(HOST_TITLE "{title}")',f'set(HOST_SUPPORT "{derived}")',f'set(HOST_RUNTIME "{runtime}")','set(HOST_DEPS',*['  "'+str(p)+'"' for p in dict.fromkeys(deps)],')','']
 put(out/'dependencies.cmake','\n'.join(lines))
 report=dict(host_math_source_sha256=sha(out/'host_spu_math.c'),host_math_transform_sha256=sha(ROOT/'tools/prepare_host_spu_math.py'),host_math_helpers_sha256=sha(ROOT/'src/game/BCESSpuRZ.h'),light_mask_interval_sha256=sha(ROOT/'src/host/LightMaskInterval.metal'),shared_sources=copied,host_backend_sha256=sha(backend),preparation_sha256=sha(__file__),ppu_objects={str(p):sha(p) for p in objects},runtime_sha256=sha(runtime),support_sha256=sha(derived),source_sdk='macosx',excluded_members=excluded,device_performance_claim=False)
 put(out/'manifest.json',json.dumps(report,indent=2)+'\n');print('Prepared separate Mac target:164 PPU chunks, macOS O2 SPU, current Metal lighting/SSAO and opt-in dispatch')
if __name__=='__main__':main()
