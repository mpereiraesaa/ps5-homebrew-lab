#!/usr/bin/env bash
set -euo pipefail

echo "deprecated: use build_stage_f.sh <f|g|h|i>; legacy filesystem telemetry is disabled" >&2
exit 2

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd -- "$root/../../.." && pwd)
reference="$project/third_party/ps5-native-app-boilerplate"
sdk="$reference/.deps/native/ps5-payload-sdk"
native="$reference/tooling/native"
tool="$reference/build/host/ps5-native-tool"
build="$root/build"
dist="$root/dist/PPSA99998"
agc_stub="$build/import-stubs/libSceAgc.so"

[[ -x $tool && -d $sdk ]] || {
    echo "Build the pinned native reference first: make -C $reference app" >&2
    exit 2
}

mkdir -p "$build/obj" "$dist/sce_sys" "$dist/sce_module"
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" \
    -std=c++20 -O2 -Wall -Wextra -Werror -fno-exceptions -fno-rtti \
    -ffunction-sections -fdata-sections -I"$project/include" \
    -c "$root/direct_main.cpp" -o "$build/obj/main.o"
(
    cd "$project"
    PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" \
        -c "$root/assets.S" -o "$build/obj/assets.o"
)
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" \
    -std=c++20 -O2 -Wall -Wextra -Werror -fno-exceptions -fno-rtti \
    -ffunction-sections -fdata-sections -c "$native/app_crt.cpp" -o "$build/obj/app_crt.o"

mkdir -p "$build/import-stubs"
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" \
    -std=c11 -O2 -fPIC -ffunction-sections -fdata-sections \
    -I"$project/sdk/agc/include" \
    -c "$project/sdk/agc/stubs/libSceAgc_link_stub.c" \
    -o "$build/obj/libSceAgc_link_stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgc.prx \
    -o "$agc_stub" "$build/obj/libSceAgc_link_stub.o"

"$sdk/bin/prospero-lld" -T "$native/ps5-pie.ld" --eh-frame-hdr \
    --version-script "$native/app-symbols.map" -e _start \
    -o "$build/llvm-pie.elf" "$build/obj/app_crt.o" "$build/obj/main.o" \
    "$build/obj/assets.o" \
    --as-needed "$sdk"/target/lib/*.so "$agc_stub"

"$tool" link --in "$build/llvm-pie.elf" --out "$build/eboot.elf" \
    --stub-dir "$sdk/target/lib" --module-sdk 0x02000009 \
    --stub "$agc_stub" --companion-sdk 0x08050001 --file-name eboot.elf
"$tool" self --sign --in "$build/eboot.elf" --out "$dist/eboot.bin" \
    --magic 0x1D3D154F

cp "$root/sce_sys/param.json" "$dist/sce_sys/param.json"
cp "$reference/sce_sys/icon0.png" "$dist/sce_sys/icon0.png"
cp "$reference/runtime/libc.prx" "$dist/sce_module/libc.prx"
"$tool" self --inspect --file "$dist/eboot.bin"
"$tool" self --inspect --file "$dist/sce_module/libc.prx"
python3 "$root/verify.py"
