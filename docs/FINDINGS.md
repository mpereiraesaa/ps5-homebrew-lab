# Hallazgos confirmados

Este archivo distingue resultados observados de hipótesis. No convertir una
prueba mínima en una afirmación general sin añadir evidencia.

## Rechazo pre-entry por origen RELRO incorrecto

Una integración de `libSceNet` amplió el fSELF de `PPSA99998` y produjo
`0x80aa001a` antes de `main()`. El control sin logging arrancó y presentó un
frame, mientras el smoke con red fallaba aunque sus doce NIDs, SONAME, módulo y
biblioteca coincidían con `libSceNet.sprx` de FW 12.02.

La causa estaba en `sce_module_writer.cpp`: usaba `got.file_offset` para el
segmento RELRO, pero `relro_start` corresponde a `.data.rel.ro`. `.got` está
dentro de la región, no necesariamente al comienzo. El layout más grande hizo
visible la incongruencia entre file offset y virtual address para páginas de
16 KiB.

El arreglo ancla ambos lados en `.data.rel.ro` y valida para cada `PT_LOAD`
mapeado que `p_offset % 0x4000 == p_vaddr % 0x4000`. Tras reconstruir también
el binario host `ps5-native-tool`, el smoke arrancó, conectó a `ps5logd` y
entregó HELLO, ocho registros secuenciados y BYE limpio. Cambiar sólo el source
sin reconstruir la herramienta conserva el fallo.

La corrección y su test viven en el fork local publicable de
`third_party/ps5-native-app-boilerplate`; no dependen de dumps ni constantes
propietarias.

## WebKit

El probe visual confirmó:

- Canvas 2D, `requestAnimationFrame`, `fetch`, WebSocket y localStorage.
- Sin WebAssembly, WebGL 1/2, Web Audio, AudioWorklet, Gamepad API ni IndexedDB.

Decisión: WebKit puede servir como menú o panel de control, pero no es una base
adecuada para ports exigentes o emulación en este entorno.

## Host de homebrew nativo

Ejecutar el ELF directamente con `elfldr` no proporcionó presupuesto de memoria
directa: los allocators devolvieron `0x80020023`. Ejecutarlo mediante `hbldr`
dentro de `FAKE00000` sí habilitó la memoria y las APIs multimedia.

VideoOut observado:

- Resolución: 3840x2160.
- Pitch registrado: 3840x2176.
- Doble buffer y eventos de flip funcionando.

También se comprobaron ScePad, SceAudioOut y salida del BigApp mediante
`sceSystemServiceGetAppIdOfRunningBigApp()` + `sceSystemServiceKillApp()`.

## JIT: qué está demostrado

El probe escribió código máquina `mov eax, imm32; ret` en memoria anónima y lo
invocó como función:

- `RW -> RX`: devolvió 42.
- `RX -> RW -> RX`: tras reescribirlo devolvió 43.
- Mapeo RWX: devolvió 99.

El stress probe escribió y ejecutó una función distinta en cada página de 16
KiB:

| Tamaño | Páginas comprobadas | Resultado |
| ---: | ---: | --- |
| 1 MiB | 64 | correcto |
| 16 MiB | 1.024 | correcto |
| 64 MiB | 4.096 | correcto |
| 128 MiB | 8.192 | correcto |

Esto prueba ejecución dinámica asistida por el jailbreak/SDK, no una API JIT
oficial de Sony ni compatibilidad automática con cualquier runtime.

### Concurrencia

- Cuatro hilos alternando `RW/RX` sin sincronización: fallo `rc=-2`.
- Cambios de permisos protegidos por mutex: también apareció `rc=-2`.

Hipótesis pendiente: el wrapper privilegiado modifica entradas completas del
mapa virtual y regiones vecinas pueden compartir una entrada. Hace falta
inspeccionar el mapa y probar guard pages, RWX concurrente y/o doble mapeo.

### Doble mapeo `jitshm`

Se creó un objeto JIT de 16 MiB y un alias con las APIs `sceKernelJit*`. Los
handles se mapearon en dos direcciones virtuales distintas que apuntan a las
mismas páginas físicas:

