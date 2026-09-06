# Xash3D FWGS en PS5: tamaño de lo ausente (2026-09-06)

Objetivo: medir cuánto del engine `xash3d-fwgs` compila para el target nativo
de PS5 con el SDK del boilerplate y qué símbolos quedan sin proveedor, antes de
escribir una sola línea del backend. Sin consola: todo es host.

## Método

- Fuente: `third_party/xash3d-fwgs` en `9aa39ad` (2026-08-30), clon superficial
  con submódulos. Script: `research/xash3d/tools/ps5_symbol_probe.sh`.
- Compilador: `prospero-clang18` del boilerplate (`x86_64-sie-ps5`, sysroot del
  payload SDK), `-std=gnu11 -O1 -w`, sólo `-c`.
- Fuentes: `engine/common`, `imagelib`, `soundlib`, `http`, `server`, `client`
  completo, `platform/posix`, `platform/stub`, `public`, `filesystem`. Sin
  `ref_*`; `mainui` y `hlsdk-portable` se miden aparte más abajo.
- Defines: `XASH_STATIC_LIBS=1 XASH_NO_LIBDL=1 XASH_CRASHHANDLER=0
  XASH_TIMER=TIMER_POSIX XASH_MESSAGEBOX=MSGBOX_STDERR`. El `build.h` del target
  detecta `__FreeBSD__ 9` y deriva `XASH_FREEBSD`, `XASH_POSIX`, `XASH_64BIT`,
  `XASH_AMD64` por sí solo; el compilador define además `__PROSPERO__` y
  `__SCE__`, útiles para una rama `XASH_PS5` futura.
- Dos configuraciones: cliente con `XASH_SDL=2` (selecciona los backends SDL en
  `defaults.h` sin compilar `platform/sdl2`) y `XASH_DEDICATED=1`.
- Símbolos: `llvm-nm -u` sobre los objetos menos los definidos por el propio
  conjunto, cruzados con los exports de los stubs `target/lib/*.so` del SDK.
- Los scripts derivan la raíz del laboratorio desde Git. Las dependencias se
  pueden reemplazar con `XASH3D_ROOT`, `HLSDK_ROOT`, `PS5_BOILERPLATE_ROOT` y
  `PS5_PAYLOAD_SDK`. Sin `PROBE_OUT` crean un directorio temporal nuevo; si se
  proporciona, debe no existir y nunca se borra una ruta previa.
  `ps5_symbol_probe.sh` reproduce el cliente por defecto; `PROBE_EXTRA` permite
  reemplazar sus defines, por ejemplo con `-DXASH_DEDICATED=1`.

## Resultado de compilación

| Configuración | Archivos | Compilan | Fallan | Causa de los fallos |
| --- | ---: | ---: | ---: | --- |
| Cliente (`XASH_SDL=2`) | 162 | 156 | 6 | 5 por `SDL.h`/`SDL_thread.h` (`cl_game.c`, `input.c`, `filesystem_engine.c`, `net_ws.c`, `system.c`); 1 por `generated_library_tables.h` (`lib_static.c`, tabla que genera waf). |
| Dedicado | 162 | 158 | 4 | 3 redefiniciones esperadas por compilar el cliente en modo dedicado; `lib_static.c`. |

Todas las cabeceras de sistema que usa el engine resolvieron con el sysroot del
payload SDK: sockets, `dirent`, `sys/stat`, `pthread`, `setjmp`, `time`,
`ifaddrs`. Ningún fallo de compilación fue por libc o POSIX.

## Símbolos externos del cliente

304 símbolos externos sobre 4.677 definidos.

