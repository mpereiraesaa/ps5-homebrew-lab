# Constructores `DMA_DATA` de AGC

Alcance: firmware PS5 12.02 y dumps autorizados de esta consola. Este análisis
es estático: no ejecuta ni envía comandos a la GPU.

## Identidad comprobada

La tabla dinámica del `libSceAgc.sprx` del sistema identifica dos exports:

| Cola | Offset | NID | Nombre recuperado |
| --- | ---: | --- | --- |
| ACB / async compute | `+0x740` | `-RnpfpxIhec` | `sceAgcAcbDmaData` |
| DCB / graphics | `+0x47d0` | `WmAc2MEj6Io` | `sceAgcDcbDmaData` |

Los nombres se corroboraron con la implementación pública de Prosper y sus
pruebas de ABI. Los bytes completos de ambos exports coinciden entre el módulo
del sistema 12.02 y el mapping capturado dentro de San Andreas.

## Formato probado

Ambos builders reservan siete DWORD y escriben la cabecera PM4
`0xc0055000`: paquete tipo 3, opcode `DMA_DATA` (`0x50`), cinco DWORD de
payload tras la cabecera. El cuerpo contiene dos direcciones/valores de 64 bits
y un DWORD final de control. La fórmula raw DCB quedó cerrada desde el export
12.02 y contrastada ejecutando localmente sus bytes en cinco casos aislados:

```text
DW0 = c0055000
DW1 = (a12&1)<<31 | (a6&3)<<29 | (a4&3)<<25 |
      (a3&3)<<20 | (a7&3)<<13 | (a2&1)
DW2/DW3 = source64
DW4/DW5 = destination64
DW6 = (a11&1)<<31 | (a10&1)<<30 | (a3&8)<<26 |
      (a6&8)<<25 | (a3&4)<<25 | (a6&4)<<24 |
      (byte_count & 0x03ffffff)
```

La comparación bit a bit con las estructuras oficiales de paquetes AMD GFX9
cierra también los campos ordinarios: `a2` es `engine_sel`; `a3` agrupa
`dst_sel/das/daic`; `a4` es `dst_cache_policy`; `a6` agrupa
`src_sel/sas/saic`; y `a7` es `src_cache_policy`. `a6` igual a `0x14`, `0x24`
o `0x64` selecciona además una de tres parejas de fuentes especiales del
firmware; el nombre semántico PS5 de esas tres extensiones sigue sin probarse.

La DCB tiene una forma de fuente inmediata y una forma de fuente por dirección.
Esto hace viable investigar un fill acelerado. Para el caso ordinario ya están
fijados los enums, políticas, tamaño en bytes y bits de sincronización. Lo que
todavía **no** está probado es que una asignación de nuestro homebrew tenga una
dirección GPU válida, que podamos someter el paquete desde una cola propia ni
la transición/coherencia requerida por un backbuffer de VideoOut.

### Caso inmediato observado en San Andreas

El helper de eboot `0x4db84c0` crea una plantilla DCB con:

- fuente inmediata `0`;
- destino placeholder `0`;
- longitud `4` bytes;
- forma bloqueante activa.

Después copia esa plantilla al command buffer definitivo, corrige el puntero
por el desplazamiento de la copia y llama a tres patchers sobre una misma
etiqueta alineada:

1. `sceAgcDmaDataPatchSetDstAddressOrOffset` (`libSceAgc+0xd0c0`);
2. `sceAgcWaitRegMemPatchAddress` (`+0xd100`);
3. `sceAgcQueueEndOfPipeActionPatchAddress` (`+0xd320`).

La secuencia demuestra que el juego usa `DMA_DATA` para escribir cero en una
etiqueta GPU de cuatro bytes antes del protocolo wait/release. Es una base
excelente para el primer probe aislado porque ya tenemos un caso real completo
de construcción y parcheo. No justifica escalar la longitud ni usar memoria de
VideoOut hasta demostrar límites, política de caché y visibilidad CPU/GPU.

El barrido completo de referencias encuentra nueve callsites DCB y el
verificador ancla cada bloque de preparación por SHA-256, además de recalcular
el destino de su `CALL rel32` al thunk `0x4dc0c10`. Las formas observadas son:

- tres copias con longitud dinámica;
- tres inicializaciones inmediatas a cero de cuatro bytes, incluida la
  plantilla privada de sincronización;
- dos copias indexadas de cuatro bytes;
- una copia inversa de cuatro bytes.

Esto elimina la posibilidad de que el caso documentado fuera el único uso del
export. Los nueve comparten `a12=1` y ninguno activa `a11`; las tres copias de
longitud dinámica activan `a10=1`. Es evidencia comparativa útil, pero no basta
por sí sola para nombrar esos bits como políticas de caché PS5.

### Correlación con AMD PAL GFX9

El builder oficial AMD PAL de `DMA_DATA` coloca `sync` en `cp_sync`, `rawWait`
y `disWc` en el DWORD final, y limita `numBytes` a menos de 64 MiB. Las
posiciones coinciden exactamente con nuestra fórmula:

- `a12` → `DW1.bit31` → `cp_sync`;
- `a10` → `DW6.bit30` → `raw_wait`;
- `a11` → `DW6.bit31` → `dis_wc`;
- `a9` → `DW6.bits[25:0]` → `byte_count`.

