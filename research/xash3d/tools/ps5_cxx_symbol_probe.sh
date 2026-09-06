#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)
XASH_ROOT=${XASH3D_ROOT:-"$REPO_ROOT/third_party/xash3d-fwgs"}
HLSDK_ROOT=${HLSDK_ROOT:-"$REPO_ROOT/third_party/hlsdk-portable"}
BOILERPLATE_ROOT=${PS5_BOILERPLATE_ROOT:-"$REPO_ROOT/third_party/ps5-native-app-boilerplate-exp-prx-module"}
SDK_ROOT=${PS5_PAYLOAD_SDK:-"$BOILERPLATE_ROOT/.deps/native/ps5-payload-sdk"}

if [[ -n ${PROBE_OUT:-} ]]; then
  OUTROOT=$PROBE_OUT
  if [[ -e $OUTROOT ]]; then
    echo "PROBE_OUT already exists; refusing to overwrite: $OUTROOT" >&2
    exit 2
  fi
  mkdir -p "$OUTROOT"
else
  OUTROOT=$(mktemp -d -t xash-ps5-cxx-probe.XXXXXX)
fi

[[ -d $XASH_ROOT/3rdparty/mainui ]] || {
  echo "missing mainui tree: $XASH_ROOT/3rdparty/mainui" >&2
  exit 2
}
[[ -d $HLSDK_ROOT ]] || { echo "missing hlsdk tree: $HLSDK_ROOT" >&2; exit 2; }
[[ -r $BOILERPLATE_ROOT/tooling/prospero-clang18 ]] || {
  echo "missing Prospero compiler wrapper: $BOILERPLATE_ROOT/tooling/prospero-clang18" >&2
  exit 2
}
[[ -d $SDK_ROOT ]] || { echo "missing PS5 payload SDK: $SDK_ROOT" >&2; exit 2; }

CC=(env PS5_PAYLOAD_SDK="$SDK_ROOT" sh "$BOILERPLATE_ROOT/tooling/prospero-clang18")
probe() { # name basedir extra-defs... ; sources via stdin
  local name=$1 base=$2; shift 2; local defs=("$@"); local out="$OUTROOT/$name"; mkdir -p "$out/obj"; cd "$base"
  while read -r src; do
    [[ -n $src ]] || continue
    local obj="$out/obj/${src//\//_}.o"; local std=(-std=gnu++11 -fno-exceptions -fno-rtti); [[ $src == *.c ]] && std=(-std=gnu11)
    if "${CC[@]}" "${std[@]}" -O1 -w -fPIC -ferror-limit=2 "${defs[@]}" "${INC[@]}" -c "$src" -o "$obj" </dev/null 2>"$obj.err"; then echo "OK $src"; else echo "FAIL $src :: $(grep -m1 'error:' "$obj.err" | sed 's/.*error: //')"; fi
  done > "$out/compile.log"
  local ok_count fail_count
  ok_count=$(grep -c '^OK' "$out/compile.log" || true)
  fail_count=$(grep -c '^FAIL' "$out/compile.log" || true)
  echo "== $name: OK $ok_count FAIL $fail_count"
  if (( fail_count > 0 )); then
    grep '^FAIL' "$out/compile.log" | sed 's/.*:: //' | sort | uniq -c | sort -rn | head -8
  fi
}
# mainui
M=$XASH_ROOT/3rdparty/mainui
INC=(-I. -Iminiutl -Ifont -Icontrols -Imenus -Imodel -Isdk_includes/common -Isdk_includes/engine -Isdk_includes/public -Isdk_includes/pm_shared)
MAINUI_SOURCES=$OUTROOT/mainui.sources
( cd "$M" && find . miniutl font menus menus/dynamic model controls -maxdepth 1 -name '*.cpp' | sed 's|^\./||' | sort -u ) > "$MAINUI_SOURCES"
probe mainui "$M" -DMAINUI_USE_STB=1 "-DSTDINT_H=<stdint.h>" -DK_ESCAPE_FIX=1 < "$MAINUI_SOURCES"
# hlsdk client
H=$HLSDK_ROOT
INC=(-I. -I../dlls -I../common -I../engine -I../pm_shared -I../game_shared -I../public -I../utils/fake_vgui/include)
HLSDK_CLIENT_SOURCES=$OUTROOT/hlsdk-client.sources
( cd "$H/cl_dll" && { find . -name '*.cpp' ! -name 'GameStudioModelRenderer_Sample*' ! -name 'vgui_*' ! -name 'voice_status*' ! -name 'voice_banmgr*'; find ../game_shared -maxdepth 1 -name '*.cpp' ! -name 'vgui_*' ! -name 'voice_*'; echo ../public/safe_snprintf.c; echo ../external/openbsd/strlcpy.c; echo ../external/openbsd/strlcat.c; find ../pm_shared -name '*.c'; } | sort -u ) > "$HLSDK_CLIENT_SOURCES"
probe hlsdk_client "$H/cl_dll" -DCLIENT_DLL -DCLIENT_WEAPONS -Dstricmp=strcasecmp -Dstrnicmp=strncasecmp -D_snprintf=snprintf -D_vsnprintf=vsnprintf < "$HLSDK_CLIENT_SOURCES"
# hlsdk server
INC=(-I. -I../common -I../engine -I../pm_shared -I../game_shared -I../public)
HLSDK_SERVER_SOURCES=$OUTROOT/hlsdk-server.sources
( cd "$H/dlls" && { find . -name '*.cpp' ! -name '*mpstubb*' ! -name 'stats.cpp' ! -name '*Wxdebug*'; find ../pm_shared -name '*.c'; echo ../public/safe_snprintf.c; echo ../external/openbsd/strlcpy.c; echo ../external/openbsd/strlcat.c; } | sort -u ) > "$HLSDK_SERVER_SOURCES"
probe hlsdk_server "$H/dlls" -DCLIENT_WEAPONS -DNO_VOICEGAMEMGR -Dstricmp=strcasecmp -Dstrnicmp=strncasecmp -D_snprintf=snprintf -D_vsnprintf=vsnprintf < "$HLSDK_SERVER_SOURCES"
echo "probe output: $OUTROOT"