| Categoría | Cuántos | Proveedor / acción |
| --- | ---: | --- |
| libc y POSIX del SDK | 105 | `libSceLibcInternal` 75, `libkernel` 27, `libkernel_sys` 3. Imports normales del título. |
| Terceros empaquetados en el árbol | 40 | `bzip2`, `opus`, `opusfile`, `vorbis`, `ogg`. C portable; compilan con el mismo toolchain. |
| Internos del engine | 156 | Definidos en archivos que fallaron por `SDL.h` o en `platform/sdl*`: `NET_*`, `Sys_*`, `FS_*`/`g_fsapi`, `CL_LoadProgs`, `IN_*`, `Platform_*`, `R_*Video`/`VID_*`/`GL_*`/`SW_*`, `SNDDMA_*`, `VoiceCapture_*`, `COM_LoadLibrary`/`COM_GetProcAddress`/`COM_FreeLibrary`, `Tri*`/`pfn*`, cvars `cl_*`. No son huecos de plataforma: son el backend a escribir. |
| **Faltan de verdad en el SDK** | **3** | `__assert` (destino del `assert()` de la libc del target), `getpwuid` (`id_posix.c`, sólo identidad de usuario), `dladdr` (`lib_posix.c`, nombre de función para logs). |

Sin `compiler-rt` pendiente: ningún `__divti3`, `__popcount` ni similar.

En dedicado: 292 externos, 126 del SDK (añade `libScePosixForWebKit` 2 y
`libSceNet` 1), 37 de terceros, 129 internos y los mismos 3 ausentes.

## Lo que esto dice del port

1. **La libc no es el problema.** De 304 externos, tres faltan y los tres son
   triviales: `__assert` es una función de una línea; `getpwuid` se reemplaza
   por un id fijo o el `sceUserService`; `dladdr` desaparece con el cargador
   PRX. El `libc.prx` del boilerplate es un shim, pero las funciones reales
   vienen de `libSceLibcInternal` y `libkernel`, que ya exportan las 105.
2. **El trabajo real es el backend `platform/ps5`**, en la línea de
   `platform/psvita` y `platform/nswitch`: una rama `XASH_PS5` en `build.h`
   y `defaults.h` que seleccione `VIDEO_PS5`, `INPUT_PS5`, `SOUND_PS5`,
   `TIMER_POSIX`, `MSGBOX_STDERR`; `vid_ps5.c` sobre el backend AGC
   (`R_Init_Video`, `VID_SetMode`, `GL_SwapBuffers` como present del frame
   loop, `SW_*Buffer` para el fallback); `in_ps5.c` sobre ScePad; `s_ps5.c`
   sobre AudioOut (`SNDDMA_*`); `host_ps5.c` con `Platform_RunEvents`; y
   `lib_ps5.c` implementando `COM_LoadLibrary`, `COM_GetProcAddress` y
   `COM_FreeLibrary` sobre `prx_load`, `prx_get_proc` y `prx_unload` de
   `modules/prx_loader.h`. `system.c`, `net_ws.c` y `filesystem_engine.c`
   compilan en cuanto no exista `XASH_SDL`.
3. **Hilos y red existen** en el SDK: `pthread` vía `libSceLibcInternal`,
   sockets BSD vía `libkernel` (`socket`, `bind`, `select`, `getifaddrs`).
   Queda por probar en hardware que un título pueda abrir sockets; el
   laboratorio ya usa `sceNet*` para la telemetría.
4. **C++ medido: tampoco es el problema.** Ver la sección siguiente. El
   runtime C++ básico que necesitan `mainui` y `hlsdk-portable` lo exporta
   `libSceLibcInternal`: `operator new`/`delete` (`_Znwm`, `_Znam`, `_ZdlPv`,
   `_ZdaPv`), `__cxa_atexit`, `__cxa_guard_acquire`/`release` y
   `__cxa_pure_virtual`. Sin excepciones ni RTTI, como compila el boilerplate,
   no hace falta `libc++` completo.
5. **`filesystem_stdio`** es un módulo aparte que el engine carga con
   `COM_LoadLibrary`. Con `XASH_STATIC_LIBS` queda dentro del ejecutable; con
   el cargador PRX puede ser el primer módulo real del port.

## Componentes C++: `mainui` y `hlsdk-portable`

Script: `research/xash3d/tools/ps5_cxx_symbol_probe.sh`. Mismo toolchain,
`-std=gnu++11 -fno-exceptions -fno-rtti -fPIC`, con las definiciones que waf
aportaría (`STDINT_H=<stdint.h>`, `stricmp=strcasecmp`, `strnicmp=strncasecmp`,
`_snprintf=snprintf`, `_vsnprintf=vsnprintf`). `hlsdk-portable` en `e277ffa`
(2026-08-26), configuración sin VGUI (`fake_vgui`), `CLIENT_WEAPONS`,
`NO_VOICEGAMEMGR`.

