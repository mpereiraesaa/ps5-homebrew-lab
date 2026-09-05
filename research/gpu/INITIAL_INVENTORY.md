# Inventario GPU inicial

Fecha: 2026-09-03. Contexto: menú, sin aplicación foreground. Captura mediante
ps5debug-NG 1.3, únicamente enumeración y lectura.

## Resultado de procesos y mapas

- 93 procesos enumerados.
- `AgcCompositor.elf` carga `libSceAgcDriver.sprx` y `libSceAgcVsh.sprx`.
- El compositor también contiene regiones `SceAgcDriver` y
  `GpuClearStateGuardData`.
- SceShellUI y varios servicios cargan `libSceAgcVsh.sprx`.
- No apareció `libSceGnmDriver` como nombre de mapping en este estado.

## Dump de libSceAgcDriver

Se capturaron cuatro segmentos legibles con span disperso de 144 KiB. El dump
empieza en el mapping ejecutable y no contiene la cabecera ELF original, por lo
que debe importarse en Ghidra como imagen raw x86-64 respetando las bases y
permisos del manifiesto, o reconstruirse en un contenedor ELF local.

La repetición produjo:

| Segmento | Tamaño | Repetición |
| --- | ---: | --- |
| `r-x` | 48 KiB | hash idéntico |
| `r--` | 32 KiB | hash idéntico |
| `r--` | 16 KiB | hash idéntico |
| `rw-` | 48 KiB | cambió |

Decisión: identificar builds con los hashes de segmentos inmutables. El hash de
RW describe sólo el snapshot runtime.

## Cadenas de alta señal observadas

- `sce_agc_initialize` y `sce_agc_initialize_internal_memory`.
- `sceAgcDriverSubmitMultiCommandBuffersDirect`.
- `sceAgcDriverSdmaCopyLinearBlocking`.
- `_sceAgcDriverCreateUserSpecialQueue`.
- Mensajes de adquisición de cola y validación de índices.
- Integración con `sceVideoOutSubmitEopFlip` y labels de VideoOut.
- Distinción explícita entre compositor, game process y non-game process.
- Memoria/estado para register shadow, trap handler, CWSR y workloads.

Estas cadenas orientan el análisis, pero no constituyen símbolos resueltos ni
prototipos confirmados.

## Próximo objetivo

Se capturó también el host `FAKE00000` mientras ejecutaba nuestro probe de
VideoOut. El proceso runtime aparece como `SceCloudClientApp` y cargó
`libSceVideoOut`, `libSceAudioOut`, `libScePad` y librerías de soporte. No tenía
maps cuyo nombre contuviera AGC, GNM o GPU.

Esto explica el estado actual: el homebrew dispone de presentación y multimedia,
pero no ha cargado una pila de render GPU. No demuestra todavía si puede cargarla
explícitamente ni qué permisos recibirá al hacerlo.

Próximo objetivo: capturar un juego PS5 nativo autorizado y comparar su conjunto
de módulos/mapas con menú y `FAKE00000`. Después se importará el driver raw en
Ghidra para localizar inicialización y callers.

## Juego PS5 nativo

La tercera captura encontró el proceso foreground `eboot.bin`. A diferencia del
host homebrew, el juego cargó simultáneamente:

- `libSceAgc.sprx` (capa user-mode/API);
- `libSceAgcDriver.sprx` (driver/submit);
- `libSceVideoOut.sprx`;
- `libSceRazorCpu.sprx`.

También aparecieron regiones dedicadas `SceGnmTrapCode`, `SceGnmTrapData`,
`SceGnmEopFifo`, `SceGnmCwsr`, `SceGnmACQRB`, `SceGnmDingDong`,
`SceAgcDdid`, register-shadow y áreas de dump/GPR. Los nombres GNM dentro de la
infraestructura no contradicen que la librería user-mode PS5 observada sea AGC.

Se volcaron read-only `libSceAgc` y `libSceAgcDriver`. El código y primer
segmento read-only del driver tienen los mismos hashes que en el compositor; un
segmento read-only posterior difiere y requiere determinar si contiene
relocations o estado generado. `libSceAgc` quedó listo para importación raw.

Conclusión: la diferencia entre nuestro host y un juego no es VideoOut, sino la
carga/inicialización AGC y sus allocations/colas auxiliares. La siguiente unidad
de análisis es `libSceAgc`, que probablemente envuelve la interfaz del driver.

## Importación en Ghidra

Como el dump de memoria comienza en el primer mapping y carece de cabecera ELF,
se creó un contenedor de análisis ELF64 con seis `PT_LOAD`, direcciones runtime,
alineación de 16 KiB y permisos originales. Ghidra lo importó y autoanalizó como
`/gpu/game-libSceAgc.analysis.elf` dentro del proyecto `PS5_GPU_RESEARCH`.

No se debe ejecutar ese contenedor: existe únicamente para que Ghidra conserve
el layout virtual y resuelva correctamente referencias x86-64 RIP-relative.
