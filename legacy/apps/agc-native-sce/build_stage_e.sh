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
stage="$project/legacy/probes/ps5-agc-phase0"
build="$root/build-stage-e"
dist="$root/dist-stage-e/PPSA99998"
driver_stub="$build/import-stubs/libSceAgcDriver.so"
agc_stub="$build/import-stubs/libSceAgc.so"
[[ -x $tool && -d $sdk ]] || exit 2
python3 "$project/research/gpu/tools/build_stage_e_gfx1013.py"
python3 "$project/research/gpu/tools/extract_stage_e_pal_metadata.py"
python3 "$project/research/gpu/tools/generate_stage_e_agc_metadata.py"
mkdir -p "$build/obj" "$build/import-stubs" "$dist/sce_sys" "$dist/sce_module"
cc=(env PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18")
common=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
"${cc[@]}" -std=c++20 "${common[@]}" -fno-exceptions -fno-rtti \
  -I"$project" -c "$root/stage_e_main.cpp" -o "$build/obj/main.o"
for unit in stage_b_surface stage_b_compose stage_b_completion stage_b_event_adapter \
            stage_e_shader_header stage_e_color_target \
            stage_e_runtime_defaults stage_e_pipeline_registers stage_e_dcb_offline; do
  "${cc[@]}" -std=c11 "${common[@]}" -I"$project" -c "$stage/$unit.c" \
    -o "$build/obj/$unit.o"
done
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
objects=("$build/obj/app_crt.o" "$build/obj/main.o" "$build/obj/assets.o")
for unit in stage_b_surface stage_b_compose stage_b_completion stage_b_event_adapter \
            stage_e_shader_header stage_e_color_target \
            stage_e_runtime_defaults stage_e_pipeline_registers stage_e_dcb_offline; do
  objects+=("$build/obj/$unit.o")
done
"$sdk/bin/prospero-lld" -T "$native/ps5-pie.ld" --eh-frame-hdr \
  --version-script "$native/app-symbols.map" -e _start \
  -o "$build/llvm-pie.elf" "${objects[@]}" --as-needed \
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
python3 "$root/verify_stage_e.py"
