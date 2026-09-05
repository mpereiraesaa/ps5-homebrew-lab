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
build="$root/build-stage-e-cpu"
dist="$root/dist-stage-e-cpu/PPSA99998"
main_source="$root/stage_e_cpu_main.cpp"
verify_cpu=1
if [[ ${1:-} == --smoke ]]; then
  build="$root/build-stage-e-smoke"
  dist="$root/dist-stage-e-smoke/PPSA99998"
  main_source="$root/stage_e_smoke_main.cpp"
  verify_cpu=0
elif [[ ${1:-} == --import-smoke ]]; then
  build="$root/build-stage-e-import-smoke"
  dist="$root/dist-stage-e-import-smoke/PPSA99998"
  main_source="$root/stage_e_import_smoke_main.cpp"
  verify_cpu=0
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--smoke|--import-smoke]" >&2
  exit 2
fi
driver_stub="$build/import-stubs/libSceAgcDriver.so"
agc_stub="$build/import-stubs/libSceAgc.so"
[[ -x $tool && -d $sdk ]] || exit 2
python3 "$project/research/gpu/tools/build_stage_e_shaders.py"
mkdir -p "$build/obj" "$build/import-stubs" "$dist/sce_sys" "$dist/sce_module"
cc=(env PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18")
common=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
"${cc[@]}" -std=c++20 "${common[@]}" -fno-exceptions -fno-rtti -I"$project" \
  -c "$main_source" -o "$build/obj/main.o"
"${cc[@]}" -std=c11 "${common[@]}" -I"$project" \
  -c "$project/legacy/probes/ps5-agc-phase0/stage_e_shader_header.c" -o "$build/obj/header.o"
(cd "$project" && "${cc[@]}" -c "$root/stage_e_assets.S" -o "$build/obj/assets.o")
"${cc[@]}" -std=c++20 "${common[@]}" -fno-exceptions -fno-rtti \
  -c "$native/app_crt.cpp" -o "$build/obj/app_crt.o"
"${cc[@]}" -std=c11 -O2 -fPIC \
  -I"$project/sdk/agc/include" -c "$project/sdk/agc/stubs/libSceAgcDriver_link_stub.c" \
  -o "$build/obj/driver-stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgcDriver.prx \
  -o "$driver_stub" "$build/obj/driver-stub.o"
"${cc[@]}" -std=c11 -O2 -fPIC \
  -I"$project/sdk/agc/include" -c "$project/sdk/agc/stubs/libSceAgc_link_stub.c" \
  -o "$build/obj/agc-stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgc.prx \
  -o "$agc_stub" "$build/obj/agc-stub.o"
"$sdk/bin/prospero-lld" -T "$native/ps5-pie.ld" --eh-frame-hdr \
  --version-script "$native/app-symbols.map" -e _start \
  -o "$build/llvm-pie.elf" "$build/obj/app_crt.o" "$build/obj/main.o" \
  "$build/obj/header.o" "$build/obj/assets.o" --as-needed \
  "$sdk"/target/lib/*.so "$agc_stub" "$driver_stub"
"$tool" link --in "$build/llvm-pie.elf" --out "$build/eboot.elf" \
  --stub-dir "$sdk/target/lib" --module-sdk 0x02000009 \
  --stub "$agc_stub" --stub "$driver_stub" \
  --companion-sdk 0x08050001 --file-name eboot.elf
"$tool" self --sign --in "$build/eboot.elf" --out "$dist/eboot.bin" \
  --magic 0x1D3D154F
cp "$root/sce_sys/param.json" "$dist/sce_sys/param.json"
cp "$reference/sce_sys/icon0.png" "$dist/sce_sys/icon0.png"
cp "$reference/runtime/libc.prx" "$dist/sce_module/libc.prx"
sha256sum "$build/eboot.elf" "$dist/eboot.bin"
"$tool" self --inspect --file "$dist/eboot.bin"
if [[ $verify_cpu -eq 1 ]]; then
  python3 "$root/verify_stage_e_cpu.py"
fi
