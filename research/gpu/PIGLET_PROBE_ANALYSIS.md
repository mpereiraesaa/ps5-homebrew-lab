# Probe Piglet/GLSlim — PS5 12.02

Fecha de corte: 2026-09-03. Este análisis separa evidencia observada de
compatibilidad inferida. No se ejecutó ningún ELF de este probe en la consola.

## Resultado ejecutivo

La PS5 12.02 conserva una implementación EGL/OpenGL ES orientada al shell,
pero no con el empaquetado de PS4:

- Existe `/system_ex/common_ex/lib/libSceGLSlimVSH.sprx` (406606 bytes en el
  filesystem de esta consola).
- No existen, en las cuatro rutas estándar examinadas,
  `libScePigletv2VSH.sprx` ni `libSceShaccVSH.sprx`.
- El SDK asigna a GLSlim el sysmodule interno `0x800000a9`.
- Su stub contiene 203 exports: 32 EGL, 145 GLES/Orbis GL, 6 Piglet y 20
  funciones `sceSlimgl*` de IPC/composición.
- Los inventarios de memoria sólo lo muestran en `SceNKUIProcess`. No aparece
  en RE2, San Andreas ni en el proceso del probe VideoOut `FAKE00000`.

Por tanto, “Piglet está en PS5” es correcto a nivel de API y módulo, pero aún
no está demostrado que un proceso homebrew tenga autorización para cargarlo,
inicializar su backend o presentar una ventana.

## Evidencia local

El módulo de `SceNKUIProcess` ocupa cuatro mappings:

| Segmento | Dirección observada | Tamaño | Permisos |
|---|---:|---:|---|
| texto | `0x8005bc000` | 999424 | `r-x` |
| datos RO | `0x8006b0000` | 147456 | `r--` |
| datos RO/BSS | `0x8006d4000` | 245760 | `r--` |
| datos RW | `0x800710000` | 16384 | `rw-` |

La diferencia entre el tamaño del archivo y el total mapeado es normal para
un ELF/SPRX con segmentos y BSS; no implica que el archivo esté incompleto.

Exports relevantes y NID calculados con `prospero-nid`:

| Símbolo | NID |
|---|---|
| `scePigletAllocateSystemMemoryEx` | `oXkQEVitkCs` |
| `scePigletAllocateVideoMemoryEx` | `sDotUt1uEhA` |
| `scePigletGetConfigurationVSH` | `3gtNzvkq-XY` |
| `scePigletReleaseSystemMemoryEx` | `T-+xooU3VvQ` |
| `scePigletReleaseVideoMemoryEx` | `AcruVcmKz78` |
| `scePigletSetConfigurationVSH` | `M9RtXpjSYtE` |
| `eglGetDisplay` | `Z7pNCsK2dAs` |
| `eglInitialize` | `KJmeNzmA6UM` |
| `eglGetError` | `Pu5Yd9+FY9Y` |
| `eglTerminate` | `ConU-nXswn8` |
| `eglChooseConfig` | `fesoNJCZpSA` |
| `eglCreateContext` | `0oZKK6QmW-k` |
| `eglCreateWindowSurface` | `PSqt1KLK7o0` |
| `eglMakeCurrent` | `D947DWfj9tY` |
| `eglSwapBuffers` | `51YpII41z34` |
| `glClearColor` | `Pkhe5Qcq++0` |
| `glClear` | `KOJ4+zzhpAg` |

Los NID calculados prueban la identidad esperada por el loader/stub, no por sí
solos que firmware 12.02 vaya a resolverlos para `FAKE00000`; fase 1 mide eso.

## Diferencia respecto de PS4

La ruta pública de PS4 cargaba `libScePigletv2VSH.sprx` y
`libSceShaccVSH.sprx`, y después parcheaba módulos VSH. `orbisGlPerf` reportó
EGL 1.4 y OpenGL ES 2.0 Piglet una vez aplicada esa preparación. Su biblioteca
`liborbisGl` configuraba memoria compartida, memoria de video, flexible memory,
command buffers y una ventana candidata `{type,width,height}` antes de
`eglInitialize`.

Fuentes públicas consultadas:

