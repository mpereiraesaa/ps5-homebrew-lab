# Descriptores color y depth/stencil AGC en San Andreas (PS5)

## Alcance

Reconstrucción estática de los dos objetos de 128 bytes creados por
`0x1f466c0`: color MRT y depth/stencil. No asigna nombres públicos a registros
AGC todavía no corroborados ni supone que el layout sea estable entre SDK o
firmware.

## Forma del objeto

Hay dos asignaciones distintas:

- `0x1f46e77` reserva la lista color y `0x1f46e8a` la deja en
  `texture_subobject+0x28` (`parent+0x88`). Su plantilla es `0x6e76dc0`.
- `0x1f476a2` reserva la lista depth/stencil y `0x1f476a5` la deja en
  `texture_subobject+0x30` (`parent+0x90`). Su plantilla es `0x6e76d00`.

Ambas contienen 16 pares DWORD `{register_id, value}`. La tabla que sigue
corresponde a depth/stencil, no al color backbuffer como se clasificó al
principio.

| Offset | ID | Valor inicial | Actualización observada |
|---:|---:|---:|---|
| `0x00` | `0x10` | `0x80000180` | formato/flags |
| `0x08` | `0x11` | `0x20000180` | formato/flags |
| `0x10` | `0x12` | `0` | dirección slot 0, bits 8..39 |
| `0x18` | `0x13` | `0` | dirección slot 2, bits 8..39 |
| `0x20` | `0x14` | `0` | dirección slot 1, bits 8..39 |
| `0x28` | `0x15` | `0` | dirección slot 3, bits 8..39 |
| `0x30` | `0x1a` | `0` | dirección slot 0, bits 40..47 |
| `0x38` | `0x1b` | `0` | dirección slot 2, bits 40..47 |
| `0x40` | `0x1c` | `0` | dirección slot 1, bits 40..47 |
| `0x48` | `0x1d` | `0` | dirección slot 3, bits 40..47 |
| `0x50` | `0x1e` | `0` | dirección slot 4, bits 40..47 |
| `0x58` | `0x02` | `0` | layout/flags |
| `0x60` | `0x05` | `0` | dirección slot 4, bits 8..39 |
| `0x68` | `0x07` | `0` | extensión de superficie |
| `0x70` | `0x0b` | `0` | campo opcional |
| `0x78` | `0x0a` | `0` | campo opcional |

La plantilla color base es:

```text
318 31b 31c 31d 31e 31f 321 323
324 325 390 398 3a0 3a8 3b0 3b8
```

`0x1f382f0` suma `15 * mrt_slot` a los primeros once IDs y `mrt_slot` a
los cinco finales antes de entregar los 16 pares al writer. Este patrón es la
prueba estructural que separa color MRT de depth/stencil.

La construcción color en `0x1f48fb8..0x1f49025` separa cuatro direcciones en
los mismos trozos `address >> 8` y `address >> 40`:

| Dirección temporal | DWORD bajo | Byte alto | IDs base |
|---:|---:|---:|---:|
| `stack+0x40` (superficie principal) | `descriptor+0x04` | `+0x54` | `0x318` / `0x390` |
| `stack+0x48` | `+0x2c` | `+0x5c` | `0x31f` / `0x398` |
| `stack+0x50` | `+0x34` | `+0x64` | `0x321` / `0x3a0` |
| `stack+0x58` | `+0x4c` | `+0x6c` | `0x325` / `0x3a8` |

`stack+0x40` se rellena con el puntero principal antes de construir la lista;
es la rama relevante para correlacionar la superficie color con VideoOut.

También queda probada la procedencia cruda de cinco campos de layout. El
constructor carga `source+0x12c`, y permuta los cuatro DWORD de
`source+0x130..0x13c` como sigue:

| Temporal | Procedencia |
|---:|---:|
| `stack+0x60` | `source+0x12c` |
| `stack+0x64` | `source+0x130` |
| `stack+0x68` | `source+0x134` |
| `stack+0x6c` | `source+0x13c` |
| `stack+0x70` | `source+0x138` |

El valor del par color base `ID 0x3b0` se forma exactamente como:

```c
value_3b0 = ((stack_64 - 1) & 0x3fff)
          | ((stack_60 << 14) & 0x0fffc000)
          | ((stack_70 << 28) & 0xf0000000);
```

