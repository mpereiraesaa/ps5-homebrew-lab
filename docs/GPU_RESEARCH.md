# Línea de investigación GPU

> Registro cronológico privado. La implementación activa y publicable es
> `projects/ps5-agc-gears`; consultar `CURRENT.md` antes de interpretar como
> vigente cualquier “estado” o “siguiente paso” de este documento.

## Referencia pública ProsperoTV (2026-09-04)

Se fijaron localmente como referencias GPL-3.0-or-later
`third_party/ps5-hardware-video-decoding-research` y
`third_party/ProsperoTV`. ProsperoTV contiene una ruta AGC nativa real en
`src/iptv_native_agc_present.c`, no sólo una abstracción:

- inicializa AGC mediante `sceAgcInit(&state, 8)`;
- reserva y mapea memoria directa tipo 12 con protección `0x33`;
- crea y enlaza vertex/pixel shaders;
- obtiene defaults de registros y construye CX/SH/UC DCBs;
- espera ownership de VideoOut mediante el paquete del driver;
- emite draw y flip en el mismo DCB;
- envía con `sceAgcDriverSubmitDcb` y sincroniza con `sceAgcSuspendPoint`;
- desregistra VideoOut, desmonta y libera memoria en orden.

La implementación evita `GetDmem`, `CreateQueue` y el bootstrap manual:
`sceAgcInit` y las APIs de `libSceAgc`/`libSceAgcDriver` encapsulan esa capa.
El host nativo `PPSA99998` ya validó imports, `sceAgcInit`, BatchMap y el submit
mínimo. ProsperoTV continúa como referencia secundaria para la siguiente unión
con VideoOut, sin copiar sus assets privados ni depender de internals de un
juego comercial.

El renderer no es inmediatamente reproducible: cinco blobs AGC se incluyen
desde `assets/private/` y no están publicados. El código sí aporta firmas,
estructuras, flags, tamaños, orden de vida, submit y sincronización. El primer
clear propio necesitará shaders redistribuibles generados independientemente o
un camino AGC que no dependa de esos assets.

## Objetivo

Conseguir que un ELF homebrew ejecute trabajo verificable en la GPU de la PS5,
primero mediante una operación mínima y después mediante un renderer reutilizable.
VideoOut seguirá siendo únicamente el mecanismo de presentación. SDL software,
ports y emulación quedan pausados mientras esta línea esté activa.

## Estado vigente (Stage E completado)

La operación mínima ya está demostrada en hardware desde la aplicación nativa
`PPSA99998`: `DMA_DATA` cambió cuatro bytes propios de `0xa5a55a5a` a cero y
el `RELEASE_MEM` posterior cambió la fence de uno a cero. El submit, BatchMap y
cleanup completo devolvieron éxito. No intervino VideoOut, ningún shader, draw
ni proceso comercial. Por tanto, inicialización, mapping, command fetch,
escritura GPU y completion básica ya no son hipótesis; el trabajo activo pasa a
integración con VideoOut. Stage B v4 completó esa unión en hardware: registró
dos buffers propios, preparó sólo el seleccionado, obtuvo `SubmitDcb=0`, observó
primero fence GPU cero y luego el evento del `flip_arg` exacto. El set activo
devolvió `RESOURCE_BUSY` al desregistrar y fue liberado por `VideoOutClose` antes
de desmontar el framebuffer. Todo el teardown posterior devolvió cero; el
supervisor cerró PPSA99998 y verificó los cuatro servicios saludables.
Evidencia: `research/gpu/captures/agc-stage-b-v4-runtime.json`.

Stage C aisló después `DMA_DATA` de VideoOut y escaló el rango privado de
256 B a 4 KiB y 64 KiB. Cada ejecución obtuvo submit cero y fence cero, verificó
por CPU todo el target, ambos canarios y todo el exterior, hizo scrub y teardown
completo y terminó con cierre y servicios saludables. Evidencia consolidada:
`research/gpu/captures/agc-stage-c-progression.json`.

Stage D unió por fin ambas rutas en un único DCB: `DMA_DATA` rellenó con color
sólido los `0x00880000` bytes del backbuffer 1, después `SetFlip` lo presentó y
`RELEASE_MEM` entregó ownership. La lectura CPU confirmó todo el target, dos
guardas de 64 bytes y que el backbuffer 0 de recuperación permaneció intacto.
Llegó el evento del `flip_arg` exacto, el color verde se mantuvo cinco segundos
y fue confirmado físicamente por el operador. Cleanup, cierre exacto y salud de
los cuatro servicios también quedaron comprobados. Evidencia:
`research/gpu/captures/agc-stage-d-runtime.json`.

