# Memoria de command buffers AGC en San Andreas (PS5)

## Alcance y resultado

Análisis estático del `eboot.bin` reconstruido, sin attach, breakpoints, llamadas
remotas ni escrituras en la PS5. La ruta observada para los command buffers de
San Andreas no es un `malloc` flexible ordinario: `FMallocBinned3` entrega una
dirección dentro de una gran ventana virtual y hace respaldar/commitear sus
páginas con **main direct memory**.

Este resultado describe el port PS5 de Unreal/San Andreas; no prueba por sí
solo que AGC exija exactamente el mismo allocator, flags o granularidad para
todo homebrew.

## Ruta exacta del command buffer

`FUN_01f22940` llama al método `+0x18` de `PTR_PTR_06c72280` con:

```c
Malloc(0x100000, 0x10000); // 1 MiB, alineación 64 KiB
```

En el dump, `PTR_PTR_06c72280 = 0x06c70650`; el primer miembro del objeto apunta
a la vtable `0x061ccf70`, cuyo slot `+0x18` es `FUN_01fef170`. Esta es la entrada
`Malloc` de `FMallocBinned3` y deriva al slow path `FUN_01fe9180` cuando no hay
un bloque en la caché por hilo.

Para 1 MiB, el slow path toma la rama de asignación grande:

1. redondea tamaño y alineación a unidades de `0x10000`;
2. `FUN_01f9b0f0(0)` selecciona el pool virtual principal;
3. `FUN_01f9b4b0` reserva un rango virtual de ese pool;
4. `FUN_01f9b6b0` respalda/commitea el rango;
5. el puntero virtual resultante se instala como `base/cursor/end` del writer.

El pool 0 parte de `DAT_06c70610` (observado previamente como
`0x1000000000`) y abarca `0x7fc0000000`. El pool 1 parte de
`DAT_06c70618` (observado como `0x8fc0000000`) y abarca `0x40000000` (1 GiB).
Son ventanas **virtuales**; esos tamaños no significan RAM comprometida.

## Reserva, mapeo y liberación física

### Pool 0: el que usa el command buffer estudiado

`FUN_01f9b6b0` llega a `FUN_01f9c0f0`/`FUN_01f9b990`. La rama `pool_type != 1`
selecciona páginas físicas de 64 KiB mediante un bitmap global. Por cada página
construye una entrada de batch con:

- VA destino: `pool_base + offset`;
- offset de direct memory: `page_index << 16`;
- tamaño: `0x10000`;
- flags/protección combinados: `0x0cf2`;
- operación `0` para mapear.

Las entradas contiguas se agrupan y se envían mediante
`sceKernelBatchMap` (`FUN_04dc1610`). El array admite hasta `0x200` entradas
antes de vaciarse.

Al liberar, `FUN_01fea380` -> `FUN_01f9ca70` -> `FUN_01f9cb60` ->
`FUN_01f9c3a0` consulta los rangos con `sceKernelVirtualQuery`. Después devuelve
las páginas al bitmap y agrega entradas BatchMap con operación `1`, offset
físico cero y el mismo `0x0cf2`, es decir, desmapea/decommitea el backing del
rango virtual antes de reciclarlo.

### Pool 1: ruta alternativa, no la seleccionada aquí

`FUN_01f9b990`, cuando `pool_type == 1`, usa:

```c
sceKernelAllocateMainDirectMemory(size, 0x10000, 0x0c, &physical_offset);
sceKernelMapDirectMemory(&va, size, 0x0f2, 0x10,
                         physical_offset, 0);
```

La liberación de esta rama llama a `sceKernelReleaseDirectMemory` tras
`sceKernelVirtualQuery`. Esta segunda ruta confirma independientemente que el
backing administrado por el subsistema es direct memory, aunque el command
buffer de 1 MiB analizado selecciona el pool 0/batch.

## Imports libkernel verificados

Base runtime de `libkernel.sprx`: `0x800000000`.

| Operación | Thunk / GOT | libkernel | NID |
|---|---:|---:|---|
| `sceKernelAllocateMainDirectMemory` | `0x04dc1600` / `0x066d8320` | `+0x18100` | `B+vc2AO2Zrc` |
| `sceKernelMapDirectMemory` | `0x04dbc290` / `0x066d5968` | `+0x18520` | `L-Q3LEjIbgA` |
| `sceKernelBatchMap` | `0x04dc1610` / `0x066d8328` | `+0x18c30` | `2SKEx6bSq-4` |
| `sceKernelVirtualQuery` | `0x04dc1620` / `0x066d8330` | `+0x18dc0` | `rVjRvHJ0X6c` |
| `sceKernelReleaseDirectMemory` | `0x04dbc200` / `0x066d5920` | `+0x183f0` | `MBuItvba6z8` |
| `sceKernelGetDirectMemorySize` | — | `+0x178a0` | `pO96TwzOm5E` |

