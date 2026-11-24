option(PROBE_BUILD_FULL_RUNTIME "Build the pinned complete runtime + synthetic PPU integration" ON)
if(NOT PROBE_BUILD_FULL_RUNTIME)
    return()
endif()

# Optional local support-code diagnostic. The title's PPU and assets are not
# linked here. Keep the synthetic runtime provider and the game target distinct.
set(BCES_SUPPORT_ARCHIVE "" CACHE FILEPATH "Local macOS BCES support archive for registration checks")
if(BCES_SUPPORT_ARCHIVE)
    if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
        message(FATAL_ERROR "BCES_SUPPORT_ARCHIVE diagnostic is macOS-only; never pass a macOS archive to iOS")
    endif()
    if(NOT EXISTS "${BCES_SUPPORT_ARCHIVE}")
        message(FATAL_ERROR "Generate the macOS BCES support archive first")
    endif()
    add_executable(bces_support_host src/host/bces_support_main.cpp)
    target_include_directories(bces_support_host PRIVATE "${PS3RECOMP_DIR}/runtime/prx" "${PS3RECOMP_DIR}/runtime/spu")
    target_link_libraries(bces_support_host PRIVATE full_runtime_boot)
    # Several registration TUs expose only constructors: normal archive search
    # would omit them. Force-load is essential for actual PRX/SPU registration.
    target_link_options(bces_support_host PRIVATE "LINKER:-force_load,${BCES_SUPPORT_ARCHIVE}")
    set_property(TARGET bces_support_host APPEND PROPERTY LINK_DEPENDS "${BCES_SUPPORT_ARCHIVE}")
    add_test(NAME bces_support_registration COMMAND bces_support_host)
endif()
if(NOT TARGET probe_shader_translation)
    message(FATAL_ERROR "Full runtime requires shader translation; for a clear-only build also set PROBE_BUILD_FULL_RUNTIME=OFF")
endif()
include("${CMAKE_CURRENT_LIST_DIR}/SDLDependency.cmake")

# Mirror the pinned SDK's HLE/core source rules. Do not use its dependency
# discovery/AppKit linkage on iOS, and do not discard unreferenced modules.
set(FULL_RUNTIME_SOURCES "")
foreach(part system filesystem input audio video network spurs sync codec font misc hardware)
    file(GLOB_RECURSE part_sources CONFIGURE_DEPENDS "${PS3RECOMP_DIR}/libs/${part}/*.c")
    list(APPEND FULL_RUNTIME_SOURCES ${part_sources})
endforeach()
file(GLOB_RECURSE core_sources CONFIGURE_DEPENDS "${PS3RECOMP_DIR}/runtime/*.c" "${PS3RECOMP_DIR}/runtime/*.cpp")
list(FILTER core_sources EXCLUDE REGEX "/tests/|/runtime/ppu/|/runtime/host/|/spu_dispatch_mt\\.c$")
list(APPEND FULL_RUNTIME_SOURCES ${core_sources})
list(REMOVE_DUPLICATES FULL_RUNTIME_SOURCES)
list(FILTER FULL_RUNTIME_SOURCES EXCLUDE REGEX "/tests/|rsx_vulkan_backend\\.c$")
file(GLOB at3_sources "${PS3RECOMP_DIR}/third_party/at3_standalone/*.cpp")
list(APPEND FULL_RUNTIME_SOURCES ${at3_sources} "${VIDEO}/rsx_shader_msl.cpp" "${VIDEO}/rsx_metal_backend.m")
foreach(name libs/video/rsx_metal_backend.m libs/video/rsx_draw_engine.c libs/video/rsx_shader_msl.cpp)
    list(REMOVE_ITEM FULL_RUNTIME_SOURCES "${PS3RECOMP_DIR}/${name}")
    list(APPEND FULL_RUNTIME_SOURCES "${RENDERER_OVERLAY}/${name}")
endforeach()
foreach(name runtime/platform/win32_compat.c libs/spurs/cellFiber.c)
    list(REMOVE_ITEM FULL_RUNTIME_SOURCES "${PS3RECOMP_DIR}/${name}")
    list(APPEND FULL_RUNTIME_SOURCES "${RUNTIME_OVERLAY}/${name}")
