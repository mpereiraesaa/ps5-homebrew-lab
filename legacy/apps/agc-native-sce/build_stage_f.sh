#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
variant=${1:-f}
if [[ $variant != n && $variant != f && $variant != g && $variant != g22 && $variant != g23off && $variant != g23on && $variant != h && $variant != i && $variant != iclearproof && $variant != i1000 && $variant != i10000 ]]; then exit 2; fi
project=$(cd -- "$root/../../.." && pwd)
reference="$project/third_party/ps5-native-app-boilerplate"
sdk="$reference/.deps/native/ps5-payload-sdk"
native="$reference/tooling/native"
tool="$reference/build/host/ps5-native-tool"
stage="$project/legacy/probes/ps5-agc-phase0"
ps5log="$project/projects/logging_server/client"
dev_conf="$project/projects/logging_server/dev.conf"
if [[ $variant == h || $variant == i* ]]; then
  shader_build="$project/research/gpu/build/stage-h-gears"
  shader_pipe="$project/research/gpu/experiments/gears-contracts/gears_lit.pipe"
  shader_name=gears
  metadata_name=stage-h-gears
  metadata_header=stage_h_compiled_metadata.h
  metadata_define=STAGE_H_GEARS_METADATA
  assets_source=stage_h_assets.S
else
  shader_build="$project/research/gpu/build/stage-f-cube"
  shader_pipe="$project/research/gpu/experiments/gears-contracts/cube_vertex_input.pipe"
  shader_name=cube
  metadata_name=stage-f-cube
  metadata_header=stage_f_compiled_metadata.h
  metadata_define=STAGE_F_CUBE_METADATA
  assets_source=stage_f_assets.S
fi
build="$root/build-stage-$variant"
dist="$root/dist-stage-$variant/PPSA99998"
driver_stub="$build/import-stubs/libSceAgcDriver.so"
agc_stub="$build/import-stubs/libSceAgc.so"
[[ -x $tool && -d $sdk && ( ${PS5_NO_LOG:-0} == 1 || -f $dev_conf ) ]] || {
  echo "missing toolchain, SDK, or private logging_server/dev.conf" >&2
  exit 2
}
python3 "$project/research/gpu/tools/build_stage_e_gfx1013.py" \
  --pipe "$shader_pipe" --output "$shader_build/$shader_name.pal.elf" \
  --gs "$shader_build/$shader_name.bin" --ps "$shader_build/${shader_name}_lit.bin"
python3 "$project/research/gpu/tools/extract_stage_e_pal_metadata.py" \
  --elf "$shader_build/$shader_name.pal.elf" \
  --output "$project/research/gpu/captures/$metadata_name-gfx1013-pal-metadata.json"
python3 "$project/research/gpu/tools/generate_stage_e_agc_metadata.py" \
  --source "$project/research/gpu/captures/$metadata_name-gfx1013-pal-metadata.json" \
  --output "$stage/$metadata_header" \
  --capture "$project/research/gpu/captures/$metadata_name-gfx1013-agc-metadata.json"
mkdir -p "$build/obj" "$build/import-stubs" "$dist/sce_sys" "$dist/sce_module"
cc=(env PS5_PAYLOAD_SDK="$sdk" sh "$reference/tooling/prospero-clang18")
common=(-O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections)
"${cc[@]}" -std=c++20 "${common[@]}" -D"$metadata_define" -fno-exceptions -fno-rtti \
  -I"$project" -I"$ps5log" -c "$root/stage_${variant}_main.cpp" -o "$build/obj/main.o"
if [[ ${PS5_NO_LOG:-0} == 1 ]]; then
  "${cc[@]}" -std=c11 "${common[@]}" -I"$ps5log" \
    -c "$root/ps5log_null.c" -o "$build/obj/ps5log.o"
else
  "${cc[@]}" -std=c11 "${common[@]}" -I"$ps5log" \
    -include "$ps5log/ps5log_ps5_net.h" \
    -c "$ps5log/ps5log.c" -o "$build/obj/ps5log.o"
  "${cc[@]}" -std=c11 "${common[@]}" -I"$ps5log" \
    -c "$ps5log/ps5log_ps5_net.c" -o "$build/obj/ps5log_ps5_net.o"
