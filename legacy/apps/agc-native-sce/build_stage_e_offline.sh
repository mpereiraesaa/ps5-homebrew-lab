#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd -- "$root/../../.." && pwd)
reference="$project/third_party/ps5-native-app-boilerplate"
sdk="$reference/.deps/native/ps5-payload-sdk"
native="$reference/tooling/native"
tool="$reference/build/host/ps5-native-tool"
build="$root/build-stage-e-offline"
dist="$root/dist-stage-e-offline/PPSA99998"
[[ -x $tool && -d $sdk ]] || exit 2
mkdir -p "$build/obj" "$dist/sce_sys" "$dist/sce_module"
cc=(env PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18")
common=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -I"$project")
"${cc[@]}" -std=c++20 "${common[@]}" -fno-exceptions -fno-rtti \
  -c "$root/stage_e_offline_main.cpp" -o "$build/obj/main.o"
for unit in stage_e_color_target stage_e_dcb_offline stage_e_pipeline_registers; do
  "${cc[@]}" -std=c11 "${common[@]}" \
    -c "$project/legacy/probes/ps5-agc-phase0/$unit.c" -o "$build/obj/$unit.o"
done
"${cc[@]}" -std=c++20 "${common[@]}" -fno-exceptions -fno-rtti \
  -c "$native/app_crt.cpp" -o "$build/obj/app_crt.o"
"$sdk/bin/prospero-lld" -T "$native/ps5-pie.ld" --eh-frame-hdr \
  --version-script "$native/app-symbols.map" -e _start \
  -o "$build/llvm-pie.elf" "$build/obj/app_crt.o" "$build/obj/main.o" \
  "$build/obj/stage_e_color_target.o" "$build/obj/stage_e_dcb_offline.o" \
  "$build/obj/stage_e_pipeline_registers.o" \
  --as-needed "$sdk"/target/lib/*.so
"$tool" link --in "$build/llvm-pie.elf" --out "$build/eboot.elf" \
  --stub-dir "$sdk/target/lib" --module-sdk 0x02000009 \
  --companion-sdk 0x08050001 --file-name eboot.elf
"$tool" self --sign --in "$build/eboot.elf" --out "$dist/eboot.bin" \
  --magic 0x1D3D154F
cp "$root/sce_sys/param.json" "$dist/sce_sys/param.json"
cp "$reference/sce_sys/icon0.png" "$dist/sce_sys/icon0.png"
cp "$reference/runtime/libc.prx" "$dist/sce_module/libc.prx"
sha256sum "$build/eboot.elf" "$dist/eboot.bin"
"$tool" self --inspect --file "$dist/eboot.bin"
python3 "$root/verify_stage_e_offline.py"
