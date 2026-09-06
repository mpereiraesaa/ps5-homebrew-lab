#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)
XASH_ROOT=${XASH3D_ROOT:-"$REPO_ROOT/third_party/xash3d-fwgs"}
BOILERPLATE_ROOT=${PS5_BOILERPLATE_ROOT:-"$REPO_ROOT/third_party/ps5-native-app-boilerplate-exp-prx-module"}
SDK_ROOT=${PS5_PAYLOAD_SDK:-"$BOILERPLATE_ROOT/.deps/native/ps5-payload-sdk"}

if [[ -n ${PROBE_OUT:-} ]]; then
  OUT=$PROBE_OUT
  if [[ -e $OUT ]]; then
    echo "PROBE_OUT already exists; refusing to overwrite: $OUT" >&2
    exit 2
  fi
  mkdir -p "$OUT"
else
  OUT=$(mktemp -d -t xash-ps5-symbol-probe.XXXXXX)
fi
mkdir -p "$OUT/obj"

[[ -d $XASH_ROOT ]] || { echo "missing Xash3D tree: $XASH_ROOT" >&2; exit 2; }
[[ -r $BOILERPLATE_ROOT/tooling/prospero-clang18 ]] || {
  echo "missing Prospero compiler wrapper: $BOILERPLATE_ROOT/tooling/prospero-clang18" >&2
  exit 2
}
[[ -d $SDK_ROOT ]] || { echo "missing PS5 payload SDK: $SDK_ROOT" >&2; exit 2; }

cd "$XASH_ROOT"
CC=(env PS5_PAYLOAD_SDK="$SDK_ROOT" sh "$BOILERPLATE_ROOT/tooling/prospero-clang18")
INC=(-I"$SCRIPT_DIR/probe-extra" -I3rdparty/library_suffix/include -I3rdparty/opus/opus/include -I3rdparty/opusfile/opusfile/include -I3rdparty/libogg/libogg/include -I3rdparty/vorbis/vorbis-src/include -I3rdparty/bzip2/bzip2 -Iengine -Iengine/common -Iengine/common/imagelib -Iengine/common/soundlib -Iengine/server -Iengine/client -Iengine/client/vgui -Iengine/platform -Icommon -Ipublic -Ipm_shared -Ifilesystem -I3rdparty -I3rdparty/opus/include -I3rdparty/opusfile/include -I3rdparty/vorbis/vorbis-src/include -I3rdparty/libogg/include -I3rdparty/bzip2 -I3rdparty/mbedtls/include -I3rdparty/MultiEmulator/include -I3rdparty/libbacktrace)
if [[ -n ${PROBE_EXTRA:-} ]]; then
  read -r -a EXTRA_DEFS <<< "$PROBE_EXTRA"
else
  EXTRA_DEFS=(-DXASH_SDL=2)
fi
DEFS=(-DXASH_STATIC_LIBS=1 -DXASH_NO_LIBDL=1 -DXASH_CRASHHANDLER=0 -DENGINE_DLL=1 -DXASH_LOW_MEMORY=0 '-DXASH_GAMEDIR="valve"' '-DXASH_BUILD_COMMIT="probe"' '-DXASH_BUILD_BRANCH="probe"' '-DXASH_BUILD_COMMIT_DATE="probe"' "${EXTRA_DEFS[@]}")
{ find engine/common engine/common/imagelib engine/common/soundlib engine/common/http engine/server engine/client engine/platform/posix engine/platform/stub public filesystem -maxdepth 1 -name '*.c'; echo engine/platform/misc/lib_static.c; find engine/client -mindepth 2 -name '*.c'; } | grep -v '/tests/' | sort -u > "$OUT/sources.txt"
echo "sources: $(wc -l < "$OUT/sources.txt")"
compile_one() {
  local src=$1 obj="$OUT/obj/${1//\//_}.o"
  if "${CC[@]}" -std=gnu11 -O1 -w -ferror-limit=2 "${DEFS[@]}" "${INC[@]}" -c "$src" -o "$obj" 2>"$obj.err"; then echo "OK $src"; else echo "FAIL $src :: $(grep -m1 'error:' "$obj.err" | sed 's/.*error: //')"; fi
}
# run sequentially in background-parallel batches
pids=(); n=0
while read -r src; do compile_one "$src" >> "$OUT/compile.log" & pids+=($!); n=$((n+1)); if (( n % 12 == 0 )); then wait; fi; done < "$OUT/sources.txt"; wait
ok_count=$(grep -c '^OK' "$OUT/compile.log" || true)
fail_count=$(grep -c '^FAIL' "$OUT/compile.log" || true)
echo "compiled OK: $ok_count  FAIL: $fail_count"
if (( fail_count > 0 )); then
  echo "##### failure reasons (grouped)"
  grep '^FAIL' "$OUT/compile.log" | sed 's/.*:: //' | sort | uniq -c | sort -rn | head -30
fi
echo "probe output: $OUT"
