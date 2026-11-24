execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/tools/setup_sdl_sources.py" --verify-only
    COMMAND_ERROR_IS_FATAL ANY)
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_INSTALL OFF CACHE BOOL "" FORCE)
set(SDL2_DISABLE_SDL2MAIN ON CACHE BOOL "" FORCE)
# UIKit owns UIApplicationMain and Metal presentation. SDL supplies input/audio.
# Keep real platform backends available; no dummy driver is selected by tests.
add_subdirectory("${CMAKE_SOURCE_DIR}/upstream/platform-deps/SDL2" "platform-deps/SDL2" EXCLUDE_FROM_ALL)