endforeach()
add_library(ps3recomp_full_runtime STATIC ${FULL_RUNTIME_SOURCES})
set_source_files_properties("${RENDERER_OVERLAY}/libs/video/rsx_metal_backend.m"
    PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
set_property(TARGET ps3recomp_full_runtime PROPERTY XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC YES)
target_include_directories(ps3recomp_full_runtime PUBLIC "${PS3RECOMP_DIR}/include" PRIVATE
    "${PS3RECOMP_DIR}/runtime/spu" "${PS3RECOMP_DIR}/runtime/platform" "${CMAKE_SOURCE_DIR}/src/platform")
foreach(part system filesystem input audio video network spurs sync codec font misc hardware)
    target_include_directories(ps3recomp_full_runtime PRIVATE "${PS3RECOMP_DIR}/libs/${part}")
endforeach()
target_compile_options(ps3recomp_full_runtime PRIVATE -fno-strict-aliasing -fwrapv -ffp-contract=off
    $<$<CONFIG:Release,RelWithDebInfo>:-O2> $<$<COMPILE_LANGUAGE:OBJC>:-fobjc-arc>)
target_link_libraries(ps3recomp_full_runtime PUBLIC SDL2::SDL2-static probe_shader_translation
    "-framework Metal" "-framework QuartzCore" "-framework Foundation")
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    target_compile_definitions(ps3recomp_full_runtime PRIVATE PS3RECOMP_IOS_FCONTEXT=1)
    target_link_libraries(ps3recomp_full_runtime PUBLIC ios_fiber_context)
else()
    target_link_libraries(ps3recomp_full_runtime PUBLIC "-framework AppKit")
endif()
list(LENGTH FULL_RUNTIME_SOURCES FULL_RUNTIME_SOURCE_COUNT)
message(STATUS "Complete pinned runtime: ${FULL_RUNTIME_SOURCE_COUNT} source files")

set(FULL_PROBE_GEN "${CMAKE_BINARY_DIR}/full-runtime-generated")
# Exercise the real offline PPC loader/lifter with original test instructions.
# The pinned Python tools use only the standard library on this path; the
# broader decryption/analysis requirements are not needed for this fixture.
find_program(AOT_PYTHON_EXECUTABLE NAMES python3.12
    HINTS "/Library/Frameworks/Python.framework/Versions/3.12/bin" REQUIRED)
set(AOT_PROBE_GEN "${FULL_PROBE_GEN}")
add_custom_command(OUTPUT "${AOT_PROBE_GEN}/lifted-probe.elf"
    "${AOT_PROBE_GEN}/lifted_ppu.h" "${AOT_PROBE_GEN}/lifted_ppu.cpp"
    COMMAND "${AOT_PYTHON_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/build_lifted_probe.py"
        --source "${PS3RECOMP_DIR}" --output "${AOT_PROBE_GEN}"
    DEPENDS "${CMAKE_SOURCE_DIR}/tools/build_lifted_probe.py"
        "${PS3RECOMP_DIR}/tools/ppu_loader.py" "${PS3RECOMP_DIR}/tools/ppu_lifter.py"
        "${PS3RECOMP_DIR}/tools/ppu_disasm.py" "${PS3RECOMP_DIR}/tools/elf_parser.py")
add_custom_command(OUTPUT "${FULL_PROBE_GEN}/synthetic.elf" "${FULL_PROBE_GEN}/ppu_recomp.h"
    COMMAND "${Python3_EXECUTABLE}" "${PS3RECOMP_DIR}/tools/make_smoke_elf.py"
        --out "${FULL_PROBE_GEN}/synthetic.elf" --header "${FULL_PROBE_GEN}/ppu_recomp.h"
    DEPENDS "${PS3RECOMP_DIR}/tools/make_smoke_elf.py" "${PS3RECOMP_DIR}/tools/ppu_lifter.py")
file(GLOB full_hle_inputs CONFIGURE_DEPENDS "${PS3RECOMP_DIR}/libs/*/*.c")
add_custom_command(OUTPUT "${FULL_PROBE_GEN}/ppu_hle_nids.cpp"
    COMMAND "${Python3_EXECUTABLE}" "${PS3RECOMP_DIR}/tools/gen_hle_nids.py"
        --out "${FULL_PROBE_GEN}/ppu_hle_nids.cpp" --all
    DEPENDS "${PS3RECOMP_DIR}/tools/gen_hle_nids.py" "${PS3RECOMP_DIR}/tools/nid_database.py" ${full_hle_inputs})
add_library(full_runtime_boot OBJECT src/full/FullRuntimeProbe.cpp src/full/LiftedPPUProbe.cpp
    "${AOT_PROBE_GEN}/lifted_ppu.cpp" "${AOT_PROBE_GEN}/lifted_ppu.h"
    src/full/RuntimeCoordinator.cpp src/platform/AppleWorkPool.m
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_loader.cpp" "${PS3RECOMP_DIR}/runtime/ppu/ppu_hle.cpp"
    "${PS3RECOMP_DIR}/runtime/ppu/ppu_fs.cpp" "${PS3RECOMP_DIR}/runtime/ppu/ppu_sysprx.cpp"
    "${PS3RECOMP_DIR}/runtime/spu/spu_dispatch_mt.c"
    "${FULL_PROBE_GEN}/ppu_recomp.h" "${FULL_PROBE_GEN}/ppu_hle_nids.cpp")
set_source_files_properties(src/platform/AppleWorkPool.m PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
target_include_directories(full_runtime_boot PUBLIC src/full PRIVATE "${FULL_PROBE_GEN}" "${AOT_PROBE_GEN}"
    "${PS3RECOMP_DIR}/include" "${PS3RECOMP_DIR}/runtime/ppu" "${PS3RECOMP_DIR}/runtime/spu"
    "${PS3RECOMP_DIR}/runtime/memory" "${PS3RECOMP_DIR}/runtime/syscalls"
    "${PS3RECOMP_DIR}/runtime/platform" "${PS3RECOMP_DIR}/libs/video")
target_include_directories(full_runtime_boot PUBLIC src/platform)
target_compile_options(full_runtime_boot PRIVATE -fno-strict-aliasing -fwrapv -ffp-contract=off -O1)
target_compile_options(full_runtime_boot PRIVATE $<$<COMPILE_LANGUAGE:OBJC>:-fobjc-arc>)
target_link_libraries(full_runtime_boot PUBLIC ps3recomp_full_runtime)
# Force the complete archive into the integration link: success must not be
# merely a static archive hiding unresolved references in unselected objects.
target_link_options(full_runtime_boot INTERFACE "LINKER:-force_load,$<TARGET_FILE:ps3recomp_full_runtime>")
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    set_source_files_properties("${FULL_PROBE_GEN}/synthetic.elf" PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
    set_source_files_properties("${AOT_PROBE_GEN}/lifted-probe.elf" PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
    add_executable(Infamous2FullRuntime MACOSX_BUNDLE src/ios/RuntimeApp.mm
        "${FULL_PROBE_GEN}/synthetic.elf" "${AOT_PROBE_GEN}/lifted-probe.elf" resources/ThirdPartyNotices.txt)
    target_compile_options(Infamous2FullRuntime PRIVATE -fobjc-arc)
    target_link_libraries(Infamous2FullRuntime PRIVATE full_runtime_boot "-framework UIKit")
    set_target_properties(Infamous2FullRuntime PROPERTIES
        MACOSX_BUNDLE_INFO_PLIST "${CMAKE_SOURCE_DIR}/src/ios/Info.plist"
        MACOSX_BUNDLE_GUI_IDENTIFIER "dev.infamous2.iosprobe"
        XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "dev.infamous2.iosprobe"
        XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1" XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
        XCODE_ATTRIBUTE_DEAD_CODE_STRIPPING "NO")
else()
    add_executable(full_runtime_host src/host/full_runtime_main.cpp)
    target_link_libraries(full_runtime_host PRIVATE full_runtime_boot)
    add_test(NAME complete_runtime_ppu_boot COMMAND full_runtime_host "${FULL_PROBE_GEN}/synthetic.elf")
    set_tests_properties(complete_runtime_ppu_boot PROPERTIES TIMEOUT 30)
    add_test(NAME complete_runtime_threaded COMMAND full_runtime_host "${FULL_PROBE_GEN}/synthetic.elf" --threaded)
    add_test(NAME complete_runtime_stop_paused COMMAND full_runtime_host "${FULL_PROBE_GEN}/synthetic.elf" --stop-paused)
    set_tests_properties(complete_runtime_threaded complete_runtime_stop_paused PROPERTIES TIMEOUT 30)
    add_executable(runtime_coordinator_tests src/host/coordinator_main.cpp src/full/RuntimeCoordinator.cpp src/platform/AppleWorkPool.m)
    target_include_directories(runtime_coordinator_tests PRIVATE src/full)
    target_compile_options(runtime_coordinator_tests PRIVATE $<$<COMPILE_LANGUAGE:OBJC>:-fobjc-arc>)
    target_link_libraries(runtime_coordinator_tests PRIVATE "-framework Foundation")
    add_test(NAME runtime_coordinator_stress COMMAND runtime_coordinator_tests)
    set_tests_properties(runtime_coordinator_stress PROPERTIES TIMEOUT 15)
endif()
