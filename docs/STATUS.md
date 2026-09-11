# Estado del proyecto

Última reconciliación: 2026-09-05, firmware PS5 12.02.

> **Estado canónico:** la extracción descrita cronológicamente abajo culminó en
> `projects/ps5-agc-gears`, hoy standalone, público y validado hasta 60.000
> frames. Para trabajo vigente usar `CURRENT.md`; los nombres Stage A–I son
> historia experimental bajo `legacy/`.

## Observabilidad histórica de PPSA99998

`PPSA99998` usó `ps5log/1` estructurado sobre TCP, sin archivos de log en la
consola ni mounts USB. La regresión pre-entry `0x80aa001a` era un bug del linker:
usaba el file offset de `.got` como comienzo de RELRO, aunque la región empieza
en `.data.rel.ro`. Al crecer el binario con el logger podía producir un
`PT_LOAD` incongruente respecto a páginas de 16 KiB. Se portó el arreglo de
ProsperoLight y se añadió el gate de congruencia. El smoke corregido arrancó
con `0x00006018` y entregó HELLO, ocho registros sin gaps y BYE limpio;
`LOG_INIT_RESULT=0`.

La tabla real de exports se obtuvo read-only desde `libSceNet.sprx` cargada por
`SceShellUI` y se importó privadamente en Ghidra como
`/gpu/fw1202-libSceNet.system-view.elf`. Los 12 NIDs usados por el adaptador
existen en FW 12.02 y aparecen en el fSELF fallido; SONAME, módulo y biblioteca
también coinciden como `libSceNet.prx`/`libSceNet`. Por tanto, “NID ausente o
incorrecto” queda descartado. El cruce reproducible está en
`research/gpu/tools/verify_fw_net_imports.py`; no contiene bytes propietarios.
`tools/agc_net_monitor.py` sigue el transcript local, valida el manifiesto y
archiva evidencia inmutable en `research/gpu/captures/runtime/`. Exige boot
token coincidente, cero gaps/RAW/oversized, BYE exacto, tamaño/hash y guard
fail-closed. Contrato completo: `docs/OBSERVABILITY.md`.
`make agc-check` sigue siendo el gate offline obligatorio antes de cada
build/deploy: ejecuta las 34 pruebas del subsistema de observabilidad y todos
los contratos independientes del frame loop. El runner garantiza muestra inicial,
cadencia de 60 frames, errores inmediatos y resumen terminal.

## Resultado principal

Native Label v5 demostró ejecución GPU real desde la aplicación homebrew nativa
`PPSA99998`:

- `sceAgcInit(&state, 8) = 0`;
- memoria propia `type=0x0c` mediante BatchMap `protection=0xf2`, `processed=1`;
- `sceAgcDriverSubmitDcb = 0` para un DCB de 15 DWORD;
- `DMA_DATA`: `target 0xa5a55a5a -> 0`;
- `RELEASE_MEM`: `fence 1 -> 0`, posterior al target;
- target `+0x1000` y fence `+0x1100` en líneas de caché separadas;
- scrub, BatchUnmap, releases, descarga AGC y cierre exacto completados;
- `ps5debug`, FTP, `shsrv` y `elfldr` saludables después del cierre.

Stage B añadió presentación VideoOut con evento exacto y teardown. Stage C
escaló después el fill privado, sin VideoOut ni shaders/draw, a 256 B, 4 KiB y
64 KiB; verificó por CPU target, canarios y todo el exterior en cada escalón.
Stage D rellenó por GPU y presentó un backbuffer completo de 8,5 MiB; el color
fue confirmado visualmente y toda la transacción terminó limpia. Evidencia
vigente: `research/gpu/captures/agc-stage-d-runtime.json`.

## Qué queda demostrado

- Aplicación PS5 nativa propia desplegada mediante ShadowMountPlus.
- Inicialización pública de AGC, command fetch y ejecución de DCB propio.
- Memoria directa propia visible para CPU y GPU.
- `DMA_DATA`, fence de ownership y cleanup seguro.
- Construcción/link CPU de shaders dentro de memoria directa propia.
- VideoOut 4K, evento de flip, AudioOut y DualSense en probes separados.
- Heap hasta 432 MiB; Main Direct Memory hasta 4 GiB bajo carga combinada.
- `jitshm` con doble mapping RW/RX y ejecución multihilo.