PAL indica que `sync` debe activarse en casi todos los casos y que `disWc` no
debe activarse cuando una barrera necesita confirmar que las escrituras DMA
llegaron a destino. San Andreas usa `a12=1` y `a11=0` en los nueve callsites,
coherente con esa recomendación. Se conserva como correlación arquitectónica
GFX9: Sony no exporta aquí los nombres de tipo originales de estos argumentos.

La plantilla resultante queda reconstruida como:

```text
c0055000 c0300000 00000000 00000000 00000000 00000000 00000004
```

Decodificada con los campos oficiales: motor ME, destino
`dst_addr_using_l2`, fuente inmediata `data`, ambas políticas LRU, espacios de
dirección de memoria, incremento normal, `cp_sync=1`, `raw_wait=0` y
`dis_wc=0`. Es exactamente la combinación conservadora que debemos conservar
en un primer write de cuatro bytes; no autoriza aumentar el rango ni hacer
submit sin resolver cola y mapping GPU.

La semántica de rango de la fuente inmediata quedó cerrada estáticamente
contra AMD PAL GFX9, commit `c5e800072a32f68b6ccc4422936d96167c6e0728`:
el driver denomina esta operación `DMA fill` y usa `src_sel=data`, un único
`srcData` y un `numBytes` mayor que cuatro para poner a cero rangos completos
de resultados de occlusion queries. El DWORD inmediato se repite durante todo
el conteo. Esto permite componer el futuro packet de 32 MiB, pero no autoriza
ejecutarlo antes del label probe ni prueba coherencia con VideoOut.

Prosper (commit `5842615a4b4da06802d505339beda809af96b489`) corrobora de
forma independiente el NID, tamaño de siete DWORD, argumentos de fuente,
destino y longitud, patchers y el protocolo de etiqueta cero seguido de
`ReleaseMem`. Su command packet es una representación privada traducida, por
lo que sólo se usa como evidencia secundaria; el layout PM4 nativo procede de
los bytes 12.02 y de las estructuras oficiales AMD.

El patcher valida que el byte de opcode sea `0x50` y escribe exclusivamente el
qword en `packet+0x10`, es decir DWORD4/5. La fuente inmediata cero permanece
en DWORD2/3 y la longitud cuatro permanece en DWORD6. El patcher hermano de
fuente escribe exclusivamente `packet+0x08`.

Tampoco sustituye VideoOut, contexto/cola, submit, fence ni flip. El primer uso
en hardware debe ser un buffer de prueba aislado, pequeño y con guardas, nunca
una superficie visible ni memoria de un juego comercial.

## Verificación reproducible

```sh
python3 research/gpu/tools/verify_agc_dma_data.py \
  research/gpu/dumps/system-libSceAgc.sprx \
  research/gpu/dumps/game-libSceAgc.sprx.bin \
  research/gpu/dumps/san-andreas-eboot-runtime.bin \
  --execute-local-builder \
  --output research/gpu/captures/agc-dma-data-proof.json
```

El verificador comprueba NID/offset, stores exactos de cabecera y payload,
igualdad de los exports completos entre sistema y runtime, y conserva
`raw_packet_abi_proven: true` y `safe_generic_fill_encoding_proven: true`, pero
mantiene separados `homebrew_gpu_mapping_and_submit_proven: false` y
`safe_generic_fill_hardware_execution_proven: false`: sabemos reproducir el
fill conservador, no todavía ejecutarlo desde una cola propia.
Con `--execute-local-builder`, un host x86-64 ejecuta la copia autorizada del
export dentro de un buffer falso aislado y exige retorno al inicio, avance de
28 bytes y coincidencia de los siete DWORD. No carga el módulo ni envía nada a
la consola.

## Composición con el fence de ownership

`tools/compose_agc_label_probe.py` ejecuta en el host copias aisladas de los
dos builders comprobados y construye en un mismo writer la secuencia mínima:

```text
DMA_DATA(target_u32 = 0)          7 DWORD / 28 bytes
RELEASE_MEM(fence_u64 = 0)        8 DWORD / 32 bytes
                                      total: 60 bytes
```

La CPU deberá inicializar previamente `target_u32` con un canary no nulo y
`fence_u64` con `1`. Las direcciones del artefacto son deliberadamente
sintéticas, distintas y alineadas; por eso el binario no es submit-ready. El
verificador exige que el primer builder avance a byte 28, que el segundo
comience exactamente allí y que el cursor final quede en byte 60.

La prueba queda en `captures/agc-minimal-label-stream-proof.json`; el binario
asociado sólo sirve para comprobar bytes y SHA-256. No demuestra cola, mapping,
coherencia ni ejecución GPU.

## Escalones ejecutados y siguiente frontera

Native Label v5 completó los tres puntos anteriores: obtuvo mapping efectivo,
inicializó AGC, sometió el stream mínimo sobre memoria propia y observó
`target 0xa5a55a5a -> 0` seguido por `fence 1 -> 0`, sin superficie visible.
Stage C amplió después el mismo packet, sin VideoOut, a 256 B, 4 KiB y 64 KiB
en mappings de datos separados del command arena. En los tres casos se obtuvo
`SubmitDcb=0`, fence cero, pattern completo, canarios intactos, exterior sin
cambios y cleanup total. Evidencia consolidada:
`captures/agc-stage-c-progression.json`. Stage D unió después el fill y la
presentación: `DMA_DATA` cubrió un backbuffer de `0x00880000` bytes, seguido de
SetFlip y fence, y el operador confirmó el frame visible. Evidencia:
`captures/agc-stage-d-runtime.json`.