Stage E sustituyó el fill por un pipeline gráfico propio compilado para
`gfx1013`. Los builders nativos emitieron indirectos CX/UC/SH de cinco DWORD,
`DrawIndexAuto(3)` y `SetFlip`; el DCB final tuvo 122 DWORD. El shader dibujó un
triángulo verde centrado sobre fondo morado y modificó exactamente 285.120
píxeles. Fence cero, evento exacto, guardas, buffer de recuperación, hold de
cinco segundos y cleanup pasaron; el operador confirmó el resultado visual.
Evidencia: `research/gpu/captures/agc-stage-e-centered-triangle-runtime.json`.

## Criterio de éxito final

Un probe autocontenido debe:

1. inicializar el acceso GPU desde una aplicación nativa propia;
2. reservar y registrar sus recursos sin depender de un juego comercial;
3. ejecutar un clear o triángulo mediante comandos GPU;
4. sincronizar CPU/GPU y presentar el resultado con VideoOut;
5. repetirlo durante al menos 10.000 frames sin errores ni crecimiento de memoria;
6. cerrar y liberar todos los recursos limpiamente.

Los inventarios y puertas que siguen documentan la progresión histórica. Sus
casillas pendientes no sustituyen el roadmap vigente de `docs/ROADMAP.md`.

## Reglas de investigación

- Los blobs, dumps, shaders y fragmentos sustanciales procedentes de juegos
  comerciales son exclusivamente material privado de laboratorio: jamás se
  publicarán, distribuirán ni incorporarán a builds, commits o releases.
- El árbol publicable sólo puede conservar hashes, tamaños, layouts ABI,
  observaciones sanitizadas, resultados experimentales y reimplementaciones
  independientes. Un hash identifica una muestra privada pero no autoriza a
  almacenar la muestra en el repositorio.
- Toda captura propietaria debe residir fuera del árbol versionado o en una
  ruta ignorada verificada antes de capturar. Ante duda sobre la procedencia de
  un archivo, el gate de publicación falla cerrado.
- Separar símbolo observado, firma inferida y firma confirmada.
- Guardar firmware, hash del módulo, offset y evidencia para cada conclusión.
- Preferir primero capturas y lecturas; no parchear procesos de referencia.
- No reproducir buffers completos a ciegas. Reducir cada experimento a una sola
  variable y validar direcciones, tamaños, alineaciones y ownership.
- Cada probe que pueda colgar la GPU tendrá timeout, log persistente y una vía de
  salida. Empezar por consultas; submit será una puerta posterior.
- No almacenar datos personales, claves, seriales ni contenido propietario en el
  repositorio. Los dumps locales quedan fuera de control de versiones.

## Estado inicial confirmado

- BigApp `FAKE00000` dispone de Main Direct Memory.
- VideoOut presenta dos buffers 3840x2160 y sincroniza flips.
- ps5debug-NG permite listar procesos/mapas, leer memoria y volcar módulos.
- En el menú, `AgcCompositor.elf` carga `libSceAgcDriver.sprx` y
  `libSceAgcVsh.sprx`; otros procesos del sistema cargan también AgcVsh.
- El SDK contiene stubs de `libSceGnmDriver`, incluidos símbolos de información,
  SDMA, draw/dispatch, shaders, validación, submit y captura.
- Los stubs confirman nombres/NIDs resolubles, no prototipos ni uso correcto.
- Hipótesis actual: AGC es la superficie gráfica PS5 nativa observada; GNM puede
  pertenecer a compatibilidad o herencia y no debe asumirse como camino primario.
- Native Label v5 demostró ejecución GPU desde homebrew y escritura observable
  en memoria propia; Stage D presentó por VideoOut una imagen producida por esa
  misma ruta GPU.

## Puerta 0 — banco de trabajo reproducible

- [x] Crear `research/gpu/` con `dumps/` ignorado, manifiestos, scripts y notas.
- [x] Registrar automáticamente hash, tamaño, base y segmentos de cada módulo.
- [x] Documentar el flujo ps5debug-NG -> dump -> Ghidra -> anotaciones exportadas.
- [x] Crear una plantilla de ficha por función: NID, offset, callers, argumentos,
  retorno, efectos y nivel de confianza.
- [x] Confirmar hashes repetibles para segmentos inmutables; RW cambia por estado.

**Salida:** dataset reproducible y sin material sensible versionado.

## Puerta 1 — inventario de la superficie GPU