## Frontera activa

Stage E ya ejecutó el pipeline completo con shaders propios `gfx1013`, defaults
por selector semántico y registros `84/12/3`. La causa del stall era precisa:
los paquetes indirectos CX/UC/SH codificados a mano ocupaban cuatro DWORD,
mientras los builders nativos del firmware emiten cinco. Tras usar
`sceAgcDcbSetCxRegistersIndirect`, `sceAgcDcbSetUcRegistersIndirect`,
`sceAgcDcbSetShRegistersIndirect` y `sceAgcDcbDrawIndexAuto`, el submit completo
alcanzó fence cero y evento VideoOut exacto.

El primer fullscreen triangle propio con pixel shader verde modificó 2.073.600
de 2.073.600 palabras del render target. La prueba visual inequívoca posterior
dibujó un triángulo pequeño verde centrado sobre fondo morado: cambió exactamente
285.120 píxeles, alcanzó fence cero y evento VideoOut exacto, sostuvo la imagen
5 s y completó todo el teardown. El operador confirmó visualmente el triángulo.
Evidencia final:
`research/gpu/captures/agc-stage-e-centered-triangle-runtime.json`.

La API reutilizable resultante está en `sdk/agc`. Expone 16 imports confirmados
de `libSceAgc` y `libSceAgcDriver`, sus firmas sanitizadas, facades de enlace,
un manifiesto de NIDs deterministas y el helper acotado
`ps5AgcDcbFillL2Sync`. Stage E ya compila usando estos stubs compartidos. Los
NIDs-only cuyo orden de argumentos no está cerrado permanecen fuera del header.

La prueba intermedia de doble buffer descartó wait/flip como causa del stall;
su captura se conserva como evidencia histórica en
`research/gpu/captures/agc-stage-e-double-buffer-isolation-runtime.json`. La
causa quedó resuelta después: el tamaño incorrecto de los indirectos manuales.

El gap de metadata gráfica quedó eliminado: LLPC/PAL genera un ELF
propio `gfx1013`, cuya metadata se traduce a 10 CX pre-raster, 9 CX pixel, seis
SH por etapa, specials, exports y modifier de draw derivado del mapa público de
`BaseVertex/BaseInstance`. El contrato técnico del gate visual pasa para el
checkpoint 6 y permite iteraciones clasificadas y acotadas. El directorio local
`build-gfx1030` conserva su nombre histórico únicamente para no invalidar el
cache absoluto de CMake; ese nombre no describe el target del artefacto.

## Capacidades aún no demostradas

- Texturas, samplers, entrada y audio.

## Gate Stage G preparado

El control G/21 sin logging entró en la aplicación y presentó un frame azul el
2026-09-05. Esta observación confirma ejecución, pero no sustituye todavía la
evidencia de fence/evento/guardas/cleanup que exige el gate completo. Captura:
`research/gpu/captures/agc-stage-g21-no-logging-control-runtime.json`.

La primera ejecución G/21 con linker y logging corregidos alcanzó
`stage_e_submit=0` tras configurar D32 y los 21 pares. El proceso terminó sin
fence/evento/BYE, por lo que queda clasificada como incompleta y no cierra aún
G/21. La frontera observada está después del submit, no en el loader. La causa
candidata concreta era que la tabla de 21 pares se encontraba en el stack:
`SetCxRegistersIndirect` conserva su dirección para consumo posterior de la
GPU, mientras que las tablas Stage E demostradas viven en memoria directa.

La iteración siguiente mueve los 22 pares a `shader + 0x3e00`, dentro
de la arena directa persistente y antes de la geometría en `0x4000`. El adapter
indirecto rechaza ahora cualquier span que no esté íntegramente dentro de esa
arena, incluidos overflow y cruce de límite; Stage I comparte el mismo puntero
persistente. El gate host, las builds G/I y sus verificadores pasan.