- Vista de escritura: RW, nunca ejecutable.
- Vista de ejecución: RX, nunca escribible.

Escribir por RW y ejecutar por RX devolvió correctamente 1234 en la primera
página y 5678 en la última. Después se ejecutaron 100.000 ciclos por worker:

| Workers | Verificaciones | Errores | Millones de ciclos/s |
| ---: | ---: | ---: | ---: |
| 1 | 100.000 | 0 | 24,07 |
| 4 | 400.000 | 0 | 42,47 |
| 8 | 800.000 | 0 | 77,34 |
| 12 | 1.200.000 | 0 | 108,57 |
| 16 | 1.600.000 | 0 | 118,43 |

Decisión provisional: usar doble mapeo `jitshm` para un allocator JIT. Evita
RWX y elimina transiciones de permisos durante el funcionamiento. Las tasas son
de un microbenchmark y no predicen directamente el rendimiento de un emulador.

## CPU e hilos

`sysconf()` informó 16 CPUs configuradas y online. Una carga aritmética
independiente por worker produjo aproximadamente 1x, 2x, 4x, 6x, 8x y 12x hasta
12 workers. Con 16 workers el rendimiento agregado cayó a aproximadamente 8x.

`pthread_getaffinity_np()` falló en todos los workers, así que la máscara real
no fue obtenida. No se ha determinado todavía si el comportamiento a 16 se debe
a presupuesto del BigApp, scheduling, SMT o interferencia del sistema.

La interfaz más directa `cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID,
-1, ...)` también devolvió `ERANGE` con buffers de 32, 64, 128 y 256 bytes.
La syscall está presente, pero su ABI o parámetros para PS5 todavía no están
resueltos. No confundir este resultado con una denegación de permisos.

## Presupuestos de memoria

El BigApp reportó estos límites:

- Apertura total de Direct Memory: 12 GiB.
- `RLIMIT_DATA`: 32 GiB.
- Stack: 2 MiB.
- Espacio virtual: ilimitado (`INT64_MAX`).

Los límites POSIX no equivalen al presupuesto realmente asignable. La prueba
escribió y leyó una vez cada página de 16 KiB para evitar falsos positivos por
reservas virtuales sin respaldo.

### Heap/flexible anónimo

- 128, 256, 320, 384, 400, 416 y 432 MiB: correctos.
- 448 y 512 MiB: fallo inmediato con `ENOMEM`.

El máximo observado está entre 432 y 448 MiB en este host. Recomendación
provisional: presupuestar 320 MiB normalmente o hasta 384 MiB para aplicaciones
exigentes, conservando margen para librerías, stacks y fragmentación.

### Main Direct Memory

- 128, 256, 512 MiB, 1 GiB y 2 GiB: asignados, mapeados y verificados.
- `sceKernelGetDirectMemorySize()` reportó 12 GiB.

### Carga combinada

Se mantuvieron simultáneamente 320 MiB de heap tocado, 64 MiB de `jitshm` con
doble mapeo y una arena Main Direct Memory. Se verificaron todas las páginas,
se reescribió y ejecutó código JIT bajo carga y se mantuvo el conjunto 15 s:

| Main Direct | Total combinado | Resultado |
| ---: | ---: | --- |
| 3 GiB | 3.375 GiB | correcto |
| 4 GiB | 4.375 GiB | correcto |

Después se ejecutó un soak multimedia de 179 s con todos estos recursos activos
simultáneamente:

- 3 GiB de Main Direct Memory, tocados y muestreados durante la prueba.
- 320 MiB de heap anónimo.
- 64 MiB de `jitshm`, reescribiendo por RW y ejecutando por RX.
- 128 MiB de memoria directa reservada para doble buffer 3840x2160.
- VideoOut, AudioOut, DualSense y 8 workers de cómputo.

