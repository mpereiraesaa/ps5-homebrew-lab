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
build="$root/build-submit"
dist="$root/dist-submit/PPSA99998"
stub="$build/import-stubs/libSceAgcDriver.so"
agc_stub="$build/import-stubs/libSceAgc.so"
[[ -x $tool && -d $sdk ]] || exit 2
mkdir -p "$build/obj" "$build/import-stubs" "$dist/sce_sys" "$dist/sce_module"
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" -std=c++20 -O2 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections -c "$root/submit_main.cpp" -o "$build/obj/main.o"
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" -std=c++20 -O2 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -ffunction-sections -fdata-sections -c "$native/app_crt.cpp" -o "$build/obj/app_crt.o"
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" -std=c11 -O2 -fPIC -I"$project/sdk/agc/include" -c "$project/sdk/agc/stubs/libSceAgcDriver_link_stub.c" -o "$build/obj/driver-stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgcDriver.prx -o "$stub" "$build/obj/driver-stub.o"
PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18" -std=c11 -O2 -fPIC -I"$project/sdk/agc/include" -c "$project/sdk/agc/stubs/libSceAgc_link_stub.c" -o "$build/obj/agc-stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgc.prx -o "$agc_stub" "$build/obj/agc-stub.o"
"$sdk/bin/prospero-lld" -T "$native/ps5-pie.ld" --eh-frame-hdr --version-script "$native/app-symbols.map" -e _start -o "$build/llvm-pie.elf" "$build/obj/app_crt.o" "$build/obj/main.o" --as-needed "$sdk"/target/lib/*.so "$agc_stub" "$stub"
"$tool" link --in "$build/llvm-pie.elf" --out "$build/eboot.elf" --stub-dir "$sdk/target/lib" --module-sdk 0x02000009 --stub "$agc_stub" --stub "$stub" --companion-sdk 0x08050001 --file-name eboot.elf
"$tool" self --sign --in "$build/eboot.elf" --out "$dist/eboot.bin" --magic 0x1D3D154F
cp "$root/sce_sys/param.json" "$dist/sce_sys/param.json"
cp "$reference/sce_sys/icon0.png" "$dist/sce_sys/icon0.png"
cp "$reference/runtime/libc.prx" "$dist/sce_module/libc.prx"
python3 "$root/verify_submit.py"