- [x] Comparar módulos y mapas en menú, BigApp y juego PS5 nativo.
- [x] Identificar las capas cargadas: `libSceAgc` + `libSceAgcDriver` en juego;
  AgcDriver/AgcVsh en compositor; ausentes originalmente del host heredado
  `FAKE00000` y cargadas con éxito por el host nativo `PPSA99998`.
- [ ] Catalogar imports/exports y NIDs usados por BigApp y por la referencia.
- [ ] Agrupar funciones: consulta, memoria, colas, sincronización, shaders,
  comandos, submit, flip, validación y diagnóstico.
- [ ] Ejecutar sólo funciones de consulta con firmas de alta confianza, empezando
  por reloj/estado/permisos, y registrar códigos de retorno.

**Salida:** mapa de módulos y shortlist de APIs mínimas para el primer trabajo.

## Puerta 2 — reconstrucción del camino de inicialización

- [ ] En Ghidra, localizar callers de `sceGnmSubmitCommandBuffers`,
  `sceGnmSubmitAndFlipCommandBuffers` y funciones de inicialización por defecto.
- [x] Importar `libSceAgc` y `libSceAgcDriver` con sus layouts runtime.
- [x] Identificar el constructor/finalizador de `libSceAgc` y sus primeros cruces
  hacia el driver.
- [ ] Recuperar prototipos mediante registros de llamada, stack, tamaños y
  comparación entre varios callers.
- [x] Identificar el contrato mínimo de contexto, DCB y labels/fences necesario
  para Native Label v5.
- [x] Probar `type=0x0c`, BatchMap `protection=0xf2`, alineación y visibilidad GPU
  para el arena mínimo de comandos/labels.
- [ ] Relacionar allocations observadas con cambios de mapas en ps5debug-NG.
- [ ] Confirmar cada firma con un probe de consulta o construcción sin submit.

**Salida:** diagrama del flujo init -> allocate -> encode -> submit -> wait -> flip,
con prototipos versionados y niveles de confianza.

## Puerta 3 — captura y análisis diferencial

- [ ] Crear una referencia visual mínima y controlable: idle, clear de dos colores
  y, si es posible, un único triángulo.
- [ ] Capturar snapshots antes/después de una sola transición conocida.
- [ ] Separar command buffers, shaders, descriptors, labels y render targets por
  dirección, permisos y patrón de cambio.
- [ ] Decodificar primero paquetes de sincronización/clear; evitar empezar por un
  frame completo de un juego.
- [ ] Verificar hipótesis cambiando exactamente un parámetro de la referencia.

**Salida:** formato mínimo documentado para un clear y su sincronización.

## Puerta 4 — primer trabajo GPU de homebrew

- [x] Probe 1: consultas de driver, sin submit.
- [x] Probe 2 mínimo equivalente: escritura `DMA_DATA` de cuatro bytes propios,
  canario y fence posterior observados en hardware.
- [ ] Probe 3: clear GPU de un render target no presentado; leerlo desde CPU.
- [ ] Probe 4: clear GPU presentado por VideoOut.
- [ ] Probe 5: triángulo con shaders mínimos confirmados.
- [ ] Añadir timeout de fence y recopilar diagnóstico ante cada error.

**Salida:** evidencia inequívoca de escritura/render GPU iniciada por nuestro ELF.

## Puerta 5 — capa GPU mínima

- [ ] Allocator de recursos GPU con subasignación y alineación comprobada.
- [ ] Command allocator por frame y triple buffering.
- [ ] Fences, ownership y reciclaje seguro de recursos.
- [ ] Carga de shaders reproducible y formatos de textura/render target.
- [ ] API pequeña: init, buffer, texture, pipeline, clear, draw, submit, present.
- [ ] Métricas de CPU frame time, GPU completion, ancho de banda y memoria.
- [ ] Soak de 10.000 frames y recuperación controlada de errores.

**Salida:** backend nativo suficiente para comenzar un renderer de juego.

## Próxima sesión de trabajo

1. Conservar Stage B v4 como baseline reproducible de presentación y teardown.
2. [x] Stage C amplió `DMA_DATA` en memoria privada propia: 256 B, 4 KiB y
   64 KiB, cada escalón condicionado al anterior.
3. [x] VideoOut, shaders y draw permanecieron ausentes; cada rango se verificó
   por CPU tras fence, con canarios y escaneo de todo el exterior.
4. [x] Stage D unió el fill de 8,5 MiB, SetFlip, fence y evento exacto; el
   operador confirmó físicamente el frame sólido.
5. Preparar Stage E: pipeline y triángulo mínimos con shaders redistribuibles.