El total contabilizado por el probe fue 3.5 GiB y terminó con `rc=0`. La
apertura de 12 GiB no constituye un presupuesto seguro. Recomendación actual:
diseñar inicialmente para hasta 3 GiB directos de aplicación. Los 4 GiB están
demostrados sólo en la prueba combinada corta de 15 s y siguen siendo un modo
experimental hasta repetir el soak multimedia con ese tamaño.

## Ports nativos frente a emulación

Un juego con fuentes portables normalmente se compila AOT a x86-64 y no necesita
JIT. Quake y source ports semejantes requieren adaptar vídeo, audio, entrada,
archivos, red y build. Los datos comerciales del juego siguen siendo necesarios.

El JIT resulta relevante para recompiladores dinámicos de emuladores y algunos
runtimes. Un emulador también puede usar un intérprete, con menor rendimiento.

## Experiencia previa relevante para GPU

El workspace contiene resultados de mods gráficos que el usuario confirmó en
la misma PS5: conversiones de texturas y modelos procedentes de PC para títulos
de Capcom (incluidos RE2 y RE4 Remake) y GTA San Andreas basado en Unreal
Engine. Hay reportes de build y herramientas de inspección live asociados.

Esto demuestra experiencia y compatibilidad en la capa de assets —formatos,
swizzles/layouts, empaquetado y requisitos del motor—. Esa experiencia no fue
por sí sola prueba de ejecución GPU propia; la prueba independiente llegó
después con Native Label v5: un ELF nativo inicializó AGC, sometió un DCB y
obtuvo escritura `DMA_DATA` más completion `RELEASE_MEM`. Stage E completó
después la etapa separada de shaders, draw y presentación visible.

## Inventario GPU inicial

Una captura read-only del menú enumeró 93 procesos. No había aplicación en
foreground. `AgcCompositor.elf` tenía mapeados `libSceAgcDriver.sprx`,
`libSceAgcVsh.sprx`, una región `SceAgcDriver` y otra
`GpuClearStateGuardData`. SceShellUI y varios servicios también cargaban
`libSceAgcVsh.sprx`. No apareció `libSceGnmDriver` en los nombres de mapas.

Evidencia: AGC está activo en el camino gráfico del sistema PS5 observado.
Inferencia provisional: debemos investigar AGC antes de GNM. Esto no prueba aún
qué API está disponible para BigApp ni que GNM sea inutilizable.

El inventario del host `FAKE00000` durante el probe VideoOut mostró el proceso
runtime `SceCloudClientApp`. Cargaba VideoOut, AudioOut, Pad y soporte del
sistema, pero ningún mapping nombrado AGC, GNM o GPU. Por tanto, registrar y
presentar un buffer no carga automáticamente el driver de render.

Una captura posterior de un juego PS5 nativo mostró `libSceAgc` y
`libSceAgcDriver` en su `eboot.bin`, junto con memoria dedicada para traps, EOP,
CWSR, ACQRB, ding-dong, register shadow y diagnósticos. Ésta es la primera
diferencia estructural confirmada respecto a `FAKE00000` y define AGC como el
objetivo primario de ingeniería inversa.

### AGC dentro de `FAKE00000`

El sysmodule AGC `0x80000094` carga y descarga con retorno cero mediante
`hbldr -> FAKE00000`. Sin embargo, durante su constructor registra
`FS Table offset has shifted. This is not survivable.` La rama que genera ese
mensaje compara una dirección derivada de la DMEM de AGCDriver con el valor fijo
`0xfe0040000`. Esa dirección sí pertenece al mapping `SceAgcDriver` de los dos
juegos nativos estudiados.

Por tanto, el loader acepta AGC pero su layout interno no queda validado para
uso en este host. No se deben interpretar los retornos cero como permiso para
submit. Las pruebas fase 0/0B no llamaron APIs AGC ni enviaron trabajo GPU y
terminaron con descarga del módulo y cierre limpio/verificado de `FAKE00000`.

## Stage E: draw acelerado confirmado