Los nombres de las cinco primeras funciones están corroborados por su ABI y
por cadenas de error literales en sus callsites; los NID proceden de la tabla
dinámica del `libkernel.sprx` original. `sceKernelGetDirectMemorySize` sólo
consulta capacidad y no participa en reservar el bloque.

## Qué está probado y qué sigue siendo inferencia

**Hechos observados:** tamaño/alineación de 1 MiB/64 KiB; vtable y slow path de
`FMallocBinned3`; reserva separada de VA; compromiso en páginas de 64 KiB;
BatchMap de offsets de direct memory; VirtualQuery y desmapeo al liberar; NID y
offsets anteriores.

**Inferencia fuerte:** la CPU y GPU pueden direccionar esos command buffers sin
un registro AGC adicional visible en esta ruta, gracias al mapeo de main direct
memory. El submit conserva un puntero virtual CPU, no el offset físico.

**Resuelto parcialmente:** código fuente PS5 abierto e independiente define
`CPU_READ=0x01`, `CPU_WRITE=0x02`, `CPU_EXEC=0x04`, `GPU_READ=0x10` y
`GPU_WRITE=0x20`. Por tanto, `0x0f2` y `0x0cf2` contienen de forma demostrable
`CPU_WRITE | GPU_READ | GPU_WRITE`. En ambos queda `0x0c0` sin nombre público;
en `0x0cf2` queda además `0x0c00`. No contienen `CPU_READ` ni `CPU_EXEC` según
esa máscara pública, aunque la CPU del juego sí escribe el command buffer.

La inspección de `FUN_01f9c780` elimina otra ambigüedad: la entrada BatchMap
mide `0x20` bytes; VA, offset físico y tamaño ocupan `+0x00/+0x08/+0x10`, el
valor `0x0cf2` se almacena como protección de 16 bits en `+0x18`, y la operación
map/unmap es un campo de 32 bits separado en `+0x1c`. Los bits `0x0c00` no son,
por tanto, el opcode de la operación mezclado por el decompilador.

**No resuelto:** los nombres y contratos de `0x0c0`/`0x0c00`, su posible modo
de caché/coherencia y el significado contractual del memory type `0x0c`.
Nombrarlos “GPU coherent” o “write-combined” sin más evidencia seguiría siendo
especulación. `tools/decode_memory_protection.py` conserva explícitamente esos
bits como desconocidos. Tampoco está demostrado que esos flags sean apropiados
para framebuffer, texturas, shaders y command buffers por igual.

### Restricción distinta de `MapDirectMemory` y `BatchMap`

El wrapper original de `libkernel.sprx` 12.02 permite separar los dos espacios
de flags sin inventar nombres. En el core de `sceKernelMapDirectMemory`
(`+0x18590`), la protección se enmascara con `0xfffffc0c`; el resultado entra
en el acumulador de argumentos inválidos, se limita a los 14 bits bajos y debe
ser cero. Por tanto, la máscara de protección admitida por esa ruta es
`0x03f3`: `0x33` y `0xf2` pasan, pero `0xcf2` conserva `0xc00` y sería
rechazado antes del syscall con los demás argumentos ordinarios válidos.

El export de `sceKernelBatchMap` (`+0x18c30`) reenvía el array opaco de entradas
y su cantidad al helper del syscall, sin aplicar esa máscara por entrada. Esto
confirma que `0xc00` forma parte de una codificación privada propia de la ruta
batch usada por el pool 0; no es una protección que debamos pasar a
`sceKernelMapDirectMemory`. No demuestra todavía el nombre de esos bits ni que
`0x33` sea suficiente para que AGC haga command fetch. La evidencia queda fijada
por hashes y bytes en `tools/verify_libkernel_mapping_policy.py` y su captura.

### Validación dentro de `FAKE00000`

La fase 0N comparó dos asignaciones de sólo 128 KiB, sin cargar AGC ni hacer
submit. `type=3`/`prot=0x33` funcionó con canarios CPU y cleanup completo.
`AllocateMainDirectMemory(type=0x0c)` también funcionó, pero el primer intento
de `MapDirectMemory(prot=0xf2, flags=0x10)` con VA nula devolvió
`0x80020016`: el flag fijo exige una dirección seleccionada previamente.

La fase 0O corrigió únicamente esa omisión siguiendo el ABI del export
`sceKernelReserveVirtualRange` (NID `7oxv3PPCumo`, `libkernel+0x19340`). Reservó
128 KiB de VA con alineación 64 KiB y después mapeó en esa misma VA la
asignación `type=0x0c` usando `prot=0xf2`, `flags=0x10` y alineación de mapping
cero. Reserva, asignación y mapping devolvieron cero; el puntero no cambió, los
canarios de lectura/escritura CPU pasaron y tanto `munmap` como release
devolvieron cero. Ambas fases terminaron con `submitted=no`, fueron cerradas
por identidad exacta y quedaron retiradas del CLI del supervisor.