Y `stack+0x6c << 13` alimenta los bits `13..25` del valor de `ID 0x31b`.
Esto prueba el empaquetado y su origen, pero todavía no justifica llamar a cada
campo width, height, pitch, slices o mip count.

Los nombres “slot” son neutrales: el slot 0 es la superficie principal en la
rama estudiada; los demás pueden ser planes o metadata según formato y usage.

## Dirección principal y VideoOut

VideoOut recibe completo el puntero de `ResourceCandidate+0x98`, el mismo
puntero principal colocado en `stack+0x40` y codificado por el descriptor
color en unidades de 256 bytes con la fórmula de abajo. Aún falta
cerrar qué combinación exacta de formato/tiling hace presentable esa dirección:

```c
value_318 = (uint32_t)(address >> 8);
value_390 = (uint8_t)(address >> 40);

address = ((uint64_t)(value_390 & 0xff) << 40)
        | ((uint64_t)value_318 << 8);
```

Los ocho bits inferiores se omiten. La alineación contractual del layout es
más fuerte y no debe reducirse sólo porque el campo represente 256 bytes.

La tabla siguiente es exclusivamente depth/stencil y no debe mezclarse con
los offsets color anteriores:

| Slot depth/stencil | DWORD bajo | Byte alto |
|---:|---:|---:|
| 0 | `descriptor+0x14` | `descriptor+0x34` |
| 1 | `descriptor+0x24` | `descriptor+0x44` |
| 2 | `descriptor+0x1c` | `descriptor+0x3c` |
| 3 | `descriptor+0x2c` | `descriptor+0x4c` |
| 4 | `descriptor+0x64` | `descriptor+0x54` |

## Dimensiones

La construcción del par ID `0x07` prueba:

```c
value_07 = (value_07 & 0xc000c000)
         | ((width  - 1) & 0x3fff)
         | (((height - 1) & 0x3fff) << 16);
```

Son dos campos de 14 bits codificados como `N-1`. Esto no demuestra por sí
solo que 16384 píxeles sea un límite operativo de toda la cadena.

## Estado para el clear mínimo

Probado: dos listas `{id,value}`, consumidor común final, clasificación
color-versus-depth/stencil, codificación de cinco direcciones y dimensiones en
la familia depth/stencil, además de la asignación que VideoOut presenta.

Pendiente: rederivar la dirección/formato/tiling del descriptor color,
clasificar los slots auxiliares, aislar el subconjunto mínimo y reproducirlo
dentro de un contexto AGC nativo válido antes del clear.

## Consumidor confirmado

La cadena directa depth/stencil quedó probada en `0x1f37f80`:

```text
context+0xee8 -> resource
resource+0x30 -> descriptor GPU address
EDX = 0x10 pairs
call 0x4dc0d30
  -> GOT 0x66d7eb8
  -> libSceAgc+0x4120, NID ZvwO9euwYzc
  -> packet header 0xc0039f00
```

`0x1f37fa5` carga el puntero de `resource+0x30` directamente en `RSI`, y la
llamada siguiente lo recibe sin transformación junto con el conteo `16`.
`libSceAgc+0x4120` conserva la dirección, limita el conteo a 14 bits y escribe
un paquete de cinco DWORDs con header `0xc0039f00`. Por tanto, el juego no
copia los 128 bytes al command stream desde la CPU: el command stream contiene
una orden que referencia en memoria la lista de 16 pares.

La ruta color se confirmó aparte en `0x1f382f0`: copia exactamente `0x80`
bytes desde `view+0x28`, ajusta los IDs por MRT slot y llama al cache writer
`0x4db80e0`. Cuando el cache necesita materializar el rango, éste llama al
mismo NID `ZvwO9euwYzc`; después copia `count*8` bytes y finaliza la región.

El orden dentro de la rutina de setup también queda fijado. El bucle
`0x1f37f37..0x1f37f49` llama una vez a `0x1f382f0` por MRT activo, pasando el
índice de slot. A continuación programa depth/stencil por una de dos rutas:

- si `context+0xee8` contiene un recurso, entrega `resource+0x30` directamente
  al NID con 16 pares;
- si no existe depth/stencil, copia la plantilla neutra `0x6e76d00` completa a
  la pila y la materializa con `0x4db80e0`, también con 16 pares.