`PPSA99998` creó y enlazó shaders propios compilados para `gfx1013`, construyó
un pipeline `84/12/3` y sometió un DCB de 122 DWORD. El resultado fue un
triángulo verde centrado sobre fondo morado, confirmado visualmente y por
lectura CPU de exactamente 285.120 píxeles modificados. Fence, evento VideoOut,
guardas, buffer de recuperación y teardown pasaron.

El fallo anterior no era ausencia de GPU ni incompatibilidad del shader: el
compositor manual suponía indirectos CX/UC/SH de cuatro DWORD, mientras los
builders nativos de FW 12.02 emiten cinco. La ruta vigente usa exclusivamente
los builders nativos para esos paquetes y para `DrawIndexAuto`.

Evidencia canónica:
`research/gpu/captures/agc-stage-e-centered-triangle-runtime.json`.

## G/21: procedencia de tablas indirectas

El primer G/21 con telemetría alcanzó `SubmitDcb=0` y terminó antes de emitir
fence, evento, watchdog o BYE. La revisión del compositor encontró una
diferencia respecto al Stage E demostrado: `depth_registers[22]` era una
variable automática de `main()`. El builder `SetCxRegistersIndirect` no copia
sus pares al DCB; codifica count y dirección de la tabla para que el command
processor la lea después. Un puntero válido para CPU no implica visibilidad
GPU, y el stack no pertenece a las arenas directas declaradas.

La corrección candidata reserva los pares en `shader + 0x3e00`, un span de
`0xb0` bytes que no solapa los dos pipelines Stage I ni la geometría que inicia
en `0x4000`. `stage_gpu_span_visible()` valida containment completo y overflow,
y el adapter lo exige para CX/UC/SH indirectos. Hay una regresión host que
acepta los límites exactos y rechaza stack simulado, cruces y wraparound.

`make agc-check` y las builds G/I pasan con esta corrección. La repetición G/21
en PS5 obtuvo submit cero, fence cero, 1.013.074 palabras del target cambiadas,
guardas/recovery intactos, evento VideoOut exacto, BYE y teardown completo. El
run anterior idéntico salvo la procedencia de la tabla terminaba después del
submit; por tanto el defecto de visibilidad del stack queda confirmado como la
causa del bloqueo G/21.

El operador identificó inequívocamente un cubo 3D centrado sobre un fondo
uniforme durante los cinco segundos de presentación.

Evidencia:
`research/gpu/captures/runtime/20260905T105717802Z_PPSA99998_agc-native-sce_0x989598b55e8.capture.json`.

## Lifecycle después de completion

El requisito histórico de usar Close Game no provenía de AGC ni de
ShadowMountPlus. El runtime liberaba correctamente VideoOut, memoria directa,
command mapping y módulo AGC, cerraba `ps5log/1`, y después se detenía a
propósito en `for (;;) pause()`. Sustituirlo por `return 0` conservó el contrato
GPU y retiró `PPSA99998`, pero el shell mostró después “Something went wrong
with this game or app”. Usar `_exit(0)` después del teardown explícito omitió la
ruta `atexit` del CRT y volvió al menú sin diálogo; el estado externo confirmó
que no quedaba BigApp. Éste es el patrón de éxito en FW 12.02. Los caminos
`park()` se mantienen exclusivamente para ownership/completion ambiguos.

## G/22: primer consumo depth confirmado

El sucesor de una sola variable de G/21 elevó
`stage_g_depth_register_count` de 21 a 22 y consumió
`DB_DEPTH_CONTROL=0xb6`. La captura conservó submit cero, fence cero, evento
VideoOut exacto, guardas/recovery intactos, scrub, teardown y salida limpia. El
operador vio el cubo con tres caras y oclusión coherente. Esto confirma que la
ruta completa no falla al habilitar depth; un litmus adversarial on/off sigue
siendo necesario para atribuir inequívocamente el resultado visual al test de
profundidad y no al orden actual de los triángulos.

## G/23: semántica LESS_EQUAL demostrada