G/21 fue repetido en hardware con el fSELF SHA-256
`6f5d1bd7153f152a26847d8aa3b74c4a36d4cd91afd9fcd73ba6dc3f83526ba3`.
Alcanzó submit cero, fence cero, 1.013.074 palabras modificadas por GPU,
guardas intactas, recovery intacto, evento VideoOut exacto, BYE sin gaps y
teardown completo. La causa stack/no-visibilidad queda confirmada por la
comparación entre ambas ejecuciones. El operador confirmó un cubo 3D centrado
sobre un fondo uniforme durante el hold visible.

Evidencia:
`research/gpu/captures/runtime/20260905T105717802Z_PPSA99998_agc-native-sce_0x989598b55e8.capture.json`.

El estacionamiento posterior al éxito era deliberado: aun tras cleanup y BYE,
`main()` ejecutaba `pause()` indefinido por una política heredada de los probes.
Una primera variante que retornaba `0` cerró el BigApp, pero el shell mostró
después “Something went wrong with this game or app”; no constituye cierre
limpio. La variante siguiente conservó el mismo teardown demostrado y usó
`_exit(0)` para omitir los handlers `atexit`/teardown del CRT: volvió al menú
sin diálogo y `PPSA99998` desapareció de BigApp. Los estados ambiguos conservan
`park()` y nunca se auto-cierran. Artefacto confirmado:
`850a8938c8bd1e4bd3b446e8e84c1013f201d3c8c4febfd5d4d7120ac43991c5`.
Evidencia:
`research/gpu/captures/runtime/20260905T111706374Z_PPSA99998_agc-native-sce_0xa9e14ec374e.capture.json`.

El bloque depth inline incompleto fue sustituido por
`legacy/probes/ps5-agc-phase0/stage_g_depth_state.c`. El constructor host-tested genera
21 registros para una vista D32 `64KB_Z_X` completa sin HTILE y mantiene
`DB_DEPTH_CONTROL` como el registro 22 separado. Stencil/HTILE quedan realmente
sin direcciones; se añadieron render/cache overrides y polygon-offset exigidos
por PAL. G/21 programa sólo los primeros 21 y valida el bind sin depth test.
G/22 cambia exclusivamente el count a 22: en hardware completó submit, fence,
evento, guardas, teardown y `_exit(0)`. El operador confirmó el cubo y tres
caras con oclusión visual coherente. Artefacto SHA-256:
`912056bc1e3739953589e3c56aa642905f3a1a2f7fbe9bf1130be2b338efa7e7`.
Evidencia:
`research/gpu/captures/runtime/20260905T112434738Z_PPSA99998_agc-native-sce_0xb06790cf17c.capture.json`.

El monitor inicialmente clasificó esa captura como `unknown_retain` porque su
lista de banners reconocía `Stage G v1` pero no `Stage G/22 v1`. El guard y su
regresión fueron corregidos; la transcripción original ahora clasifica como
`present_complete`. Fue un defecto de observabilidad, no del runtime.

Stage G/23 aisló la semántica con dos quads solapados y orden adversarial:
primero el cercano brillante y después el lejano oscuro. Las variantes OFF/ON
comparten geometría, shaders, transformación y draw; sólo difieren en consumir
21 o 22 pares. OFF mostró oscuro y ON brillante durante holds de 10 segundos;
el operador confirmó que la diferencia era muy notable. Ambos runs tuvieron
submit/fence/evento/guardas/teardown completos y salida limpia. Evidencias:
`research/gpu/captures/runtime/20260905T114313927Z_PPSA99998_agc-native-sce_0xc0b0cfa8324.capture.json`
y
`research/gpu/captures/runtime/20260905T114356949Z_PPSA99998_agc-native-sce_0xc151131191c.capture.json`.

El staging publicable avanzó en paralelo sin tocar el runtime bloqueado:
`gears_mesh` genera triangle lists interleaved de 24 bytes y `gears_scene`
produce exactamente los 25 DWORD de user data para cada uno de tres draws
(MVP, quaternion unitario, material y puntero SRD). Ambos tienen tests host,
compilan con el toolchain PS5 y sólo requieren `sincosf` de
`libSceLibcInternal`; la auditoría publicable pasa con 34 archivos allowlisted.