Esto demuestra que un clear color no puede interpretar la ausencia de depth
como “omitir todo ese estado”: el juego instala explícitamente un bloque depth
neutro. Todavía falta determinar si ese bloque completo es contractual o si
un subconjunto es suficiente para nuestro primer clear.

Estas pruebas cierran la mecánica del consumidor, pero todavía no autorizan a
nombrar el opcode `0x9f` con terminología pública ni demuestran qué subconjunto
de registros basta para un clear. El artefacto reproducible es
`captures/san-andreas-rt-descriptor-consumer-proof.json`, generado por
`tools/verify_rt_descriptor_consumer.py`.

## Acotación histórica del consumidor

La búsqueda global de operandos confirmó que el puntero se escribe en
`texture_subobject+0x30` (`parent+0x90`) y que los accesos directos posteriores
en el ejecutable se concentran en construcción y destrucción. La vtable del
padre está en `0x61c7900` y la del subobjeto de textura en `0x61c7990`; sus
getters, refcount y métodos de transición no contienen un bucle que copie los
16 pares. `0x1f62c70`, inicialmente candidato, manipula estado de subrecursos y
tablas del contexto, no emite este descriptor.

La evidencia nueva resuelve esas dos alternativas: el descriptor se entrega a
una rutina importada de AGC mediante el puntero ya extraído; no se transforma
en otra representación CPU antes de grabar el command stream.

### Seguimiento de dependencias y falsos positivos

La ruta interna de `0x1f2f640` recibe el subobjeto de textura, comprueba la
existencia de `texture_subobject+0x30` y conserva la dependencia del recurso en
el contexto junto con un bit de estado. Para volver al objeto padre resta
`0x60`. Esto confirma que el descriptor participa en la preparación de la
operación, pero esta rutina no copia pares `{id,value}` ni emite comandos AGC.

Tras desensamblar por completo `0x1f20000..0x1f70000`, se revisaron los nuevos
accesos `+0x90` más cercanos al backend:

- `0x1f36d0d` lee un campo que inmediatamente divide entre cuatro y convierte
  en tamaños de trabajo; el objeto también contiene metadata empaquetada en
  `+0x0c/+0x14`. No es el puntero al descriptor de 128 bytes.
- `0x1f3a5bb`, `0x1f3a62b` y `0x1f3a69b` recorren en `+0x90` un vector de bytes
  cuyo número de elementos está en `+0x98`; es un mapa de slots/bindings.
- `0x1f3d6f5` forma parte de una reducción aritmética de campos consecutivos y
  `0x1f40ce0`/`0x1f4c861` son escrituras de inicialización. Tampoco consumen el
  descriptor del render target.

Por tanto, una coincidencia aislada con `parent+0x90` ya no se considera prueba
de consumo. El próximo criterio exige conservar la identidad del objeto desde
`texture_subobject+0x30`, observar una copia de `0x80` bytes o 16 pares, o ver
el puntero llegar sin transformación a una llamada del backend.

### Vtable del contexto: segundo falso positivo descartado

`0x1f2f460` ocupa la entrada `0x61c6550` de una vtable del contexto y conserva
dependencias de recursos mediante `0x1f2f640`. El método siguiente,
`0x1f2f9e0`, parecía prometedor porque también recorre objetos y lee un campo
`+0x98`, pero la secuencia emitida demuestra que se trata de otro tipo de
objeto:

- thunk `0x4dc0da0` -> `libSceAgc+0x4590`, NID `xSAR0LTcRKM`, escribe el header
  `0xc0023f00`, un paquete PM4 `INDIRECT_BUFFER`;
- sus DWORD de dirección/control salen de `[object+0x98]+0x00/+0x08`;
- thunk `0x4dc0db0` -> `libSceAgc+0xcf60`, NID `w6Dj1VJt5qY`, sólo modifica el
  bit 0 del primer DWORD devuelto;
- thunk `0x4dc0d90` -> `libSceAgc+0x73e0`, NID `bbFueFP+J4k`, emite antes el
  paquete `0xc0022000` con campos de control/predicación.

Así, `0x1f2f9e0` programa command buffers indirectos/secundarios; no copia los
16 pares del descriptor de render target. La coincidencia de offset `+0x98`
no conserva la identidad `texture_subobject+0x30 -> descriptor`. El consumidor
real terminó apareciendo en `0x1f37f80` y satisface los dos criterios fuertes:
puntero `+0x30` sin transformar y conteo exacto de 16 pares.