El litmus usa dos quads exactamente solapados. Dibuja primero el cercano con
normal iluminada y luego el lejano con normal opuesta. En OFF, los 21 pares
mantienen depth desactivado y el segundo quad deja el centro oscuro. En ON, el
par 22 activa lectura/escritura `LESS_EQUAL`; el lejano falla y permanece el
centro brillante. Las entradas de build difieren únicamente por
`STAGE_G_DEPTH_ENABLE_TEST`, verificado por regresión host. La comparación se
repitió con holds de 10 segundos y el operador confirmó una diferencia fuerte.
Esto cierra tanto consumo como comportamiento del depth test D32 no-HTILE en
FW 12.02.

## Stage H: primera escena Gears

Stage H confirmó tres draws con shaders Gears propios. La geometría vigente,
derivada de `es2gears.c`, contiene 2.400 vértices totales (1.200/600/600).
El compositor emitió 90 DWORD: tres actualizaciones SH directas de 27 DWORD y
tres `DrawIndexAuto` de 3 DWORD. La antigua cifra 7 pertenecía a `DMA_DATA` y
era una atribución falsa; el builder de FW 12.02 fue verificado por su avance
de cursor de 12 bytes y el paquete `0xc0012d00`. También se corrigió la
selección de metadata para usar Gears 384/160 bytes en vez de Cube 264/140.

La ejecución final consumió los 22 pares depth, presentó 10 segundos, modificó
255.083 palabras, mantuvo guardas/recovery y completó teardown. El operador
confirmó inequívocamente las tres gears 3D y destacó la calidad visual.

## Stage I: animación y ownership por frame

Stage I completó 300 frames animados alternando dos backbuffers. Cada frame
usó un token positivo monotónico y no reutilizó su slot hasta observar tanto
el fence GPU como el evento VideoOut con el token exacto. Los 300 frames, los
guards de color/depth y el teardown terminaron sin errores.

La primera implementación privilegiaba corrección y serializaba GPU fence y espera
VideoOut dentro de cada frame. Esto explica 291 misses del presupuesto estricto
de 16,666667 ms aunque los promedios individuales fueran ~1,10 ms GPU y
~15,55 ms VideoOut. No implica un fallo AGC; identifica el siguiente trabajo:
Ese dato es histórico: la revisión vigente permite dos frames en vuelo y retira
cada slot sólo al completar sus dos condiciones de ownership.

La primera escena Stage I colocaba las mallas por criterio visual. Una revisión
intermedia probó distancias de radio primitivo, pero la referencia visual exigía
el perfil original. La versión vigente adapta el `es2gears.c` MIT de Mesa en la
revisión `649baedafcb90313ade69909fdef1ee156ab5f8d`: sus siete strips por diente
se expanden a 20 triángulos AGC sin degenerados, y conserva parámetros,
colocación relativa y fases 20:10:10. La ejecución previa completó 300/300
frames sin errores; captura intermedia:
`research/gpu/captures/runtime/20260905T121438262Z_PPSA99998_agc-native-sce_0xdc1c6afd099.capture.json`.

El port `es2gears` ejecutado contiene 1.200/600/600 vértices y también completó
300/300, guardas, fence/evento exactos y teardown limpio. fSELF
`ba5a862097bbd6aa13428f0050537ef5a91daaae4bc1d86c243bd8aef5497be8`;
captura
`research/gpu/captures/runtime/20260905T122247659Z_PPSA99998_agc-native-sce_0xe33b89e3f2d.capture.json`.

## Stage I: soaks 1K/10K

Los gates parametrizados exigen igualdad entre frames solicitados, completados
y verificados; una terminación parcial clasifica fail-closed. En hardware, los
soaks de 1.000 y 10.000 frames completaron exactamente sus conteos, sin errores
y con todas las condiciones de ownership y teardown satisfechas. En 10.000
frames los promedios permanecieron estables (~2,24 us compose, ~1,10 ms GPU y
~15,56 ms VideoOut). Los 9.671 misses de 16,666667 ms reproducen el overhead
serial histórico; no fueron errores de render.

## Stage I: pipelining 2-deep

