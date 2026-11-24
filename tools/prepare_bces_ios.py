#!/usr/bin/env python3
"""Prepare an iPhoneOS-only real title, using verified SDK-specific archives.

No pinned source, Mac target, game input or existing device file is changed.
The derived runner preserves title boot/clock, adapting only the Apple host.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import shutil
import subprocess
from prepare_frame_diagnostics import prepare as prepare_frame_diagnostics
from prepare_lighting_validation import prepare as prepare_lighting_validation
from prepare_metal_lighting import prepare_renderer as prepare_metal_lighting, prepare_hook as prepare_metal_light_hook
from prepare_metal_ssao import prepare as prepare_metal_ssao, hook as prepare_metal_ssao_hook, depth_reference_source
from prepare_edge_geometry import prepare as prepare_edge_geometry
from prepare_geometry_kernels import prepare as prepare_geometry_kernels
from geometry_batches import prepare as prepare_geometry_batches
from prepare_edge_flow import renderer as prepare_edge_renderer
import prepare_job_flow
import prepare_gbuffer_flow
import prepare_gbuffer_fence
import prepare_half_depth_probe
import prepare_renderer_stages
import prepare_compact_vertex
from prepare_renderer_memo import prepare as prepare_renderer_memo
from prepare_spu_dispatch import prepare as prepare_spu_dispatch
from prepare_dma_poison import patch as prepare_dma_poison
from prepare_mfc_hint import patch as prepare_mfc_hint
from prepare_overlay_filter import patch as prepare_overlay_filter
from prepare_channel_inline import patch as prepare_channel_inline
from prepare_mfc_alignment import patch as prepare_mfc_alignment
from prepare_lighting_far_reject import ensure_backend as prepare_lighting_far
from prepare_light_mask_empty import patch as prepare_interval_mask

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-report", type=Path,
                        default=ROOT / "out/bces-support-compile-iphoneos.json",
                        help="Verified iPhoneOS support report; default preserves O1 baseline")
    parser.add_argument("--mfc-hint-experiment", action="store_true",
                        help="Include opt-in MFC lookup experiment; normal preparation preserves original lookup")
    parser.add_argument("--overlay-filter-experiment", action="store_true",
                        help="Include opt-in conservative overlay signature/page filter")
    parser.add_argument("--mfc-align128", action="store_true",
                        help="Align each private MFC registry slot to 128 bytes; requires process restart")
    parser.add_argument("--job-flow", action="store_true", help="Trace the consumers of three SPU jobs")
    parser.add_argument("--half-depth-probe", action="store_true", help="Capture paired SPU/Metal half-depth and trace guest readers")
    parser.add_argument("--gbuffer-fence", action="store_true", help="Build opt-in reuse of the depth fence for normal writeback")
    parser.add_argument("--gbuffer-flow", action="store_true", help="Trace G-buffer blits and selected SPU DMA consumers")
    parser.add_argument("--renderer-stages", action="store_true", help="Trace serial renderer CPU stages")
    parser.add_argument("--compact-vertex", action="store_true", help="Build opt-in packed vertex transport")
    args = parser.parse_args()
    work = ROOT / "build/bces01229"
    output = work / "ios-prepared"
    output.mkdir(parents=True, exist_ok=True)
    port = ROOT / "upstream/infamous2-recomp"
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    if subprocess.check_output(["git", "-C", str(port), "rev-parse", "HEAD"], text=True).strip() != lock["port"]["commit"]:
        raise SystemExit("Pinned port differs")
    title_report = json.loads((ROOT / "out/step11-title-ios-validation.json").read_text())
    title = Path(title_report["archive"])
    if sha(title) != title_report["archive_sha256"] or title_report["PPU_units"] != 164:
        raise SystemExit("Rebuild/validate the iPhoneOS title archive")
    manifest = json.loads((ROOT / "out/bces-codegen-manifest.json").read_text())
    for name, expected in manifest["source_sha256"].items():
        if sha(work / "recompiled" / name) != expected:
            raise SystemExit("Title generation changed: " + name)
    support_report = json.loads(args.support_report.read_text())
    if support_report["result"] != "PASS" or support_report.get("sdk") != "iphoneos" or len(support_report["units"]) != 83:
        raise SystemExit("iPhoneOS support compilation is incomplete")
    for item in support_report["units"]:
        if not item["platform_verified"] or sha(Path(item["source"])) != item["sha256"] or sha(Path(item["object"])) != item["object_sha256"]:
            raise SystemExit("Support source/object changed: " + item["source"])
    lighting_member=prepare_lighting_validation(output,support_report,port / "ps3recomp-fork")
    ssao_member=depth_reference_source(output,support_report)
    edge_member=prepare_edge_geometry(output,support_report)
    prepare_geometry_kernels()
    prepare_geometry_batches()
    archives = []
    snapshot = json.loads((ROOT / "out/step12-ios-archives.json").read_text())
    for item in snapshot["archives"]:
        name = item["archive"]
        if not ("/shader-deps/" in name or name.endswith(("libSDL2.a", "libios_fiber_context.a", "libps3recomp_full_runtime.a"))):
            continue
        path = ROOT / name
        if item["platform"] != "IOS" or sha(path) != item["sha256"]:
            raise SystemExit("SDK archive changed; rebuild/validate first: " + name)
        archives.append(path)
    support = Path(support_report["archive"])
    support_variant = support_report.get("variant", "spu-O1")
    critical_job=bool(support_report.get("critical_job_trace"))
    if args.job_flow and not support_report.get('critical_job_logical_jobs'):
        raise SystemExit('Job flow needs logical job scopes in the support archive')
    if critical_job and sha(ROOT/'src/platform/CriticalJobTrace.h')!=support_report.get('critical_trace_header_sha256'):
        raise SystemExit('Critical job probe archive/header identity differs')
    channel_inline=bool(support_report.get("channel_inline"))
    if channel_inline:
        if support_report.get("channel_inline_units")!=70 or sha(ROOT/'src/platform/SpuChannelInline.h')!=support_report.get('channel_inline_header_sha256') or sha(ROOT/'src/platform/SpuChannelControl.h')!=support_report.get('channel_control_header_sha256'):
            raise SystemExit('Channel inline archive/header identity differs')
    if support_variant not in ("spu-O1", "spu-O2", "spu-O2-copy"):
        raise SystemExit("Unknown support optimization variant")
    expected_o2 = 70 if support_variant.startswith("spu-O2") else 0
    if sum("-O2" in item["command"] for item in support_report["units"]) != expected_o2:
        raise SystemExit("Support variant label differs from compile commands")
    if support_variant == "spu-O2-copy":
        for path, key in ((support_report["original_source"], "original_source_sha256"),
                          (support_report["native_override"], "native_override_sha256"),
                          (ROOT / "src/game/BCESSpuCopy.h", "native_header_sha256")):
            if sha(Path(path)) != support_report[key]:
                raise SystemExit("SPU copy variant input changed: " + str(path))
    # libtool member names and contents must match the already checked objects.
    members = subprocess.check_output(["ar", "-t", str(support)], text=True).splitlines()
    if sorted(x for x in members if not x.startswith("__.SYMDEF")) != sorted(Path(x["object"]).name for x in support_report["units"]):
        raise SystemExit("Support archive inventory differs")
    for item in support_report["units"]:
        if hashlib.sha256(subprocess.check_output(["ar", "-p", str(support), Path(item["object"]).name])).hexdigest() != item["object_sha256"]:
            raise SystemExit("Support archive member changed")
    reference_support=output / "libbces_support_lighting_reference.a"
    shutil.copyfile(support,reference_support)
    if any(members.count(m)!=1 for m in (lighting_member,ssao_member,edge_member)): raise SystemExit("Reference member inventory differs")
    subprocess.run(["ar","-d",str(reference_support),lighting_member,ssao_member,edge_member],check=True)
    subprocess.run(["ranlib",str(reference_support)],check=True)
    support=reference_support
    runtime = next(p for p in archives if p.name == "libps3recomp_full_runtime.a")
    deps = [p for p in archives if p != runtime]
    # Recompile the Metal TU with explicit ARC and cellGame with the installed
    # directory-size stub fixed. Preserve the original verified archive.
    overlay = output / "renderer-overlay"
    subprocess.run([sys.executable, str(ROOT / "tools/prepare_renderer.py"),
                    "--source", str(port / "ps3recomp-fork"), "--output", str(overlay)], check=True)
    prepare_frame_diagnostics(output, port / "ps3recomp-fork", overlay / "libs/video/rsx_metal_backend.m")
    prepare_spu_dispatch(output,port / "ps3recomp-fork")
    channels=output / "diagnostic_spu_channels.c"
    put(channels,prepare_mfc_alignment(channels.read_text(),args.mfc_align128))
    if channel_inline:
        channels=output / "diagnostic_spu_channels.c"
        put(channels,prepare_channel_inline(channels.read_text()))
    if args.mfc_hint_experiment:
        channels=output / "diagnostic_spu_channels.c"
        put(channels,prepare_mfc_hint(channels.read_text()))
    if args.overlay_filter_experiment:
        channels=output / "diagnostic_spu_channels.c"
        put(channels,prepare_overlay_filter(channels.read_text()))
    dma_source=output / "diagnostic_spu_dma.h"
    put(dma_source,prepare_dma_poison(dma_source.read_text()))
    prepare_metal_lighting(output)
    prepare_metal_ssao(output,port)
    prepare_edge_renderer(overlay / "libs/video/rsx_draw_engine.c")
    prepare_renderer_memo(output,port / "ps3recomp-fork")
    ppu_loader = port / 'ps3recomp-fork/runtime/ppu/ppu_loader.cpp'
    if args.job_flow:
        loader = output / 'diagnostic_ppu_loader.cpp'
        put(loader, prepare_job_flow.loader(ppu_loader.read_text()))
        ppu_loader = loader
        for path, instrument in (
            (dma_source, prepare_job_flow.dma),
            (output / 'diagnostic_cellGcmSys.c', prepare_job_flow.fifo),
            (overlay / 'libs/video/rsx_draw_engine.c', prepare_job_flow.renderer),
        ):
            put(path, instrument(path.read_text()))
    metal_source=overlay / "libs/video/rsx_metal_backend.m"
    put(metal_source,prepare_interval_mask(prepare_lighting_far(metal_source.read_text()),capture_inputs=False))
    if args.half_depth_probe:
        loader = output / 'diagnostic_ppu_loader.cpp'
        put(loader, prepare_half_depth_probe.loader(ppu_loader.read_text()))
        ppu_loader = loader
        prepare_half_depth_probe.prepare(output, overlay)
    if args.gbuffer_fence:
        prepare_gbuffer_fence.prepare(overlay)
    if args.gbuffer_flow:
        prepare_gbuffer_flow.prepare(output, overlay)
    if args.renderer_stages:
        prepare_renderer_stages.prepare(output, overlay)
    if args.compact_vertex:
        prepare_compact_vertex.prepare(overlay)
    derived = output / "libps3recomp_game_runtime.a"
    members = subprocess.check_output(["ar", "-t", str(runtime)], text=True).splitlines()
    excluded = ["rsx_metal_backend.o", "rsx_shader_msl.o", "cellGame.o", "sys_ppu_thread.o", "spu_channels.o", "spu_drain.o", "cellGcmSys.o", "rsx_draw_engine.o"]
    if any(members.count(name) != 1 for name in excluded):
        raise SystemExit("Unexpected runtime replacement inventory")
    # Always derive afresh: no stale or unchecked cached member content.
    shutil.copyfile(runtime, derived)
    subprocess.run(["ar", "-d", str(derived), *excluded], check=True)
    subprocess.run(["ranlib", str(derived)], check=True)
    reduced = subprocess.check_output(["ar", "-t", str(derived)], text=True).splitlines()
    if sorted(reduced) != sorted(m for m in members if m not in excluded):
        raise SystemExit("Derived runtime member inventory differs")
    lines = [f'set(BCES_TITLE "{title}")', f'set(BCES_SUPPORT "{support}")', f'set(BCES_SUPPORT_VARIANT "{support_variant}")', f'set(BCES_RUNTIME "{derived}")',
             f'set(BCES_METAL_SOURCE "{overlay}/libs/video/rsx_metal_backend.m")',
             f'set(BCES_MSL_SOURCE "{overlay}/libs/video/rsx_shader_msl.cpp")', "set(BCES_DEPENDENCIES"]
    lines += [f'  "{p}"' for p in deps]
    lines += [")", ""]
    lines += ['set(BCES_CHANNEL_INLINE '+('ON' if channel_inline else 'OFF')+')']
    lines += ['set(BCES_CRITICAL_JOB_TRACE '+('ON' if critical_job else 'OFF')+')']
    lines += ['set(BCES_CRITICAL_WHOLE_JOBS '+('ON' if support_report.get('critical_job_whole_jobs') else 'OFF')+')']
    lines += ['set(BCES_CRITICAL_LOGICAL_JOBS '+('ON' if support_report.get('critical_job_logical_jobs') else 'OFF')+')']
    lines += [f'set(BCES_PPU_LOADER "{ppu_loader}")', f'set(BCES_JOB_FLOW {"ON" if args.job_flow else "OFF"})']
    lines += ['set(BCES_JOB_PHASES '+('ON' if support_report.get('critical_job_phases') else 'OFF')+')']
    lines += ['set(BCES_COMPACT_VERTEX '+('ON' if args.compact_vertex else 'OFF')+')']
    lines += [f'set(BCES_HALF_DEPTH_PROBE {"ON" if args.half_depth_probe else "OFF"})']
    lines += [f'set(BCES_GBUFFER_FENCE {"ON" if args.gbuffer_fence else "OFF"})']
    put(output / "dependencies.cmake", "\n".join(lines))
    source = port / "infamous2-lle/main.cpp"
    original = subprocess.check_output(["git", "-C", str(port), "show", "HEAD:infamous2-lle/main.cpp"], text=True)
    if source.read_text() != original:
        raise SystemExit("Pinned runner has local changes")
    text = '#include <TargetConditionals.h>\n#include "BCESIOS.h"\n#include "BCESGuestMemory.h"\n' + original
    changes = [
        ('vm_base = (uint8_t*)calloc(1, 0xE0000000u);', 'vm_base = bces_guest_memory_allocate();'),
        ("int main(int argc, char** argv)", 'extern "C" int bces_game_main(int argc, char** argv)'),
        ('    printf("=== ps3recomp game runner ===\\n");', '    setvbuf(stdout, NULL, _IONBF, 0);\n    printf("=== ps3recomp game runner iOS BCES ===\\n");'),
        ('#if defined(__APPLE__)\n    /* AppKit only runs', '#if defined(__APPLE__) && !TARGET_OS_IPHONE\n    /* AppKit only runs'),
        ('    for (;;) {\n        /* GCM_SEMA_FASTPOLL', '    for (;;) {\n        bces_ios_with_pool([&] {\n        BCESIOSFrameScope frame_scope;\n        /* GCM_SEMA_FASTPOLL'),
        ('                continue;\n            }\n            /* Present a flip', '                return;\n            }\n            /* Present a flip'),
        ('    }\n    return 0;\n}\n\n/* ---------------------------------------------------------------------------\n * VFS root', '        }); // per-iteration Objective-C autorelease pool\n    }\n    return 0;\n}\n\n/* ---------------------------------------------------------------------------\n * VFS root'),
    ]
    for before, after in changes:
        if text.count(before) != 1:
            raise SystemExit("Runner adaptation no longer matches: " + before[:60])
        text = text.replace(before, after, 1)
    put(output / "runner.cpp", text)
    thread_path = "runtime/syscalls/sys_ppu_thread.c"
    thread_original = (port / "ps3recomp-fork" / thread_path).read_text()
    expected_thread_sha = json.loads((ROOT / "sources.lock.json").read_text())["ios_ppu_host_stack"]["source_sha256"]
    if sha(port / "ps3recomp-fork" / thread_path) != expected_thread_sha:
        raise SystemExit("Patched pinned PPU thread source checksum differs")
    stack_define = "#define PPU_HOST_STACK_BYTES  (256u * 1024u * 1024u)"
    thread_entry = "    ppu_thread_info* info = (ppu_thread_info*)param;"
    if thread_original.count(stack_define) != 1 or thread_original.count(thread_entry) != 1:
        raise SystemExit("PPU host stack adaptation no longer matches")
    thread_text = '#include "HostStack.h"\n#include "FrameTrace.h"\n' + thread_original.replace(stack_define, "#define PPU_HOST_STACK_BYTES  (64u * 1024u * 1024u)")
    thread_text = thread_text.replace(thread_entry, "    bces_host_stack_register();\n" + thread_entry)
    thread_text = thread_text.replace(thread_entry, thread_entry + "\n    bces_frame_trace_register_ppu((uint32_t)(info-g_ppu_threads)+1u);")
    put(output / "ppu_thread.c", thread_text)
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    for hook in profile["spu_hooks"]:
        name = "gpu_" + hook["name"] + ".c"
        original_hook = subprocess.check_output(["git", "-C", str(port), "show", "HEAD:infamous2-lle/" + name], text=True)
        if (port / "infamous2-lle" / name).read_text() != original_hook:
            raise SystemExit("GPU source changed")
        macro = hook["name"].upper() + "_JOB_IMAGE"
        before, after = f'#define {macro} {hook["reference_image_id"]}', f'#define {macro} {hook["image_id"]}'
        if original_hook.count(before) != 1:
            raise SystemExit("GPU binding changed")
        hook_text=original_hook.replace(before, after, 1)
        if hook["name"]=="light":hook_text=prepare_metal_light_hook(hook_text)
        if hook["name"]=="ssao":hook_text=prepare_metal_ssao_hook(hook_text)
        put(output / name, hook_text)
    elf = ROOT / "data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf"
    if sha(elf) != profile["elf_sha256"]:
        raise SystemExit("BCES ELF identity mismatch")
    resources = output / "resources"
    resources.mkdir(exist_ok=True)
    if not (resources / "EBOOT.elf").exists() or sha(resources / "EBOOT.elf") != profile["elf_sha256"]:
        shutil.copyfile(elf, resources / "EBOOT.elf")
    inventory = {"profile": profile["name"], "elf_sha256": profile["elf_sha256"], "entries": []}
    for base, prefix in ((ROOT / "data/game/BCES01229", "PS3_GAME"),
                         (ROOT / "data/firmware/dev_flash", "dev_flash"),
                         (ROOT / "data/vfs/BCES01229/dev_hdd0", "dev_hdd0")):
        for file in sorted(base.rglob("*")):
            if not file.is_file():
                continue
            rel = str(Path(prefix) / file.relative_to(base))
            entry = {"path": rel, "bytes": file.stat().st_size}
            if rel == "PS3_GAME/PARAM.SFO": entry["sha256"] = profile["sfo_sha256"]
            if rel == "PS3_GAME/USRDIR/EBOOT.BIN": entry["sha256"] = profile["self_sha256"]
            inventory["entries"].append(entry)
    inventory["total_bytes"] = sum(e["bytes"] for e in inventory["entries"])
    put(resources / "bces-inputs.json", json.dumps(inventory, indent=2) + "\n")
    report = {"result": "PREPARED", "title": {"path": str(title), "sha256": sha(title)},
              "support": {"path": str(support), "sha256": sha(support), "variant": support_variant,
                          "report_sha256": sha(args.support_report)},
              "dependencies": [{"path": str(p), "sha256": sha(p)} for p in archives],
              "derived_runtime": {"path": str(derived), "sha256": sha(derived), "excluded_members": excluded, "storage_adapter_sha256": sha(ROOT / "src/game/BCESGameStorage.c")},
              "runner_sha256": sha(output / "runner.cpp"), "manifest_entries": len(inventory["entries"]),
              "transfer_bytes": inventory["total_bytes"], "synthetic_fixture_linked": False}
    put(ROOT / "out/step12-preparation.json", json.dumps(report, indent=2) + "\n")
    print(f"Prepared iPhoneOS real title + 83 support units; {len(archives)} verified iOS archives; {inventory['total_bytes']} asset bytes")


if __name__ == "__main__":
    main()
