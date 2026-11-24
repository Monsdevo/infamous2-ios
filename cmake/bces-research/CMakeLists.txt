cmake_minimum_required(VERSION 3.24)
project(Infamous2Research LANGUAGES C CXX OBJC OBJCXX)
if(NOT APPLE OR CMAKE_SYSTEM_NAME STREQUAL "iOS")
 message(FATAL_ERROR "This autonomous research target requires macOS")
endif()
get_filename_component(ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(WORK "${ROOT}/build/bces01229")
set(PREPARED "${WORK}/host-research-prepared")
set(SDK "${ROOT}/upstream/infamous2-recomp/ps3recomp-fork")
include("${PREPARED}/dependencies.cmake")
set(CMAKE_C_STANDARD 17)
set(CMAKE_CXX_STANDARD 20)
add_executable(HostFrameOCR "${ROOT}/src/host/FrameOCR.m")
target_compile_options(HostFrameOCR PRIVATE -fobjc-arc)
target_link_libraries(HostFrameOCR PRIVATE "-framework Vision" "-framework Foundation")
add_executable(Infamous2Research
 "${ROOT}/src/host/ResearchMain.mm" "${ROOT}/src/host/BCESBootDiagnostics.cpp"
 "${PREPARED}/runner.cpp" "${PREPARED}/gpu_light.c" "${PREPARED}/gpu_ssao.c" "${PREPARED}/ssao_gpu.c"
 "${PREPARED}/lighting_spu_reference.c" "${PREPARED}/ssao_spu_reference.c"
 "${PREPARED}/host_spu_math.c" "${ROOT}/src/platform/HostSpuMath.c"
 "${PREPARED}/diagnostic_spu_channels.c" "${PREPARED}/diagnostic_spu_drain.c"
 "${PREPARED}/diagnostic_cellGcmSys.c" "${PREPARED}/ppu_thread.c"
 "${PREPARED}/renderer-overlay/libs/video/rsx_draw_engine.c"
 "${PREPARED}/renderer-overlay/libs/video/rsx_metal_backend.m"
 "${PREPARED}/renderer-overlay/libs/video/rsx_shader_msl.cpp"
 "${ROOT}/src/platform/SpuDispatchControl.c" "${ROOT}/src/platform/RSXLegacyFastPath.c"
 "${ROOT}/src/platform/SSAODepthBoundary.c" "${ROOT}/src/platform/MetalSSAO.c"
 "${ROOT}/src/platform/LightingValidation.mm" "${ROOT}/src/platform/GameTelemetry.cpp"
 "${ROOT}/src/platform/RendererMemo.c" "${ROOT}/src/platform/TextureHashMemo.c" "${ROOT}/src/platform/VertexFetchMemo.c"
 "${ROOT}/src/platform/CPUProfile.cpp" "${ROOT}/src/platform/FrameTrace.cpp" "${ROOT}/src/platform/ProgressTrace.cpp"
 "${ROOT}/src/platform/ShaderDiagnostics.cpp"
 "${ROOT}/src/platform/MetalPassProbe.m"
 "${ROOT}/src/platform/LightingFarReject.c"
 "${ROOT}/src/platform/HostDepthOnly.c"
 "${ROOT}/src/platform/HostNormalsWriteback.c"
 "${ROOT}/src/platform/HostIBCache.c"
 "${ROOT}/src/platform/DmaPoisonControl.c"
 "${ROOT}/src/platform/HostLightMask.c"
 "${ROOT}/src/platform/HostMaskCapture.m"
 "${ROOT}/src/platform/EdgeFlow.c" "${ROOT}/src/platform/HostStack.c" "${ROOT}/src/platform/AppleWorkPool.m"
 "${ROOT}/src/game/BCESRenderGate.cpp"
 "${SDK}/runtime/ppu/ppu_loader.cpp" "${SDK}/runtime/ppu/ppu_hle.cpp"
 "${SDK}/runtime/ppu/ppu_fs.cpp" "${SDK}/runtime/ppu/ppu_sysprx.cpp"
 "${SDK}/runtime/spu/spu_dispatch_mt.c" "${ROOT}/build/host/full-runtime-generated/ppu_hle_nids.cpp")
target_include_directories(Infamous2Research PRIVATE "${PREPARED}/trace-include" "${PREPARED}"
 "${ROOT}/src/platform" "${ROOT}/src/game" "${WORK}/recompiled"
 "${SDK}/include" "${SDK}/runtime/spu" "${SDK}/runtime/ppu" "${SDK}/runtime/syscalls"
 "${SDK}/runtime/platform" "${SDK}/runtime/prx" "${SDK}/runtime/memory"
 "${SDK}/libs/video" "${ROOT}/upstream/infamous2-recomp/infamous2-lle"
 "${ROOT}/upstream/platform-deps/SDL2/include" "${ROOT}/upstream/shader-deps/glslang" "${ROOT}/upstream/shader-deps/spirv-cross")
foreach(part system filesystem input audio video network spurs sync codec font misc hardware)
 target_include_directories(Infamous2Research PRIVATE "${SDK}/libs/${part}")
endforeach()
target_compile_options(Infamous2Research PRIVATE -O2 -fno-strict-aliasing -fwrapv -ffp-contract=off $<$<COMPILE_LANGUAGE:OBJC,OBJCXX>:-fobjc-arc>)
set_source_files_properties("${PREPARED}/lighting_spu_reference.c" PROPERTIES INCLUDE_DIRECTORIES "${WORK}/spu/jobmod_c6e7383dc013_e5400" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${PREPARED}/host_spu_math.c" PROPERTIES INCLUDE_DIRECTORIES "${WORK}/spu/jobmod_d0d15ec83992_ea2a0" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${PREPARED}/ssao_spu_reference.c" PROPERTIES INCLUDE_DIRECTORIES "${WORK}/spu/jobmod_e6fe749031f8_e2060" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${SDK}/runtime/spu/spu_dispatch_mt.c" PROPERTIES COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${PREPARED}/renderer-overlay/libs/video/rsx_shader_msl.cpp" PROPERTIES COMPILE_DEFINITIONS PS3RECOMP_HAVE_MSL_TRANSLATION=1)
foreach(a HOST_TITLE HOST_SUPPORT HOST_RUNTIME)
 target_link_options(Infamous2Research PRIVATE "LINKER:-force_load,${${a}}")
 set_property(TARGET Infamous2Research APPEND PROPERTY LINK_DEPENDS "${${a}}")
endforeach()
target_link_libraries(Infamous2Research PRIVATE ${HOST_DEPS}
 "-framework CoreVideo" "-framework Cocoa" "-framework IOKit" "-framework ForceFeedback"
 "-framework Carbon" "-framework CoreAudio" "-framework AudioToolbox" "-framework AVFoundation"
 "-framework Foundation" "-framework GameController" "-framework Metal" "-framework QuartzCore"
 "-framework CoreHaptics" "-framework AppKit")