- [orbisGlPerf](https://github.com/orbisdev/orbisGlPerf)
- [liborbis / liborbisGl](https://github.com/orbisdev/liborbis/tree/master/liborbisGl)
- [orbisdev-orbislink](https://github.com/orbisdev/orbisdev-orbislink)

No se reutiliza ciegamente `ScePglConfig` de PS4: GLSlim de PS5 podría haber
cambiado tamaño, flags, ownership de memoria, IPC o ABI de la ventana. Tampoco
se presupone un compilador Shacc separado; su ausencia puede significar que
GLSlim integra otra ruta, acepta sólo shader binaries, o depende de un servicio
no accesible al homebrew.

## Probe implementado

Código: `legacy/probes/ps5-piglet-probe`. Produce cinco ELFs independientes:

1. `piglet-phase1-resolve.elf`: `dlopen` y `dlsym`, sin llamar EGL/Piglet.
1b. `piglet-phase1b-sysmodule.elf`: solicita primero el sysmodule interno
   `0x800000a9` y sólo intenta resolver símbolos si la carga tiene éxito.
2. `piglet-phase2-getconfig.elf`: añade una consulta
   `scePigletGetConfigurationVSH` y vuelca 128 bytes de un buffer opaco de
   1024 bytes. No llama `SetConfiguration`.
3. `piglet-phase3-egl-init.elf`: añade `eglGetDisplay`, `eglInitialize`,
   `eglTerminate`.
4. `piglet-phase4-clear-swap.elf`: añade config ES2, ventana candidata PS4,
   contexto, un clear azul y un swap, seguido de cleanup completo.

Todas las fases:

- cargan explícitamente el módulo de `system_ex`;
- registran cada símbolo resuelto y código de error;
- tienen watchdog de proceso de 12 segundos;
- escriben `/data/ps5-piglet-probe.log` con `fsync`;
- hacen `eglTerminate`/destrucción/`dlclose` cuando corresponde;
- no parchean módulos ni llaman `scePigletSetConfigurationVSH`;
- no incluyen un target automático de deploy/run.

Los cinco ELFs compilan sin warnings con `-Wall -Wextra -Werror` y el
toolchain local Prospero.

## Riesgos y criterio de parada

- Fase 1 es la más segura: puede fallar por sandbox/permisos o dependencias del
  módulo, pero no inicializa GPU.
- Fase 2 usa la firma candidata `int(void*)`. El buffer sobredimensionado reduce
  el riesgo de ABI, pero una firma diferente aún puede terminar el proceso.
- Fase 3 puede bloquearse dentro del backend/IPC; el watchdog fuerza salida del
  proceso, aunque no garantiza revertir estado global defectuoso del driver.
- Fase 4 usa la ventana PS4 candidata y ya puede tocar presentación/GPU. Sólo se
  debe ejecutar si las fases 1–3 terminan limpiamente.
- Un fallo de fase 3 sin `SetConfiguration` no descarta definitivamente GLSlim:
  puede demostrar precisamente que PS5 exige una configuración válida. En ese
  caso, el siguiente paso correcto es recuperar/decompilar el ABI PS5 de
  `Get/SetConfiguration`, no copiar flags PS4.

## Próxima acción manual

Con el juego cerrado y después de relanzar el host homebrew, ejecutar **sólo**
`piglet-phase1-resolve.elf`. Esperar como máximo 15 segundos, cerrar
`FAKE00000` si queda negro y recuperar `/data/ps5-piglet-probe.log`. No avanzar
a fase 2 hasta revisar ese log y confirmar que el módulo se descargó al salir.

## Resultado en hardware — fase 1

Ejecutado en PS5 12.02 mediante `hbldr -> FAKE00000`:

```text
PS5 GLSlim probe phase 1 start; no patches, no SetConfiguration
dlopen /system_ex/common_ex/lib/libSceGLSlimVSH.sprx: failed
dlerror: error_code=0xffffffff
phase 1 exit rc=10
```

El watchdog no intervino y no se llamó ninguna API EGL/Piglet. La carga directa
por pathname queda descartada para este host. Esto no prueba que GLSlim sea
inaccesible: el firmware lo cataloga como sysmodule interno `0x800000a9`, por
lo que el próximo probe debe intentar únicamente
`sceSysmoduleLoadModuleInternal(0x800000a9)` y después repetir la resolución de
símbolos. No se debe ejecutar fase 2 con el módulo sin cargar.

## Resultado en hardware — fase 1B

Ejecutado en el mismo host mediante `hbldr -> FAKE00000`:

```text
PS5 GLSlim probe phase 1B-sysmodule start; no patches, no SetConfiguration
sceSysmoduleLoadModuleInternal(0x800000a9) rc=0x80020063
phase 1 exit rc=10
```

El identificador `0x800000a9` coincide con la tabla `sysmodtab` del SDK local,
pero no existe en los headers locales una definición fiable de
`0x80020063`. Por tanto, la conclusión comprobada se limita a que el cargador
interno rechazó la solicitud desde este host; no se etiqueta todavía como
“permiso denegado”, “módulo ausente” ni “ID inválido”. No se llamó `dlopen`
después del rechazo, ni ninguna función EGL/Piglet.

Con dos rutas soportadas fallidas —pathname e internal sysmodule— no se debe
avanzar a las fases 2–4. La evidencia actual confirma que GLSlim está presente
en el firmware y es usado por `SceNKUIProcess`, pero no que sea consumible por
`FAKE00000`. Cualquier prueba siguiente debe investigar primero el contexto de
carga o las dependencias estáticas del proceso autorizado, sin parches.
