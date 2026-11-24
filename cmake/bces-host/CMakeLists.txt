cmake_minimum_required(VERSION 3.24)
project(Infamous2BCESHost LANGUAGES C CXX)
if(NOT APPLE OR CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "This reference target is macOS-only; its archives must never enter an iOS link")
endif()
get_filename_component(PORT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(WORK "${PORT_ROOT}/build/bces01229")
set(SDK "${PORT_ROOT}/upstream/infamous2-recomp/ps3recomp-fork")
set(TITLE "${WORK}/title")
include("${WORK}/host-dependencies.cmake")
set(CMAKE_C_STANDARD 17)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
file(GLOB PPU CONFIGURE_DEPENDS "${WORK}/recompiled/ppu_recomp_*.cpp")
list(LENGTH PPU COUNT)
if(NOT COUNT EQUAL 164)
    message(FATAL_ERROR "Expected the complete 164-chunk BCES lift")
endif()
add_executable(Infamous2BCES
    ${PPU} "${TITLE}/main.cpp" "${TITLE}/gpu_light.c" "${TITLE}/gpu_ssao.c" "${TITLE}/ssao_gpu.c"
    "${PORT_ROOT}/src/host/BCESBootDiagnostics.cpp"
    "${SDK}/runtime/ppu/ppu_loader.cpp" "${SDK}/runtime/ppu/ppu_hle.cpp"
    "${SDK}/runtime/ppu/ppu_fs.cpp" "${SDK}/runtime/ppu/ppu_sysprx.cpp"
    "${SDK}/runtime/spu/spu_dispatch_mt.c"
    "${PORT_ROOT}/build/host/full-runtime-generated/ppu_hle_nids.cpp")
target_include_directories(Infamous2BCES PRIVATE
    "${WORK}/recompiled" "${SDK}/include" "${SDK}/runtime/ppu" "${SDK}/runtime/spu"
    "${SDK}/runtime/memory" "${SDK}/runtime/syscalls" "${SDK}/runtime/prx" "${SDK}/runtime/platform"
    "${SDK}/libs/video" "${PORT_ROOT}/upstream/infamous2-recomp/infamous2-lle")
target_compile_options(Infamous2BCES PRIVATE -O1 -fno-strict-aliasing -fwrapv -ffp-contract=off)
set_source_files_properties(${PPU} PROPERTIES COMPILE_OPTIONS "-w")
set_source_files_properties("${SDK}/runtime/spu/spu_dispatch_mt.c" PROPERTIES COMPILE_DEFINITIONS SPU_USE_DISPATCH_MT)
target_link_options(Infamous2BCES PRIVATE "LINKER:-force_load,${BCES_SUPPORT}" "LINKER:-force_load,${BCES_RUNTIME}")
set_property(TARGET Infamous2BCES APPEND PROPERTY LINK_DEPENDS "${BCES_SUPPORT}" "${BCES_RUNTIME}" ${BCES_DEPENDENCIES})
target_link_libraries(Infamous2BCES PRIVATE ${BCES_DEPENDENCIES}
    "-framework CoreVideo" "-framework Cocoa" "-framework IOKit" "-framework ForceFeedback"
    "-framework Carbon" "-framework CoreAudio" "-framework AudioToolbox" "-framework AVFoundation"
    "-framework Foundation" "-framework GameController" "-framework Metal" "-framework QuartzCore"
    "-framework CoreHaptics" "-framework AppKit")
message(STATUS "Real BCES game target: ${COUNT} PPU chunks; all writes/build outputs on monssd")