El runner vigente somete dos frames antes de retirar el más antiguo y mantiene
command buffer y fence independientes por backbuffer. El soak hardware final
completó 10.000/10.000, reportó `max_frames_in_flight=2`, cero errores, guardas
intactas, fences finales cero, token VideoOut exacto y teardown limpio. El loop
midió 166.829.047.957 ns: 16.682.904 ns/frame, o 59,9416 fps. Los 9.999
`deadline_misses` miden latencia submit-a-retiro de cada frame bajo profundidad
dos; el intervalo global es la métrica correcta de throughput.

fSELF `f05759892259dc0087273d4e2038722a0f2eb2ec17f132118a0fd887e0472234`;
captura `research/gpu/captures/runtime/20260905T124347472Z_PPSA99998_agc-native-sce_0xf590a3bdbe1.capture.json`.

## Stage I: clear de color por pipeline

El color DMA fue sustituido por un triángulo fullscreen situado en el plano
lejano y emitido antes de las tres gears. El compositor publicable exige un
bloque SH de 27 DWORD y `DrawIndexAuto(3)` de 3 DWORD; capacidad insuficiente
falla antes de submit. Una variante verde completó 300/300 como prueba visual,
y la variante final negra completó 300/300 y después 10.000/10.000 con
`color_dma=false`, dos frames en vuelo, cero errores, guardas intactas, fences
cero, token exacto y teardown limpio. El soak midió 166.831.421.365 ns,
16.683.142 ns/frame (59,9407 fps).

fSELF `7b24d5f152f82584e5af1a9d906699b75f5527764db469189346f6017b284dc2`;
captura `research/gpu/captures/runtime/20260905T125654862Z_PPSA99998_agc-native-sce_0x10105db257eb.capture.json`.

## Módulos PRX propios (2026-09-06)

Gate ejecutado con el título `PPSA99999` y el módulo `hello.prx` construido por
`ps5-native-tool link --module` en la rama `exp/prx-module` del fork del
boilerplate. Evidencia canónica:
`research/gpu/captures/runtime/20260906T085730845Z_PPSA99999_prx-gate_0x519451728697.capture.json`.

Demostrado en FW 12.02:

- `sceKernelLoadStartModule("/app0/sce_module/hello.prx")` carga y arranca un
  módulo propio; `sceKernelGetModuleInfo` devuelve nombre y cuatro segmentos;
  las llamadas a sus exports y una import de kernel desde el módulo funcionan;
  `sceKernelStopUnloadModule` descarga limpio. Transcript sin gaps y BYE.
- Dos contratos del loader, hallados por bisección de unos veinte lanzamientos
  con una variable por iteración y aplicados en el conversor:
  `DT_PLTGOT` debe ser una tabla de tres entradas, porque el loader escribe
  las entradas 1 y 2 aunque no exista PLT y con un GOT de una entrada corrompía
  el module param y devolvía `0x80020063`; y `e_entry` se ejecuta como rutina
  de arranque y debe devolver 0, ya que el relleno `int3` daba SIGTRAP y un
  `ret` con `eax` basura daba `0x80020016`.

No disponible en FW 12.02 para módulos de aplicación:

- Carga por dependencia `DT_NEEDED`: el loader sólo carga las entradas
  conocidas de `sce_module` como `libc.prx`; el módulo propio no se carga y
  las imports quedan a cero.
- `sceKernelDlsym`: devuelve `0x80020003` para todo módulo de aplicación,
  incluido el `libc.prx` del boilerplate, con cualquier tabla hash, incluso de
  un solo bucket. El desensamblado del `libkernel` de 12.02 muestra que es un
  wrapper fino sobre la syscall, luego el rechazo es del kernel. El loader
  tampoco invoca `module_start` por búsqueda de símbolo; llama a `e_entry`.
- La tabla `DT_HASH` de los módulos de Sony no es SysV sobre el nombre
  codificado, el NID, el nombre plano ni los bytes crudos del NID; su clave
  sigue abierta y sólo importa si algún día hace falta `dlsym` del kernel.

