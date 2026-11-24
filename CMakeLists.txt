cmake_minimum_required(VERSION 3.24)
project(Infamous2IOSProbe LANGUAGES C CXX)
set(CMAKE_C_STANDARD 17)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(PS3RECOMP_DIR "${CMAKE_SOURCE_DIR}/upstream/infamous2-recomp/ps3recomp-fork" CACHE PATH "Pinned, patched runtime")
if(NOT EXISTS "${PS3RECOMP_DIR}/libs/video/rsx_texture_layout.c")
    message(FATAL_ERROR "Run tools/setup_sources.py first")
endif()

# Compile this platform-neutral renderer source for EACH target SDK.
# Do not discover Homebrew/macOS libraries in an iOS build.
add_library(rsx_texture_common STATIC "${PS3RECOMP_DIR}/libs/video/rsx_texture_layout.c")
target_include_directories(rsx_texture_common PUBLIC
    "${PS3RECOMP_DIR}/include" "${PS3RECOMP_DIR}/libs/video")
add_library(probe_common STATIC src/common/Probe.cpp)
target_include_directories(probe_common PUBLIC src/common)
target_link_libraries(probe_common PUBLIC rsx_texture_common)
target_compile_options(probe_common PRIVATE -Wall -Wextra -Werror -fno-strict-aliasing -ffp-contract=off)

find_package(Python3 COMPONENTS Interpreter REQUIRED)
include(cmake/ShaderDependencies.cmake)
set(RENDERER_OVERLAY "${CMAKE_BINARY_DIR}/renderer-overlay")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_SOURCE_DIR}/sources.lock.json"
    "${CMAKE_SOURCE_DIR}/patches/ios-metal-surface.patch"
    "${CMAKE_SOURCE_DIR}/tools/prepare_renderer.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/prepare_renderer.py"
    --source "${PS3RECOMP_DIR}" --output "${RENDERER_OVERLAY}"
    COMMAND_ERROR_IS_FATAL ANY)
set(RUNTIME_OVERLAY "${CMAKE_BINARY_DIR}/runtime-overlay")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_SOURCE_DIR}/patches/ios-runtime-vm.patch"
    "${CMAKE_SOURCE_DIR}/tools/prepare_runtime.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/prepare_runtime.py"
    --source "${PS3RECOMP_DIR}" --output "${RUNTIME_OVERLAY}"
    COMMAND_ERROR_IS_FATAL ANY)
add_library(runtime_platform STATIC "${RUNTIME_OVERLAY}/runtime/platform/win32_compat.c")
target_include_directories(runtime_platform PUBLIC "${PS3RECOMP_DIR}/runtime/platform")
# Synthetic fixture hooks stay out of future game targets. The verified
# cellFiber overlay selects the iOS mechanism while preserving macOS.
if(APPLE AND (CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64" OR CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"))
    enable_language(ASM)
    execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/setup_context_sources.py" --verify-only
        COMMAND_ERROR_IS_FATAL ANY)
    set(FCONTEXT_SOURCE "${CMAKE_SOURCE_DIR}/upstream/context-deps/boost-context/src/asm")
    add_library(ios_fiber_context STATIC src/platform/IOSFiberContext.c
        "${FCONTEXT_SOURCE}/make_arm64_aapcs_macho_gas.S"
        "${FCONTEXT_SOURCE}/jump_arm64_aapcs_macho_gas.S")
    target_include_directories(ios_fiber_context PUBLIC src/platform)
endif()
function(add_runtime_fixture target use_fcontext)
    add_library(${target} STATIC src/common/RuntimeProbe.c src/common/RuntimeProbeMemory.c src/common/ContextSupport.c
        "${RUNTIME_OVERLAY}/libs/spurs/cellFiber.c")
    target_include_directories(${target} PUBLIC src/common PRIVATE
        "${PS3RECOMP_DIR}/include" "${PS3RECOMP_DIR}/libs/spurs")
    target_compile_definitions(${target} PRIVATE vm_base=runtime_probe_vm_base)
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wno-deprecated-declarations
        -fno-strict-aliasing -fwrapv -ffp-contract=off)
    target_link_libraries(${target} PUBLIC runtime_platform)
    if(use_fcontext)
        target_compile_definitions(${target} PRIVATE PS3RECOMP_IOS_FCONTEXT=1)
        target_link_libraries(${target} PUBLIC ios_fiber_context)
    endif()
endfunction()
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    if(NOT TARGET ios_fiber_context)
        message(FATAL_ERROR "iOS fiber adapter currently requires Apple arm64")
    endif()
    add_runtime_fixture(runtime_probe_fixture TRUE)
else()
    add_runtime_fixture(runtime_probe_fixture FALSE)
endif()
set(VIDEO "${PS3RECOMP_DIR}/libs/video")
add_library(rsx_core STATIC
    "${RENDERER_OVERLAY}/libs/video/rsx_draw_engine.c"
    "${VIDEO}/rsx_dispatch.c" "${VIDEO}/rsx_commands.c"
    "${VIDEO}/rsx_vertex_fetch.c" "${VIDEO}/rsx_vertex_compact.c" "${VIDEO}/rsx_fp_decompiler.c"
    "${VIDEO}/rsx_vp_decompiler.c" "${RENDERER_OVERLAY}/libs/video/rsx_shader_msl.cpp"
    "${PS3RECOMP_DIR}/runtime/milestone.c")
target_link_libraries(rsx_core PUBLIC rsx_texture_common)
if(PROBE_ENABLE_SHADER_TRANSLATION)
    target_link_libraries(rsx_core PUBLIC probe_shader_translation)
