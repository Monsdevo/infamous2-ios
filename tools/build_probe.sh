#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
case "${1:-host}" in
    host)
        cmake -S . -B build/host -G Ninja -DCMAKE_BUILD_TYPE=Release
        cmake --build build/host --parallel 2
        ctest --test-dir build/host --output-on-failure
        ;;
    ios|simulator)
        target="$1"
        sdk=iphoneos
        [ "$target" != simulator ] || sdk=iphonesimulator
        cmake -S . -B "build/$target" -G Xcode \
            -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT="$sdk" \
            -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 \
            -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO
        cmake --build "build/$target" --config Release --parallel 2
        ;;
    *) echo "Usage: $0 host|ios|simulator" >&2; exit 2 ;;
esac