Esto probó que `FAKE00000` podía reproducir la política de mapping directo de
los backbuffers de San Andreas. Esas fases no probaron command fetch AGC: el
command pool usa la ruta BatchMap `0xcf2`, cuya parte privada `0xc00` no tiene
equivalente aceptado por `MapDirectMemory`. Posteriormente, Native Label v5 sí
probó command fetch y escritura GPU desde `PPSA99998` usando BatchMap `0xcf2`.

## Implicación para homebrew

El patrón mínimo seguro que sugiere la evidencia es: reservar direct memory,
mapearla con los atributos correctos, escribir comandos dentro de un rango
alineado, mantener ese mapping y todos los recursos referenciados vivos hasta
el fence GPU, y sólo entonces desmapear/liberar o reciclar. Copiar literalmente
Para firmware 12.02, `type=0x0c` con BatchMap `0x0cf2` queda probado para el
arena mínimo de comandos/labels de Native Label v5. Esto no convierte esos
valores en una recomendación universal para backbuffers u otras clases de
buffer; cada clase conserva su propio contrato.
## Unión del administrador con backbuffers VideoOut

San Andreas utiliza el mismo subsistema de reserva virtual para dos clases
relevantes, pero **no** la misma ruta final de backing:

- command segments: pool 0, 1 MiB, alineación 64 KiB y BatchMap `0x0cf2`;
- backbuffers VideoOut: pool 1, tamaño/alineación calculados por el layout AGC,
  Main Direct Memory tipo `0x0c` y MapDirectMemory `0x0f2`, flags `0x10`.

El slot virtual `+0x18` reserva y `+0x38` libera. El backbuffer inicializa el
bit `0x04` en `texture_subobject+0xa0` (`parent+0x100`), por lo que la factory
`0x1f466c0` no toma el fallback del allocator global: llama al método virtual
`+0x28` de la vtable `0x61c7990`, resuelto como `0x1f62870`.

`0x1f62870` llama a `0x1f9b0f0(1)`, selecciona inequívocamente pool 1, impone
alineación mínima de 64 KiB, reserva VA mediante `0x1f9b4b0` y compromete el
rango con `0x1f9b6b0`. La rama `pool_type == 1` de esta última es la ruta
`AllocateMainDirectMemory(type=0x0c)` + `MapDirectMemory(prot=0x0f2,
flags=0x10)`. Su retorno se guarda en `texture_subobject+0x38`, equivalente a
`ResourceCandidate+0x98`, y se pasa después sin transformación a
`sceVideoOutRegisterBuffers2`.

Para los command segments, la resolución del global cierra la identidad
concreta: `0x1f98c04` construye
el objeto estático en `0x6c70650` con vtable `0x61ccf70`, y `0x1f9a4fc`
publica su dirección en `0x6c72280`. El slot `+0x18` es `0x1fef170`
(`FMallocBinned3::Malloc`) y el slot `+0x38` es `0x1fef970` (`Free`). Para el
segmento de 1 MiB, `Malloc` supera el límite `0x20000` de la caché pequeña y
entra en `0x1fe9180`, cuya rama grande reserva VA en pool 0 y compromete páginas
mediante BatchMap `0x0cf2`.

Esto corrige dos simplificaciones. El objeto `0x6c72280` es el heap general de
Unreal y explica los command segments; la superficie presentable usa el método
especial del recurso y pool 1. Que ambas direcciones alimenten AGC no convierte
todo `malloc` en memoria GPU. La diferencia observada establece una primera
clasificación útil aunque los bits privados aún no tengan nombre:

| Clase | Pool | Protección | Tipo/flags |
|---|---:|---:|---|
| Command segment | 0 | `0x0cf2` | BatchMap de páginas existentes |
| Backbuffer VideoOut | 1 | `0x0f2` | type `0x0c`, map flags `0x10` |

Por tanto, para el primer clear no debe reutilizarse automáticamente `0x0cf2`
en la superficie ni `0x0f2` en el command stream.

La misma función enlaza el backing con el descriptor hardware: el puntero
principal de `ResourceCandidate+0x98` se copia a la descripción temporal y
termina codificado como `address >> 8` en el descriptor de 128 bytes apuntado
por `ResourceCandidate+0x90` (`descriptor+0x14/+0x34`, con una segunda copia
en `+0x24/+0x44`). VideoOut recibe en paralelo el valor completo de `+0x98`.
Esto prueba identidad de asignación entre presentación y render target, no
sólo que ambos caminos llaman al mismo allocator.