## Separación entre setup, transiciones y clear

La entrada de vtable `0x61c5d80 -> 0x1f34b10` no debe etiquetarse todavía como
un clear directo. La rutina registra hasta ocho MRT en `context+0xe08`, guarda
el número activo en `context+0xe04` y el depth en `context+0xee8`. Antes del
enlace de descriptores crea una lista de comandos diferidos para dependencias y
transiciones de subrecursos.

Dos familias de ejecutores quedaron separadas estáticamente:

- las vtables `0x614f7e0/0x614f800` despachan mediante `0x19d3d90`,
  `0x19d3dc0` y `0x19d3e00` a métodos virtuales del backend; transportan el
  recurso, rango y estado de transición;
- `0x61c7b38` ejecuta `0x1f636b0`, que termina en el consumidor color ya
  probado `0x1f382f0`; por tanto este objeto es enlace diferido de un MRT, no
  evidencia por sí solo de un clear.

Los ejecutores `0x1f633e0`, `0x1f634f0`, `0x1f636e0` y `0x1f637e0` escriben
estructuras compactas en el command context y actualizan su tabla de slots.
Esto confirma que copiar solamente el bloque final de 16 pares omitiría la
preparación de estado que Unreal realiza. Aún falta determinar cuál es el
subconjunto mínimo obligatorio para una superficie recién creada.

El backend concreto ya no es una incógnita en esos dos despachos. Sus
constructores `0x1f4152a`, `0x1f58fd2` y `0x1f59162` instalan la vptr
`0x61c5b08`. Con ella:

- el ejecutor resource-only `0x19d3d90` llama al slot `+0x10`,
  `0x1f59380`; esta rutina crea una descripción temporal vacía de `0x110`
  bytes, hace una asignación profunda sobre `backend+0x1b0` mediante
  `0x1f25a50` y luego libera el temporal con `0x1f25e20`;
- el ejecutor con rango `0x19d3dc0` llama al slot `+0xa8`, `0x1f31890`;
  éste localiza el slot del command context y copia exactamente 16 bytes de
  estado desde el registro transportado por el comando.

La pareja `0x1f25a50/0x1f25e20` no emite paquetes GPU: copia una estructura
compleja con referencias y después ejecuta su destrucción. Por ello no podemos
llamar barrera, flush ni clear a `0x1f59380`; la observación demostrable es un
reset/reemplazo del bloque de estado. La siguiente búsqueda queda reducida a
decodificar los 16 bytes que consume `0x1f31890` y seguir el punto donde ese
cache de estado se materializa en el command stream. La relación completa está
incluida en el verificador reproducible.

Ese segundo punto ya quedó cerrado. `0x4db7020` garantiza que exista el rango
de slots y, cuando debe crear el backing, `0x4db6990` llama al thunk
`0x4dc1c30 -> libSceAgc+0x28d0`. La rutina AGC construye un paquete de longitud
variable con cabecera basada en `0xc0007600`. El thunk
`0x4dc1c40 -> libSceAgc+0xd040` devuelve el comienzo de su payload y el engine
guarda ese puntero en la tabla corta (`command_context+0x278`) o extendida
(`+0x280`). En consecuencia, la escritura de 16 bytes de `0x1f31890` modifica
directamente cuatro DWORD del payload PM4 ya reservado; no es solamente una
copia a un shadow cache CPU desconectado.

La semántica de esos cuatro DWORD sigue abierta. La evidencia actual permite
llamarlos *ranged state record* y relacionarlos con la familia de paquete raw
`0x76`, pero no llamarlos aún barrera, flush o transición de layout sin
decodificar el descriptor fuente.

La procedencia del descriptor permite ahora corregir esa hipótesis. El objeto
fuente aporta dos selectores WORD en `+0xcc/+0xce`, un conteo en `+0xd0`
limitado a 16 y una secuencia contigua de DWORD. La rutina copia esos valores
sin transformación al payload raw `0x76`. Es, por tanto, una escritura genérica
de un rango de registros; no constituye evidencia de transición del render
target. Los nombres semánticos de los selectores siguen pendientes.