| Componente | Archivos | Compilan | Externos | Del SDK | Faltan | Qué falta |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `mainui` (menú) | 82 | 80 | 64 | 49 | 15 | `__assert`, `__dso_handle`, y 13 de `CFontManager`/`g_FontMgr`, definidos en los dos archivos del backend de fuentes stb que no compilaron por un include (`K_ESCAPE`); no es plataforma. |
| `hlsdk` cliente (`client.so`) | 52 | 52 | 61 | 43 | 3 | `__assert`, `g_VCSInfo_Branch`, `g_VCSInfo_Commit` (waf genera los dos últimos). Las 15 `_ZTV*` restantes son vtables de armas que el build real toma de `dlls/`, no plataforma. |
| `hlsdk` servidor (`hl.so`) | 106 | 106 | 48 | 45 | 3 | Los mismos tres. |

Conclusión C++: cero símbolos de runtime sin proveedor. `__dso_handle` lo
define el CRT del ejecutable; para un módulo PRX hay que emitirlo en el módulo,
una línea. `__assert` es la misma función de una línea que en el engine.

## Entrega a otro agente: contexto necesario

- Tooling de módulos: fork `mpereiraesaa/ps5-native-app-boilerplate`, rama
  `exp/prx-module`; leer `docs/MODULES.md` completo (contratos del loader,
  `tools/build-module.sh`, `modules/prx_loader.h`). Los módulos del engine
  (`client`, `hl`, `menu`, `filesystem_stdio`, `ref_agc`) se construyen con ese
  flujo y publican sus entradas con `PRX_DEFINE_DESCRIPTOR`.
- Gate de hardware y sus resultados: repo Gears, rama `exp/prx-gate`,
  `experiments/prx-gate/README.md`. Resumen: carga en runtime sí; `DT_NEEDED`
  de módulos propios no; `sceKernelDlsym` no; resolución por descriptor sí.
- Libro del laboratorio: `docs/FINDINGS.md` sección "Módulos PRX propios",
  `docs/CURRENT.md` "Application-owned modules", plan `docs/XASH3D_PS5_PLAN.html`.
- Renderer: `ref_agc` se implementa contra `ref_api.h` sobre el backend de
  `projects/ps5-agc-gears`; el viewer BSP de la Fase 1 (rama
  `feature/bsp-viewer-gate1`, otro agente) es su antecedente directo.
- Reglas operativas: una variable por iteración; `make check` antes de tocar la
  consola; sólo un BigApp a la vez, comprobar `night_supervisor.py status`;
  reload de ShadowMountPlus sólo sin BigApp; evidencia siempre por `ps5log/1`
  con manifiesto y hash de artefacto; klog en el puerto 3232; `ftpsrv` muestra
  los fSELF como ELF descifrado con los últimos 512 bytes reescritos.
- Título de pruebas: `PPSA99999` está reservado para gates y lo conocen los
  helpers; `PPSA99997` es la demo Gears y lo usa otro agente; `PPSA99998` es
  el laboratorio histórico.
- Pendientes que este informe no cierra: verificar en hardware sockets y
  `pthread` desde un título; decidir la ruta de datos del juego bajo `/app0`;
  el primer módulo real recomendado es `filesystem_stdio` como PRX, seguido de
  un `platform/ps5` mínimo que arranque el engine hasta la consola.

## Datos crudos

- `research/xash3d/ps5-symbol-gap-2026-09-06.json`: listas completas por
  categoría y configuración.
- `research/xash3d/tools/ps5_symbol_probe.sh`: reproduce la compilación del
  engine; `PROBE_EXTRA` fija la configuración, `PROBE_OUT` el destino.
- `research/xash3d/tools/ps5_cxx_symbol_probe.sh` y
  `research/xash3d/ps5-cxx-symbol-gap-2026-09-06.json`: componentes C++.
- `research/xash3d/tools/probe-extra/ogg/config_types.h`: sustituto del header
  que genera el configure de libogg, sólo para el probe.