endif()
target_compile_options(rsx_core PRIVATE -fno-strict-aliasing -fwrapv -ffp-contract=off)
add_library(rsx_diag_clock STATIC src/common/RendererClock.c)
if(APPLE)
    enable_language(OBJC)
    add_library(rsx_metal STATIC "${RENDERER_OVERLAY}/libs/video/rsx_metal_backend.m")
    target_compile_options(rsx_metal PRIVATE -fobjc-arc)
    target_include_directories(rsx_metal PUBLIC src/platform)
    target_link_libraries(rsx_metal PUBLIC rsx_core
        "-framework Metal" "-framework QuartzCore" "-framework Foundation")
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
        target_link_libraries(rsx_metal PUBLIC "-framework AppKit")
    endif()
    # A synthetic guest memory / cellGcm fixture, NEVER a substitute for the
    # game's real HLE/LLE loader or IO mapping. No SDL or host shader archives.
    add_library(rsx_smoke_fixture STATIC src/common/RSXSmoke.c)
    target_include_directories(rsx_smoke_fixture PUBLIC src/common)
    target_link_libraries(rsx_smoke_fixture PUBLIC rsx_metal rsx_diag_clock)
endif()

if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/src/ios/Info.plist")
    enable_language(OBJCXX)
    set_source_files_properties(resources/ThirdPartyNotices.txt PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
    add_executable(Infamous2Probe MACOSX_BUNDLE src/ios/App.mm resources/ThirdPartyNotices.txt)
    target_compile_options(Infamous2Probe PRIVATE -fobjc-arc -Wall -Wextra)
    target_link_libraries(Infamous2Probe PRIVATE rsx_smoke_fixture runtime_probe_fixture
        "-framework UIKit" "-framework Metal"
        "-framework Foundation" "-framework QuartzCore" "-framework CoreGraphics")
    set_target_properties(Infamous2Probe PROPERTIES
        MACOSX_BUNDLE_INFO_PLIST "${CMAKE_SOURCE_DIR}/src/ios/Info.plist"
        MACOSX_BUNDLE_GUI_IDENTIFIER "dev.infamous2.iosprobe"
        XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "dev.infamous2.iosprobe"
        XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1"
        XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
        XCODE_ATTRIBUTE_ENABLE_USER_SCRIPT_SANDBOXING "YES")
else()
    add_executable(probe_host src/host/main.cpp)
    target_link_libraries(probe_host PRIVATE probe_common)
    add_executable(rsx_texture_tests "${PS3RECOMP_DIR}/libs/video/tests/test_texture_layout.c")
    target_link_libraries(rsx_texture_tests PRIVATE rsx_texture_common)
    enable_testing()
    add_test(NAME upstream_rsx_texture COMMAND rsx_texture_tests)
    add_test(NAME memory_thread_probe COMMAND probe_host)
    add_executable(runtime_host src/host/runtime_main.c)
    target_link_libraries(runtime_host PRIVATE runtime_probe_fixture)
    add_test(NAME runtime_vm_thread_fiber COMMAND runtime_host)
    set_tests_properties(runtime_vm_thread_fiber PROPERTIES TIMEOUT 30)
    if(TARGET ios_fiber_context)
        add_runtime_fixture(runtime_fcontext_fixture TRUE)
        add_executable(runtime_fcontext_host src/host/runtime_main.c)
        target_link_libraries(runtime_fcontext_host PRIVATE runtime_fcontext_fixture)
        add_test(NAME runtime_ios_fcontext_on_host COMMAND runtime_fcontext_host)
        set_tests_properties(runtime_ios_fcontext_on_host PROPERTIES TIMEOUT 30)
    endif()
    if(APPLE)
        add_executable(renderer_host src/host/renderer_main.c)
        target_link_libraries(renderer_host PRIVATE rsx_smoke_fixture)
        set_target_properties(renderer_host PROPERTIES LINKER_LANGUAGE CXX)
        add_test(NAME rsx_metal_headless COMMAND renderer_host)
        if(PROBE_ENABLE_SHADER_TRANSLATION)
            add_test(NAME rsx_guest_shader_rejection COMMAND renderer_host --expect-shader-rejection)
        endif()
        add_executable(rsx_engine_tests "${VIDEO}/tests/test_rsx_draw_engine.c")
        target_link_libraries(rsx_engine_tests PRIVATE rsx_core rsx_diag_clock)
        set_target_properties(rsx_engine_tests PROPERTIES LINKER_LANGUAGE CXX)
        add_executable(rsx_engine_tests_baseline "${VIDEO}/tests/test_rsx_draw_engine.c"
            "${VIDEO}/rsx_draw_engine.c")
        target_link_libraries(rsx_engine_tests_baseline PRIVATE rsx_core rsx_diag_clock)
        target_compile_options(rsx_engine_tests_baseline PRIVATE -fno-strict-aliasing -fwrapv -ffp-contract=off)
        set_target_properties(rsx_engine_tests_baseline PROPERTIES LINKER_LANGUAGE CXX)
        add_test(NAME rsx_engine_regression COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_SOURCE_DIR}/tools/check_renderer_regression.py"
            "$<TARGET_FILE:rsx_engine_tests_baseline>" "$<TARGET_FILE:rsx_engine_tests>")
        if(PROBE_ENABLE_SHADER_TRANSLATION)
            add_executable(shader_translation_tests "${VIDEO}/tests/test_shader_msl.c")
            target_link_libraries(shader_translation_tests PRIVATE rsx_core)
            set_target_properties(shader_translation_tests PROPERTIES LINKER_LANGUAGE CXX)
            add_test(NAME upstream_shader_translation COMMAND shader_translation_tests)
        endif()
    endif()
endif()

include(cmake/FullRuntime.cmake)