Stage H quedó validado en hardware el 2026-09-05. Empaqueta
los shaders lit-Gears propios (GS 384 B, PS 160 B), genera las tres mallas/SRD,
materializa tres bloques directos de 25 DWORD y emite tres `DrawIndexAuto` en
un submit. Tras aprobar G/23, consume los 22 pares depth. En consola produjo
tres gears 3D diferenciadas y el operador calificó el resultado de
impresionante. El run completó tres draws/90 DWORD, submit, fence, 255.083
palabras modificadas, evento, guardas, teardown y salida limpia. fSELF:
`5f510b7572e04a32d3c0988b989aef64b6488ddf44dcb19cdef3477deebedbf3`.
Evidencia:
`research/gpu/captures/runtime/20260905T115308530Z_PPSA99998_agc-native-sce_0xc957db3aa4d.capture.json`.

Dos fallos pre-submit ayudaron a sanear el contrato: `main` seleccionaba la
metadata Cube 264/140 en vez de Gears 384/160, y el compositor atribuía por
error 7 DWORD a `DrawIndexAuto`. La función FW 12.02 emite exactamente 3 DWORD;
cada par SH-direct/draw mide 27+3 y los tres suman 90. Ambos errores tienen
regresiones offline y no produjeron trabajo GPU pendiente.

La base del frame loop ya tiene un state machine publicable y probado para dos
buffers. Asigna tokens positivos monotónicos de 48 bits, permite cancelar sólo
antes del submit y prohíbe reutilizar una arena/backbuffer hasta recibir tanto
el fence GPU como el evento VideoOut exacto del mismo token.

El Stage H privado ya usa el mismo compositor publicable que se entregará:
tres pares SH-direct/draw, con avances exactos 27+3 DWORD y total 90. Un
cambio de ABI o falta de command capacity detiene la composición antes de
submit. El fSELF offline actual es
`b4532c0f3f6ab331409c1c6666d3f2aa4a18ef6a6e6eba8f42d714e5e5c83e54`;
su existencia sigue sin contar como evidencia hardware.

El controlador `gears_animation` une timestamp monotónico, selección alterna
de backbuffer, parámetros de los tres draws y tracker de ownership. Su soak
host de 10.000 frames confirma tokens consecutivos, rechazo de eventos cruzados
y la exigencia fence+VideoOut antes de reutilización. Compila con el toolchain
PS5 sin imports externos propios; sus únicos símbolos pendientes pertenecen a
los módulos internos `gears_scene` y `gears_frame_tracker`.

La observabilidad del futuro loop también está materializada: telemetría en
memoria para compose/GPU/VideoOut, promedios, máximos, deadlines y errores. Se
transmite frame 0, cada 60 frames, errores y resumen final mediante `ps5log/1`;
el runtime no escribe archivos. Su prueba de 10.000 frames y la auditoría
publicable pasan.

Stage I enlaza esos módulos al runtime privado y quedó aprobado en hardware el
2026-09-05. Construyó dos pipelines para los backbuffers y completó 300/300
frames animados: wait-safe, clear DMA histórico de color y D32, bind depth de
22 pares, pipeline alterno, tres draws, SetFlip, fence y evento exacto. Esa
primera revisión terminó con
resultado cero, guardas de color/depth intactas, cero errores, BYE y teardown
completo. La captura canónica es
`research/gpu/captures/runtime/20260905T120527429Z_PPSA99998_agc-native-sce_0xd4186f0c894.capture.json`.
El SHA-256 del fSELF ejecutado es
`0acab82e79e1a0a6685367a6f84c63b78b75d8992623d68b18fa23860ebb4292`.

La telemetría de la primera versión midió aproximadamente 2,2 us de composición, 1,10 ms de espera
GPU y 15,55 ms de espera VideoOut en promedio. Marcó 291/300 misses frente al
umbral estricto de 16,666667 ms: no son fallos de render, sino evidencia de que
el loop serial sumaba fence y VideoOut más overhead. La revisión vigente cerró
ese gate solapando exactamente dos slots sin debilitar ownership.

La revisión cinemática posterior sustituyó los solapes visuales arbitrarios
por un tren 20:10:10: centros a suma de radios primitivos, contacto diente-hueco
y velocidad opuesta 2:1. Pasó la regresión geométrica y otra ejecución de
300/300 frames, cero errores, guards y teardown completos. fSELF
`8bbbc020220b7975fe1ba0b1ba0fbc450ecff962254878df704bf15fb233c16b`;
captura
`research/gpu/captures/runtime/20260905T121438262Z_PPSA99998_agc-native-sce_0xdc1c6afd099.capture.json`.