Resolución adoptada: cada módulo lleva un descriptor estático relocado
(`PRXDESC1`) con pares nombre y puntero; el título lo localiza escaneando los
segmentos de `sceKernelGetModuleInfo`. Implementación compartida en
`modules/prx_loader.h` del fork, con tests host. El cargador de librerías de
Xash3D debe apoyarse en `prx_load`, `prx_get_proc` y `prx_unload`.

Observaciones operativas: `ftpsrv` expone los fSELF como ELF descifrado con
los últimos 512 bytes reescritos, así que la verificación de subida compara el
prefijo; el klog en el puerto 3232 de la consola muestra señales y errores de
`rtld`; la salida con `_exit` aparece como SIGSYS en klog aunque el shell
vuelva al menú sin diálogo.

## Xash3D BSP y resource foundation (2026-09-06)

La Fase 1 renderiza el `c1a0` privado con 3.611 draws, 164 texturas base,
lightmap y noclip. El gate de movimiento físico registró 2.018 frames con
traslación y 678 con giro. El gate texturado
`20260906T104934442Z_PPSA99997_ps5-agc-gears_0x57b1c21d2219` completó
60.000 frames, cero errores y BYE limpio; el log tiene SHA-256
`091707cbcf4b3fe31c0bb9a7134dfddeb6de14c23ffcb06d428f412e7a2ed3eb`.

La Fase 2 añade pool de memoria directa con generaciones y retiro diferido,
ring transitorio de dos slots, builders V#/T#/S#, constant buffers, tabla
generada de dos pipelines y contrato CPU→GPU/GPU→CPU. El gate
`20260906T130036578Z_PPSA99997_ps5-agc-gears_0x5ed84765862b` completó
60.000 frames conectados con cero errores, tokens exactos, guardas intactas,
ambos slots reutilizables y cuatro allocations persistentes reclamadas. Su log
tiene SHA-256
`8a7b8ce9aa03552f92c1717ff7bb4d836b616a8b399cf938951ac21f21e4c66e`.
El mapa permaneció idéntico entre dos capturas mientras la media verde del
overlay cambió aproximadamente 30,2 niveles; el operador confirmó el pulso en
vivo.

El fetch de vértices estructurados del overlay devolvió ceros en aislamiento
con esa combinación de pipeline. La solución validada conserva índices y color
en memoria transitoria, genera las cuatro posiciones desde `gl_VertexIndex` y
alimenta el color pulsante por el V# de constant buffer ya probado. La escritura
de user data también queda separada por etapa: GS en `0x8d`, PS en `0x0d`.

La implementación consolidada y la evidencia pública se fusionaron mediante
`mpereiraesaa/ps5-agc-gears#8` como commit `642d348`. Mapas, binarios, logs
completos y capturas permanecen privados; sólo se publican contratos, conteos y
hashes sanitizados.

## Xash3D engine boot: contrato real del sandbox (2026-09-07)

Gate 1 de la Fase 5 cerrado en FW 12.02 con la corrida
`20260907T074705479Z_PPSA99996_xash3d-engine_0x9c50d46dcc2a` (archivada en
`research/gpu/captures/runtime/`): el engine Xash3D FWGS `9aa39ad` en modo
dedicado, con `filesystem_stdio` y el servidor de hlsdk `e277ffa` enlazados
estáticamente, montó `valve` desde `/app0/xash3d`, generó `c1a0` con las 251
clases de entidad resueltas, simuló 90 s y salió por su propio `quit` con
`XASH_EXIT result=0` y BYE sin gaps. Diecinueve lanzamientos separaron los
hechos siguientes, todos medidos desde el título y ninguno documentado por la
foundation:

- Los descriptores 0, 1 y 2 arrancan cerrados y `dup2` sobre ellos devuelve
  `EPERM`: la captura de stdio de `ps5log` no puede funcionar en un título. La
  consola del engine llega por un shim de `write()` que reensambla líneas y
  quita escapes ANSI; sin eso un `\033[0m` pegado al inicio de la línea
  siguiente convirtió un registro estructurado en RAW y produjo un gap.
