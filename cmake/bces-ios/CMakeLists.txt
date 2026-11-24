cmake_minimum_required(VERSION 3.24)
project(Infamous2BCESIOS LANGUAGES C CXX OBJC OBJCXX)
option(BCES_TRACE_NEW_FAILURES "Diagnostic operator new allocation-failure tracing" OFF)
option(BCES_EXTENDED_VA "Request Extended Virtual Addressing (requires a supported signing team)" OFF)
option(BCES_DMA_ORIGINAL_SCAN "Compile original DMA scan without per-transfer experiment controls/counters" OFF)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "Configure with the iPhoneOS SDK; host archives are forbidden")
endif()
get_filename_component(PORT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(WORK "${PORT_ROOT}/build/bces01229")
set(PREPARED "${WORK}/ios-prepared")
set(SDK "${PORT_ROOT}/upstream/infamous2-recomp/ps3recomp-fork")
include("${PREPARED}/dependencies.cmake")
if(NOT BCES_PPU_LOADER)
    set(BCES_PPU_LOADER "${SDK}/runtime/ppu/ppu_loader.cpp")
endif()
set(CMAKE_C_STANDARD 17)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(RESOURCES "${PREPARED}/resources/EBOOT.elf" "${PREPARED}/resources/bces-inputs.json" "${PORT_ROOT}/resources/ThirdPartyNotices.txt")
set_source_files_properties(${RESOURCES} "${PORT_ROOT}/resources/GameAssets.xcassets" PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
add_executable(Infamous2Game MACOSX_BUNDLE
    "${PORT_ROOT}/src/ios/GamePerformance.mm" "${PORT_ROOT}/src/ios/GameApp.mm" "${PORT_ROOT}/src/game/BCESIOS.cpp"
    "${PORT_ROOT}/src/platform/GameTelemetry.cpp"
    "${PORT_ROOT}/src/platform/LightingFarReject.c"
    "${PORT_ROOT}/src/platform/HostLightMask.c"
    "${PORT_ROOT}/src/platform/DmaPoisonControl.c"
    "${PORT_ROOT}/src/platform/MfcHintControl.c"
    "${PORT_ROOT}/src/platform/OverlayFilterControl.c"
    "${PORT_ROOT}/src/platform/SpuChannelControl.c"
    "${PORT_ROOT}/src/platform/RSXLegacyFastPath.c"
    "${PORT_ROOT}/src/platform/RendererMemo.c" "${PORT_ROOT}/src/platform/TextureHashMemo.c"
    "${PORT_ROOT}/src/platform/VertexFetchMemo.c"
    "${PORT_ROOT}/src/game/BCESRenderGate.cpp"
    "${PORT_ROOT}/src/game/BCESGameStorage.c"
    "${PORT_ROOT}/src/platform/AppleWorkPool.m"
    "${PORT_ROOT}/src/platform/ShaderDiagnostics.cpp"
    "${PORT_ROOT}/src/platform/HostStack.c"
    "${PORT_ROOT}/src/platform/CPUProfile.cpp"
    "${PORT_ROOT}/src/platform/FrameTrace.cpp"
    "${PORT_ROOT}/src/platform/CriticalJobTrace.c"
    "${PORT_ROOT}/src/platform/CompactVertex.c"
    "${PORT_ROOT}/src/platform/ProgressTrace.cpp"
    "${PORT_ROOT}/src/platform/SpuDispatchControl.c" "${PREPARED}/diagnostic_spu_drain.c"
    "${PORT_ROOT}/src/platform/LightingValidation.mm" "${PREPARED}/lighting_spu_reference.c"
    "${PREPARED}/ssao_spu_reference.c" "${PORT_ROOT}/src/platform/SSAODepthBoundary.c"
    "${PREPARED}/edge_geometry.c" "${PORT_ROOT}/src/platform/EdgeGeometry.c"
    "${PORT_ROOT}/src/platform/EdgeFlow.c"
    "${PORT_ROOT}/src/platform/SkinningCapture.c"
    "${PORT_ROOT}/src/platform/GeometryKernels.mm" "${PORT_ROOT}/src/platform/GeometryMetalBatches.mm" "${PORT_ROOT}/src/platform/GeometryControl.mm" "${PORT_ROOT}/src/platform/GeometryMathProbe.c"
    "${WORK}/skinning/geometry_execute.c" "${WORK}/skinning/geometry_batches.c"
    "${PREPARED}/diagnostic_spu_channels.c" "${PREPARED}/diagnostic_cellGcmSys.c"
    "${PREPARED}/ppu_thread.c"
    "${BCES_MSL_SOURCE}"
    "${PREPARED}/renderer-overlay/libs/video/rsx_draw_engine.c"
    "${BCES_METAL_SOURCE}"
    "${PREPARED}/runner.cpp" "${PREPARED}/gpu_light.c" "${PREPARED}/gpu_ssao.c"
    "${PREPARED}/ssao_gpu.c" "${PORT_ROOT}/src/platform/MetalSSAO.c"
    "${BCES_PPU_LOADER}" "${SDK}/runtime/ppu/ppu_hle.cpp"
    "${SDK}/runtime/ppu/ppu_fs.cpp" "${SDK}/runtime/ppu/ppu_sysprx.cpp"
    "${SDK}/runtime/spu/spu_dispatch_mt.c"
    "${PORT_ROOT}/build/ios/full-runtime-generated/ppu_hle_nids.cpp" ${RESOURCES} "${PORT_ROOT}/resources/GameAssets.xcassets")
target_include_directories(Infamous2Game PRIVATE
    "${PREPARED}"
    "${WORK}/skinning"
    "${PREPARED}/trace-include"
    "${WORK}/recompiled" "${PORT_ROOT}/src/game" "${PORT_ROOT}/src/platform"
    "${PORT_ROOT}/upstream/platform-deps/SDL2/include"
    "${PORT_ROOT}/upstream/shader-deps/glslang" "${PORT_ROOT}/upstream/shader-deps/spirv-cross"
    "${SDK}/include" "${SDK}/runtime/ppu" "${SDK}/runtime/spu"
    "${SDK}/runtime/memory" "${SDK}/runtime/syscalls" "${SDK}/runtime/prx" "${SDK}/runtime/platform"
    "${SDK}/libs/video" "${PORT_ROOT}/upstream/infamous2-recomp/infamous2-lle")
target_compile_options(Infamous2Game PRIVATE -O1 -fno-strict-aliasing -fwrapv -ffp-contract=off
    $<$<COMPILE_LANGUAGE:OBJC,OBJCXX>:-fobjc-arc>)
target_compile_definitions(Infamous2Game PRIVATE BCES_SUPPORT_VARIANT="${BCES_SUPPORT_VARIANT}")
target_compile_definitions(Infamous2Game PRIVATE BCES_CRITICAL_JOB_TRACE=$<BOOL:${BCES_CRITICAL_JOB_TRACE}>)
target_compile_definitions(Infamous2Game PRIVATE BCES_CRITICAL_WHOLE_JOBS=$<BOOL:${BCES_CRITICAL_WHOLE_JOBS}>)
target_compile_definitions(Infamous2Game PRIVATE BCES_CRITICAL_LOGICAL_JOBS=$<BOOL:${BCES_CRITICAL_LOGICAL_JOBS}>)
target_compile_definitions(Infamous2Game PRIVATE BCES_JOB_FLOW=$<BOOL:${BCES_JOB_FLOW}>)
target_compile_definitions(Infamous2Game PRIVATE BCES_JOB_PHASES=$<BOOL:${BCES_JOB_PHASES}>)
if(BCES_GBUFFER_FENCE)
    target_compile_definitions(Infamous2Game PRIVATE BCES_GBUFFER_FENCE=1)
endif()
if(BCES_HALF_DEPTH_PROBE)
    target_sources(Infamous2Game PRIVATE "${PORT_ROOT}/src/platform/HalfDepthProbe.c")
    target_compile_definitions(Infamous2Game PRIVATE BCES_HALF_DEPTH_PROBE=1)
endif()
target_compile_definitions(Infamous2Game PRIVATE BCES_COMPACT_VERTEX=$<BOOL:${BCES_COMPACT_VERTEX}>)
set_source_files_properties("${PORT_ROOT}/src/platform/CompactVertex.c" PROPERTIES COMPILE_OPTIONS "-O2")
target_compile_definitions(Infamous2Game PRIVATE BCES_TRACE_NEW_FAILURES=$<BOOL:${BCES_TRACE_NEW_FAILURES}>)
set_source_files_properties("${BCES_MSL_SOURCE}" PROPERTIES COMPILE_DEFINITIONS PS3RECOMP_HAVE_MSL_TRANSLATION=1 COMPILE_OPTIONS "-O2")
set_source_files_properties("${PREPARED}/ppu_thread.c" PROPERTIES COMPILE_OPTIONS "-O2")
set_source_files_properties("${PORT_ROOT}/src/platform/RSXLegacyFastPath.c" PROPERTIES COMPILE_OPTIONS "-O2")
set_source_files_properties("${PORT_ROOT}/src/platform/CPUProfile.cpp" PROPERTIES COMPILE_OPTIONS "-O2")
set_source_files_properties("${PORT_ROOT}/src/platform/CriticalJobTrace.c" PROPERTIES COMPILE_OPTIONS "-O2")
set_source_files_properties("${PREPARED}/diagnostic_spu_channels.c" "${PREPARED}/diagnostic_spu_drain.c" "${PREPARED}/diagnostic_cellGcmSys.c"
    PROPERTIES COMPILE_OPTIONS "-O2" COMPILE_DEFINITIONS PS3RECOMP_IOS_FCONTEXT=1)
set_source_files_properties("${PREPARED}/lighting_spu_reference.c" PROPERTIES INCLUDE_DIRECTORIES "${WORK}/spu/jobmod_c6e7383dc013_e5400" COMPILE_OPTIONS "-O2" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${PREPARED}/ssao_spu_reference.c" PROPERTIES INCLUDE_DIRECTORIES "${WORK}/spu/jobmod_e6fe749031f8_e2060" COMPILE_OPTIONS "-O2" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${PREPARED}/edge_geometry.c" PROPERTIES INCLUDE_DIRECTORIES "${WORK}/spu/jobmod_d0d15ec83992_ea2a0" COMPILE_OPTIONS "-O2" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${WORK}/skinning/geometry_execute.c" "${WORK}/skinning/geometry_batches.c" PROPERTIES COMPILE_OPTIONS "-O2" COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
set_source_files_properties("${PORT_ROOT}/src/platform/GeometryKernels.mm" "${PORT_ROOT}/src/platform/GeometryMetalBatches.mm" "${PORT_ROOT}/src/platform/GeometryControl.mm" PROPERTIES COMPILE_OPTIONS "-fobjc-arc;-O2")
set_source_files_properties("${PORT_ROOT}/src/platform/LightingValidation.mm" PROPERTIES COMPILE_OPTIONS "-fobjc-arc;-O2")
set_source_files_properties("${PREPARED}/renderer-overlay/libs/video/rsx_draw_engine.c" PROPERTIES COMPILE_OPTIONS "-O2")
set_source_files_properties("${PORT_ROOT}/src/platform/RendererMemo.c" "${PORT_ROOT}/src/platform/TextureHashMemo.c" "${PORT_ROOT}/src/platform/VertexFetchMemo.c" PROPERTIES COMPILE_OPTIONS "-O2")
foreach(part system filesystem input audio video network spurs sync codec font misc hardware)
    target_include_directories(Infamous2Game PRIVATE "${SDK}/libs/${part}")
endforeach()
if(BCES_SUPPORT_VARIANT STREQUAL "spu-O2-copy")
    target_sources(Infamous2Game PRIVATE "${PORT_ROOT}/src/game/BCESSpuCopy.c")
    target_compile_definitions(Infamous2Game PRIVATE BCES_SPU_COPY_ENABLED=1)
    set_source_files_properties("${PORT_ROOT}/src/game/BCESSpuCopy.c" PROPERTIES COMPILE_OPTIONS "-O2")
endif()
# Xcode evaluates mixed-language target options using its CXX settings.
# Set ARC on the actual Objective-C sources, not only a language expression.
set_source_files_properties("${PORT_ROOT}/src/ios/GamePerformance.mm" "${PORT_ROOT}/src/ios/GameApp.mm" "${PORT_ROOT}/src/platform/AppleWorkPool.m"
    PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
set_source_files_properties("${BCES_METAL_SOURCE}" PROPERTIES COMPILE_OPTIONS "-fobjc-arc;-O2")
set_source_files_properties("${SDK}/runtime/spu/spu_dispatch_mt.c" PROPERTIES COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
foreach(archive BCES_TITLE BCES_SUPPORT BCES_RUNTIME)
    target_link_options(Infamous2Game PRIVATE "LINKER:-force_load,${${archive}}")
    set_property(TARGET Infamous2Game APPEND PROPERTY LINK_DEPENDS "${${archive}}")
endforeach()
if(BCES_DMA_ORIGINAL_SCAN)
    set_property(SOURCE "${PREPARED}/diagnostic_spu_channels.c" "${PORT_ROOT}/src/platform/DmaPoisonControl.c" "${PORT_ROOT}/src/ios/GameApp.mm"
        APPEND PROPERTY COMPILE_DEFINITIONS BCES_DMA_ORIGINAL_SCAN=1)
endif()
target_link_libraries(Infamous2Game PRIVATE ${BCES_DEPENDENCIES}
    "-framework UIKit" "-framework Metal" "-framework QuartzCore" "-framework Foundation"
    "-framework GameController" "-framework CoreBluetooth" "-framework CoreHaptics" "-framework CoreMotion"
    "-framework AVFoundation" "-framework AudioToolbox" "-framework CoreAudio"
    "-framework CoreGraphics" "-framework CoreVideo" "-framework OpenGLES")
set_target_properties(Infamous2Game PROPERTIES
    MACOSX_BUNDLE_INFO_PLIST "${PORT_ROOT}/src/ios/GameInfo.plist"
    MACOSX_BUNDLE_GUI_IDENTIFIER "dev.infamous2.iosprobe"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "dev.infamous2.iosprobe"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1" XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
    XCODE_ATTRIBUTE_DEAD_CODE_STRIPPING "NO" XCODE_ATTRIBUTE_ENABLE_BITCODE "NO"
    XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES"
    XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon")
if(BCES_EXTENDED_VA)
    set_target_properties(Infamous2Game PROPERTIES
        XCODE_ATTRIBUTE_CODE_SIGN_ENTITLEMENTS "${PORT_ROOT}/src/ios/GameEntitlements.plist")
endif()