La implementación vigente ya usa el generador original de Mesa `es2gears.c`
(MIT, revisión `649baedafcb90313ade69909fdef1ee156ab5f8d`) adaptado de strips a
listas AGC. Conserva radios, espesores, layout y fases, escalados uniformemente.
En hardware completó 300/300 frames con 1.200/600/600 vértices, cero errores y
teardown limpio. fSELF
`ba5a862097bbd6aa13428f0050537ef5a91daaae4bc1d86c243bd8aef5497be8`;
captura
`research/gpu/captures/runtime/20260905T122247659Z_PPSA99998_agc-native-sce_0xe33b89e3f2d.capture.json`.

Los soaks Stage I quedaron aprobados el 2026-09-05. El gate de 1.000 completó
1.000/1.000 con cero errores; fSELF
`676f2345449123aadb879935cebb737759c05dcfd20b6074e56d3f3c75e717bb`,
captura
`research/gpu/captures/runtime/20260905T123033935Z_PPSA99998_agc-native-sce_0xea04874b86a.capture.json`.
El gate de 10.000 completó 10.000/10.000, también con cero errores, guardas
intactas, fence GPU cero, evento VideoOut exacto y teardown completo; fSELF
`868ef4c150ef800c4f73d60ce6b89e0f98f6d5a7cc44f2d6f198f94701c23ca7`,
captura
`research/gpu/captures/runtime/20260905T123120692Z_PPSA99998_agc-native-sce_0xeab2b589547.capture.json`.
El promedio final fue ~2,24 us compose, ~1,10 ms GPU wait y ~15,56 ms
VideoOut wait. Los 9.671 deadline misses confirman de forma estable el coste
del scheduling serial; no hubo deriva, corrupción ni error AGC.

El soak pipelined definitivo completó 10.000/10.000 con
`max_frames_in_flight=2`, cero errores, guardas intactas, fences finales cero,
evento VideoOut exacto y teardown limpio. El intervalo global fue 16.682.904
ns/frame (59,9416 fps); compose/GPU/VideoOut promediaron 2.218 ns, 1.103.477 ns
y 15.561.916 ns. fSELF
`f05759892259dc0087273d4e2038722a0f2eb2ec17f132118a0fd887e0472234`;
captura
`research/gpu/captures/runtime/20260905T124347472Z_PPSA99998_agc-native-sce_0xf590a3bdbe1.capture.json`.

El clear de color ya no usa DMA en la implementación vigente. Un draw
fullscreen reutiliza el pipeline `gfx1013` antes de las tres gears; depth sigue
teniendo clear independiente. La variante final negra superó 10.000/10.000 a
59,9407 fps, con profundidad dos, cero errores y todos los contratos terminales
intactos. fSELF
`7b24d5f152f82584e5af1a9d906699b75f5527764db469189346f6017b284dc2`;
captura
`research/gpu/captures/runtime/20260905T125654862Z_PPSA99998_agc-native-sce_0x10105db257eb.capture.json`.

El orden de comandos publicable también fue extraído a `gears_renderer`: clear
más tres gears, cuatro draws y 120 DWORD exactos. El runtime privado ya consume
esa unidad y el artefacto refactorizado completó 300/300 con todos los contratos
intactos. fSELF
`00758b10ebcbc426ccaf59e3c600492fe9aa2b78262b576d3edc106c8510bd00`;
captura
`research/gpu/captures/runtime/20260905T130239074Z_PPSA99998_agc-native-sce_0x10608212d49a.capture.json`.

## Fuentes de verdad

- Plan vigente: `docs/ROADMAP.md`.
- Contrato Stage E: `research/gpu/STAGE_E_TRIANGLE.md`.
- Readiness: `research/gpu/captures/minimal-gpu-readiness.json`.
- Evidencia v5: `research/gpu/captures/agc-native-label-v5-runtime.json`.
- Historial: `research/gpu/captures/` y análisis bajo `research/gpu/`.