La primera pieza de control situada inequívocamente junto al enlace aparece
en `0x1f37ed9`, inmediatamente antes del bucle de MRT. El juego llama
`libSceAgc+0x5ce0` con selector `7` y dirección nula; AGC construye un paquete
`EVENT_WRITE` de dos DWORD, exactamente `[0xc0004600, 0x00000407]`. El bit
`0x400` no procede del callsite: el builder lo añade mediante una tabla de bits
que incluye los selectores `7`, `15` y `16`. A continuación llama
`libSceAgc+0x7ad0`. Este helper
queda resuelto a través de `libSceAgcDriver+0x6c80/+0x7050`: para selector cero
reserva exactamente tres DWORD y serializa
`[0xc0017904, 0x00000342, 0xc2000000]`. Sólo después se enlazan color y depth.
El orden y los bytes quedan probados, pero todavía no se asigna un nombre
público al evento `7` ni al paquete fijo; llamarlo *flush* requeriría
corroboración adicional.

La codificación PM4 pública de AMD sí permite clasificar el primer DWORD:
opcode `0x79` es `SET_UCONFIG_REG`, cuyo espacio parte de `0xc000`. Por ello el
segundo DWORD `0x342` selecciona el registro `0xc342` y el tercero escribe
`0xc2000000`. Esto prueba una escritura UCONFIG, no su finalidad. Los nombres
de registros de otras variantes GFX10 públicas no se trasladan automáticamente
a `gfx1013`, el target confirmado de la GPU personalizada de PS5, así que el
nombre y la semántica del registro permanecen abiertos.

La fase anterior también queda acotada. `0x1f34eba` llama al helper compuesto
`0x4db8380` en modo `2`. Sus flags se forman con `0xc00` para una condición de
color y `0x3000` cuando está presente alguna de las condiciones depth/stencil.
En modo `2`, el helper emite primero otro paquete raw `0x46`, esta vez con
selector `0x10`; el builder lo serializa exactamente como
`[0xc0004600, 0x00000410]`. Después transforma los bits restantes en máscaras y paquetes
de control adicionales. La secuencia observada queda:

```text
compound control mode 2 (evento 0x10 + flags por attachment)
  -> construcción/programación de estado
  -> evento 0x07 sin dirección
  -> paquete fijo de 3 DWORD vía libSceAgc+0x7ad0
  -> enlace de todos los MRT
  -> depth real o plantilla depth neutra
```

Esto es evidencia fuerte de dos fases de sincronización/control alrededor del
setup, pero no basta para trasladar nombres oficiales a los selectores ni para
afirmar qué subconjunto es obligatorio en una superficie nueva.

La tabla pública GFX9/GFX10 de PAL clasifica los tipos `7` y `0x10` como
`CS_PARTIAL_FLUSH` y `PS_PARTIAL_FLUSH`, respectivamente, y usa un índice de
evento específico para los partial flush. La coincidencia de opcode, tipo y bit
de índice convierte esos nombres en candidatos arquitectónicos fuertes. No se
declaran nombres ABI de PS5: AGC podría conservar una tabla derivada o
personalizada. El byte-proof reproducible está en
`captures/agc-event-write-proof.json`, generado por
`tools/verify_agc_event_write.py`.

### Separación exacta de las máscaras de attachments

El helper compuesto completo `0x4db8380` permite ya separar los dos casos que
el setup puede producir:

```text
flags color 0x0c00:
  EVENT_WRITE 0x410
  EVENT_WRITE 0x02e
  limpia input bit 0x400
  terminal event type 0x2d

flags color+depth/stencil 0x3c00:
  EVENT_WRITE 0x410
  EVENT_WRITE 0x02e
  EVENT_WRITE 0x02c
  limpia input bits 0x1400
  terminal event type 0x14
```

Después de esas ramas, ambos caminos convergen en una cadena privada que
construye `DMA_DATA`, `RELEASE_MEM`, `WAIT_REG_MEM`, `ACQUIRE_MEM` y
`WRITE_DATA`, copia la plantilla resultante al writer real y parchea una misma
dirección alineada en DMA/espera/release. Los thunks se resolvieron uno por uno
contra los offsets de `libSceAgc`; no se dedujeron por proximidad.

`libSceAgc+0x6e00` es un builder dual: el modo uno produce el paquete de nueve
DWORD `WAIT_REG_MEM64` (`0x93`), pero este caller fija `ESI=0`. La rama realmente
seleccionada genera siete DWORD con header `0xc0053c00`, es decir,
`WAIT_REG_MEM` (`0x3c`). El opcode `0x93` queda explícitamente fuera de esta
transacción.