fi
for unit in stage_b_surface stage_b_compose stage_b_completion stage_b_event_adapter \
            stage_e_color_target stage_e_runtime_defaults \
            stage_e_pipeline_registers stage_e_dcb_offline \
            stage_gpu_visibility; do
  "${cc[@]}" -std=c11 "${common[@]}" -I"$project" -c "$stage/$unit.c" \
    -o "$build/obj/$unit.o"
done
if [[ $variant == g || $variant == g22 || $variant == g23off || $variant == g23on || $variant == h || $variant == i* ]]; then
  "${cc[@]}" -std=c11 "${common[@]}" -I"$project" \
    -c "$stage/stage_g_depth_state.c" -o "$build/obj/stage_g_depth_state.o"
fi
if [[ $variant == h || $variant == i* ]]; then
  gears_units=(gears_mesh gears_scene gears_draw_compose)
  if [[ $variant == i* ]]; then
    gears_units+=(gears_frame_tracker gears_animation gears_telemetry gears_frame_runner gears_rt_clear gears_renderer)
  fi
  for unit in "${gears_units[@]}"; do
    "${cc[@]}" -std=c11 "${common[@]}" -I"$project" \
      -c "$project/projects/ps5-agc-gears/src/$unit.c" -o "$build/obj/$unit.o"
  done
fi
"${cc[@]}" -std=c11 "${common[@]}" -D"$metadata_define" -I"$project" \
  -c "$stage/stage_e_shader_header.c" -o "$build/obj/stage_e_shader_header.o"
(cd "$project" && "${cc[@]}" -c "$root/$assets_source" -o "$build/obj/assets.o")
"${cc[@]}" -std=c++20 "${common[@]}" -fno-exceptions -fno-rtti \
  -c "$native/app_crt.cpp" -o "$build/obj/app_crt.o"
"${cc[@]}" -std=c11 -O2 -fPIC -I"$project/sdk/agc/include" \
  -c "$project/sdk/agc/stubs/libSceAgcDriver_link_stub.c" -o "$build/obj/driver-stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgcDriver.prx \
  -o "$driver_stub" "$build/obj/driver-stub.o"
"${cc[@]}" -std=c11 -O2 -fPIC -I"$project/sdk/agc/include" \
  -c "$project/sdk/agc/stubs/libSceAgc_link_stub.c" -o "$build/obj/agc-stub.o"
"$sdk/bin/prospero-lld" --shared -soname libSceAgc.prx \
  -o "$agc_stub" "$build/obj/agc-stub.o"
objects=("$build/obj/app_crt.o" "$build/obj/main.o" "$build/obj/assets.o" \
         "$build/obj/stage_e_shader_header.o" "$build/obj/ps5log.o")
if [[ ${PS5_NO_LOG:-0} != 1 ]]; then
  objects+=("$build/obj/ps5log_ps5_net.o")
fi
for unit in stage_b_surface stage_b_compose stage_b_completion stage_b_event_adapter \
            stage_e_color_target stage_e_runtime_defaults \
            stage_e_pipeline_registers stage_e_dcb_offline \
            stage_gpu_visibility; do
  objects+=("$build/obj/$unit.o")
done
if [[ $variant == g || $variant == g22 || $variant == g23off || $variant == g23on || $variant == h || $variant == i* ]]; then
  objects+=("$build/obj/stage_g_depth_state.o")
fi
if [[ $variant == h || $variant == i* ]]; then
  objects+=("$build/obj/gears_mesh.o" "$build/obj/gears_scene.o" \
            "$build/obj/gears_draw_compose.o")
  if [[ $variant == i* ]]; then
    objects+=("$build/obj/gears_frame_tracker.o" \
              "$build/obj/gears_animation.o" \
              "$build/obj/gears_telemetry.o" \
              "$build/obj/gears_frame_runner.o" \
              "$build/obj/gears_rt_clear.o" \
              "$build/obj/gears_renderer.o")
  fi
fi
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
if [[ ${PS5_NO_LOG:-0} == 1 ]]; then
  rm -f "$dist/dev.conf"
else
  cp "$dev_conf" "$dist/dev.conf"
fi
sha256sum "$build/eboot.elf" "$dist/eboot.bin"
"$tool" self --inspect --file "$dist/eboot.bin"