- `getcwd()` de `libSceLibcInternal` hace `SIGSEGV` dentro de la propia
  librería. `chdir()` devuelve `EPERM` para cualquier ruta, `/app0` incluido, y
  `access()` también sobre `/download0` aunque `open`/`write` funcionan allí.
  `filesystem_stdio` direcciona su raíz como `./`, así que el backend mantiene
  un cwd virtual y resuelve rutas relativas antes de llamar a `sceKernelOpen`,
  `sceKernelStat`, `sceKernelMkdir`, `sceKernelUnlink`, `sceKernelRename`.
- `opendir()` de libc devuelve `EPERM` en todas partes; `sceKernelGetdents`
  lista `/download0` pero devuelve `EINVAL` sobre la imagen `/app0` (nullfs de
  ShadowMount). Como el motor descubre juegos, WADs y nombres por enumeración,
  el build escribe `xash3d/.dirindex` y el backend sirve la imagen desde él.
- `/download0` existe y es escribible con `downloadDataSize` 256; `/temp0` no
  existe (`ENOENT`). La raíz del engine vive en `/download0/xash3d` y la imagen
  es `-rodir`.
- El heap de libc admite 8 MiB y falla a 16 MiB; la reserva de 21,25 MiB de
  entidades del servidor no cabía. `lld --wrap` de `malloc/free/realloc/calloc`
  envía las peticiones de 256 KiB o más a `mmap` anónimo (pico 32 MiB en la
  corrida). `sceLibcHeapSize` no existe en los stubs del SDK y el conversor
  nativo no publica exports, así que no hay forma de agrandar ese heap.
- `ioctl(FIONBIO)` y `fcntl(F_SETFL)` devuelven `EPERM`/`EACCES` en el socket
  UDP del servidor, que quedaba bloqueado en `recvfrom` y congelaba el bucle
  principal. El shim de `recvfrom` hace `poll` con timeout cero. `socket`,
  `bind`, `sendto`, `poll` y `pthread_create` funcionan.
- `getaddrinfo`/`gethostname` importarían `libScePosixForWebKit` y una llamada
  cayó con dirección NULL dentro de una librería del sistema; el backend
  resuelve direcciones numéricas localmente.
- El lld del SDK no sirve para `ld -r`: emite una sección de relocalización por
  grupo COMDAT y el enlace final la rechaza; el paso relocable usa el `ld.lld`
  del host y `llvm-objcopy -G lib_<módulo>_exports`.
- `ftpsrv` devuelve los fSELF como ELF descifrado con los últimos 512 bytes
  reescritos; `tools/deploy_title_ftp.py` verifica `eboot.bin` contra el ELF
  enlazado por prefijo y el resto de archivos byte a byte.

Contraste con las limitaciones publicadas por BlackBear para su port de
CPython (`blackbearreloaded/ps5-python`, `docs/ps5-limitations.md`): coinciden
en que la duplicación de descriptores no existe (allí `dup`/`dup2` devuelven
`ENOTSUP`; aquí `dup2` sobre 0-2 dio `EPERM` en FW 12.02 con ShadowMount), en
que `getaddrinfo` del SDK no sirve para IPv6 y en que no hay `dlopen`
arbitrario de `.so`/`.sprx`. Añaden tres límites que el gate no ejercitó y que
el port debe respetar: `execve` no lanza ELFs del sistema de archivos, así que
`Sys_NewInstance` del engine (cambio de `-game` por `execv`) nunca funcionará y
el cambio de juego debe ser en proceso como en Vita; `mmap` respaldado por
archivo devuelve `ENOTSUP`, y no hay semáforos POSIX con nombre. El engine, el
filesystem y el servidor no usan ninguno de los tres: `mmap` anónimo, `read`/
`write`, y mutex/condvar de pthread.

Todo vive en `ps5-xash3d`, rama `exp/engine-boot` (PR #3):
`xash/platform_ps5/{boot,sys,fs,mem}_ps5.c`, `xash/build_engine.sh` y
`docs/ENGINE_BOOT_PHASE5.md`. Las fuentes del engine no se tocan.