El contrato de la label ya quedó reconstruido hasta sus DWORD exactos. El
`RELEASE_MEM` usa ocho DWORD y, antes de parchear la dirección, produce:

```text
color-only:  c0064900 0000052d 20010000 00000000 00000000 00000001 00000000 00000000
color+depth: c0064900 00000514 20010000 00000000 00000000 00000001 00000000 00000000
WAIT:        c0053c00 00000013 00000000 00000000 00000001 ffffffff 00000019
```

El patcher `libSceAgc+0xd320` instala la misma dirección alineada en DW3/DW4
del `RELEASE_MEM`; su payload DW5/DW6 es el entero de 64 bits `1`. Por tanto,
esta transacción concreta es `DMA_DATA(label=0) -> RELEASE_MEM(label=1) ->
WAIT_REG_MEM(label == 1, mask=0xffffffff, poll=0x19) -> ACQUIRE_MEM(label,32)`.
No debe confundirse con el fence de final de cola documentado por separado,
que usa CPU=`1` y GPU=`0`.

Esto cambia el próximo paso: no es seguro extraer solamente los dos
`EVENT_WRITE`. Son el prefijo de una transacción de coherencia con label
privada. El contrato de valor y espera de la label ya está probado; aún faltan
los nombres exactos de las máscaras de `ACQUIRE_MEM`. Los eventos ya tienen
correlatos públicos AMD fuertes:
`0x2e=FLUSH_AND_INV_CB_META`, `0x2c=FLUSH_AND_INV_DB_META`,
`0x2d=FLUSH_AND_INV_CB_DATA_TS` y
`0x14=CACHE_FLUSH_AND_INV_TS_EVENT`.
El artefacto reproducible es
`captures/san-andreas-attachment-control-paths.json`, generado por
`tools/verify_attachment_control_paths.py`.

El callsite de `ACQUIRE_MEM` también quedó acotado sin renombrar campos por
intuición. Después de parchear la label en DMA/WAIT/RELEASE llama
`libSceAgc+0x3830` con los argumentos raw:

```text
ESI=1, EDX=0, ECX=0x9000,
R8=label alineada, R9D=0x20, stack[0]=0x190
```

El builder emite ocho DWORD con header `0xc0065800`; el rango pasado es
exactamente 32 bytes, la misma reserva de la label. Esto prueba el alcance de
la adquisición. En el dump runtime los flags internos del encoder son cero y
seleccionan su ruta genérica; el paquete resultante queda completamente
parametrizado por la dirección de la label:

```text
DW0 = c0065800
DW1 = 80000000
DW2 = ceil(((label & ff) + 32) / 256)  // 1 o 2
DW3 = 00000000
DW4 = (label >> 8) & ffffffff
DW5 = (label >> 40) & ff
DW6 = 00000019
DW7 = 00009000
```

La reserva sólo ocupa dos unidades de 256 bytes si el byte bajo de la label es
mayor que `0xe0`. Esto prueba los campos raw, el redondeo de rango y el
intervalo de polling, pero no autoriza todavía a traducir `0x9000` a nombres
de bits PS5 usando solamente una definición AMD pública.

La ruta reflejada `ClearRenderTarget2D` (`0x48a74b0`) también se descartó como
ancla directa, pero ahora su flujo queda cerrado. El comando de vtable
`0x61c3bf0` ejecuta `0x1f13de0`, que llama al setup probado `0x1f34b10`.
Después se invoca la operación canvas `0x278e500` y se encola el comando de
vtable `0x61c3c10`; su ejecutor `0x1f13e30` salta al teardown `0x1f384e0`.
La propia operación canvas construye el comando `0x614f6f0`: su ejecutor
`0x19d11c0` llega al backend `0x1f386a0`, que llama `libSceAgc+0x69f0` y luego
`libSceAgc+0x5240`. Este último serializa el paquete PM4 `DRAW_INDEX_AUTO`
(`0xc0012d00`). Por tanto es inequívocamente un draw gráfico encerrado entre
setup y teardown, no evidencia de un clear AGC autónomo sin pipeline. Esta ruta
requiere el estado gráfico correspondiente y no proporciona un atajo sin
shaders para la primera pantalla de color.
