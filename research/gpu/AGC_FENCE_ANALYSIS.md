# Análisis de sincronización AGC

Fecha: 2026-09-03
Objetivo: separar la sincronización genérica CPU/GPU de la label usada por el
flip de VideoOut y determinar cuándo es lícito reciclar un command buffer.

Todo este análisis se hizo sobre dumps locales. No se adjuntó un debugger, no
se ejecutaron llamadas dentro del proceso y no se escribió memoria de la PS5.

## Resultado principal

San Andreas usa un fence binario embebido en el propio segmento de command
buffer:

1. reserva los últimos 32 bytes del espacio disponible, alineados a 8 bytes;
2. escribe `1` en CPU en el primer QWORD de esa zona;
3. emite un paquete PM4 `RELEASE_MEM` de ocho DWORDs cuya dirección de destino
   es esa misma zona y cuyo dato es `0`;
4. envía el command buffer;
5. el segmento y los recursos retenidos no pueden reciclarse mientras la label
   conserve el valor distinto de cero;
6. cuando la GPU alcanza el `RELEASE_MEM`, escribe `0`; sólo entonces la cola de
   cleanup puede liberar las referencias y devolver el segmento al allocator.

El significado comprobado puede expresarse así:

```c
// label reside en memoria visible por CPU y GPU
volatile uint64_t *label = align_down(command_end - 32, 8);
*label = 1;                       // pending
agc_release_mem(writer,
                /*event=*/0x28,
                /*dst_sel=*/1,
                /*int_sel=*/3,
                /*address=*/label,
                /*data_sel=*/2,
                /*data=*/0);     // GPU completed

// Regla de ownership
recycle_only_when(*label == 0);
```

La comparación CPU quedó aislada posteriormente en el thread de interrupción.
La regla anterior está demostrada en ambos extremos: inicialización a `1`,
dirección idéntica en el paquete, payload GPU `0` y lectura del mismo puntero
antes de transferir el trabajo al cleanup.

## Evidencia: constructor PM4 genérico

`libSceAgc+0x2700`, export NID `wr23dPKyWc0`, se encuentra en runtime en
`0x80058e700` (base observada `0x80058c000`). Confianza: **alta**.

La función:

- garantiza ocho DWORDs libres en `AgcCommandWriterCandidate`;
- avanza `writer->cursor` exactamente 32 bytes;
- escribe `0xc0064900` como DW0 (`PACKET3 RELEASE_MEM`, opcode `0x49`);
- escribe la dirección de 64 bits en DW3/DW4;
- escribe los datos de 64 bits en DW5/DW6;
- escribe `param_12 & 0x07ffffff` en DW7.

Firma semántica aproximada, no ABI pública confirmada:

```c
uint32_t *AgcEmitReleaseMemCandidate(
    AgcCommandWriterCandidate *writer,
    uint32_t event_type,
    uint32_t cache_action,
    uint32_t dst_sel,
    uint8_t int_sel,
    uint64_t address,
    uint32_t data_sel,
    uint64_t data,
    uint16_t data_lo16,
    uint16_t data_hi16,
    uint8_t address_mode,
    uint32_t context_id);
```

Los nombres exactos de los campos requieren las cabeceras AGC; la posición de
dirección y payload en el paquete está confirmada por la decompilación.

## Evidencia: dos `RELEASE_MEM` distintos en la misma función

En `san-andreas-eboot-runtime.analysis.elf`, `FUN_01f21fd0`:

- la primera llamada, en `0x1f221cc`, usa `data_sel=3`. El builder genera
  `c0064900 06000528 60010000 <addr-lo> <addr-hi> 0 0 0`; su dirección se
  conserva en `work+0x38` y `work+0x58`. La correlación GFX9 identifica el
  selector 3 como reloj/timestamp GPU. Es una label auxiliar, no el fence de
  ownership;
- la segunda llamada, en `0x1f224c3`, es el fence de ownership: calcula
  `label = align_down(segment_end - 32, 8)`, guarda el puntero en `work+0x20`
  y ejecuta `*label = 1` antes de emitir el paquete;
- esa segunda llamada usa event `0x28`, dirección `label`, `data_sel=2` y dato
  `0`. El builder genera
  `c0064900 06000528 42010000 <addr-lo> <addr-hi> 0 0 0`;
- luego reajusta `base/end` del writer para que esos 32 bytes queden dentro del
  command stream enviado y fuera del siguiente tramo utilizable.

La interpretación está cruzada con la definición oficial GFX9 de
`RELEASE_MEM`: selector 2 envía 64 bits, selector 3 envía el reloj GPU. La
prueba local reproduce ambos paquetes ejecutando exclusivamente una copia de
los bytes del builder dentro de un buffer aislado; no ejecuta ni envía PM4 a
la consola.

El verificador reproducible es
`tools/verify_agc_release_fence.py` y su resultado queda en
`captures/agc-release-fence-proof.json`. Ancla por SHA-256 las dos ventanas de
callsite, resuelve el thunk a `libSceAgc+0x2700` y exige avance exacto de 32
bytes del writer.

La misma convención de ownership aparece en `FUN_01f22770`: reserva la cola del
segmento, emite el `RELEASE_MEM` selector 2 hacia ella y conserva el puntero en
el objeto del builder (`+0xc8`). Confianza: **alta**.

La llamada vecina de `FUN_01f21fd0` a `libSceAgc+0x21c0` no es otro fence.
El builder reserva 14 DWORD y escribe la cabecera `0xc00c3f00`; el callsite
`0x1f22441` sólo se alcanza cuando el writer enlaza/rota entre segmentos.
Por tanto, no pertenece al stream mínimo de un único segmento y añadirlo a 0R
no sería una corrección fundada. `tools/verify_agc_segment_link.py` fija el
callsite, thunk, builder, cabecera y tamaño sin contactar la consola.

El trabajo de submission mide `0x98` bytes. Los campos relevantes observados
son:

```c
struct SubmissionWorkFenceFields {
    // ... submit fields at +0x00 .. +0x18
    volatile uint64_t *gpu_done_label; // +0x20; 1=pending, 0=complete
    // ... retained ranges/resources
    int32_t queue_type;                // +0x90; 0=graphics, 1=compute
};
```

## Evidencia: separación submit/cleanup

`AgcSubmissionWorkerCandidate` en `0x01f24bb0` primero encola el trabajo en una
estructura por cola de seguimiento del interrupt thread
(`DAT_06c64e90 + 0x10 + queue_type * 0xd0`) mediante `FUN_01f21d30`. Sólo
después llama a `submitGraphics` o `submitAsyncCompute`.

Al retornar el driver señala únicamente la completion CPU de `work+0x18`.
Esto no libera el trabajo ni demuestra que la GPU haya consumido el stream.
Confianza: **alta**.

El objeto de segmento creado en `FUN_01f22940` contiene:

```c
struct CommandSegmentCandidate {
    void *base;                 // +0x00, bloque de 1 MiB alineado a 64 KiB
    atomic_uint refcount;       // +0x08 (parte baja observada)
};
```

Al rotar de segmento, `FUN_01f22770` incrementa el contador y guarda el objeto
en una lista retenida. `FUN_01f21fd0` transfiere listas/rangos retenidos al
trabajo de submission. Eso evita que se liberen antes del fence. Confianza:
**media-alta**; falta aislar el consumidor de cleanup que decrementa esas
referencias tras observar la label.

## Consumidor exacto de la label

Las cadenas de nombre de thread y sus vtables recuperan estos entry points:

| Thread | Vtable slot `+0x08` |
|---|---:|
| `AgcSubmissionThread` | `0x1f24bb0` |
| `AgcInterruptThread` | `0x1f25040` |
| `AgcCleanupThread` | `0x1f253a0` |

`AgcInterruptThread` extrae trabajos y en `0x1f2517e` comprueba:

```asm
mov  rax, [work + 0x20]
cmp  qword ptr [rax], 0
jne  still_pending
```

La segunda cola repite la secuencia en `0x1f25281`. Sólo cuando la label vale
cero procesa las listas asociadas y llama `0x1f21d30` para encolar el trabajo
en `DAT_06c64e88`, que consume `AgcCleanupThread`. El cleanup no hace polling:
libera referencias, objetos y bloques que el interrupt thread ya declaró
terminados.

```text
SubmissionThread -> driver submit -> InterruptThread comprueba label
                                      |
                                      +-- != 0: retiene el trabajo
                                      +-- == 0: lo pasa a CleanupThread
```

Antes del barrido, el interrupt thread espera mediante la infraestructura de
evento importada en `0x4dc0c80`. Ese thunk resuelve a
`libkernel+0x1cf50`, NID `fzyMKs9kim0`, confirmado con el generador NID del SDK
como `sceKernelWaitEqueue`. La llamada usa un máximo de un evento y timeout
nulo, por lo que el thread queda bloqueado hasta que el driver lo despierta.

La inicialización completa alrededor de `0x1f418c9..0x1f41a1d` resuelve:

| Thunk | Destino | NID / función |
|---|---|---|
| `0x4dc0f80` | `libkernel+0x1ce70` | `D0OdFMjp46I`, `sceKernelCreateEqueue` |
| `0x4dc0f90` | `libSceAgcDriver+0x64d0` | `w2rJhmD+dsE`, registro de evento AGC |
| `0x4dc0fa0` | `libkernel+0x1d960` | `WDszmSbWuDk`, `sceKernelAddUserEventEdge` |
| `0x4dc0c80` | `libkernel+0x1cf50` | `fzyMKs9kim0`, `sceKernelWaitEqueue` |

La espera real es por tanto dirigida por eventos, seguida de una comprobación
ordinaria de la label. Un primer homebrew no debe bloquear indefinidamente en
esa equeue hasta validar el registro de evento. El fallback conservador es
leer la label con semántica acquire, aplicar pausa/backoff y abortar por deadline
sin liberar ni reutilizar memoria si no llega a cero.

Los selectores también quedan cerrados por los argumentos y las aserciones
UTF-16 adyacentes:

- `addEqEvent(equeue, AgcAsyncComputeQueue, nullptr)`: selector `0x20`;
- `addEqEvent(equeue, AgcGraphicsQueue, nullptr)`: selector `0x00`;
- `sceKernelAddUserEventEdge(equeue, kWakeThreadUserEvent)`: id `0x1800`.

La equeue se crea con el nombre literal `AgcEqueue`. Para nuestro primer clear
sólo interesa registrar el selector graphics `0`; async-compute y el evento
manual de wake no pertenecen al mínimo funcional hasta confirmar shutdown.

### Shutdown observado

El destructor del objeto de interrupción está en `0x1f58da0` y fija el orden:

1. escribe `1` en `interrupt_object+0x1b8` para solicitar parada;
2. llama `sceKernelTriggerUserEvent(equeue, 0x1800, nullptr)` mediante el NID
   `F6e0kwo4cnk`, despertando una espera bloqueada;
3. espera/finaliza el objeto de thread mediante sus slots virtuales `+0x18` y
   `+0x28`;
4. llama `sceKernelDeleteEqueue`, NID `jpFjmgAC5AE`.

No hay un export separado de “removeEqEvent” en esta ruta: la asociación del
driver deja de ser utilizable al destruir la equeue. Para un probe, la equeue
no se destruye hasta detener y unir el thread que puede estar bloqueado en
`sceKernelWaitEqueue`.

## La ruta VideoOut no es el fence genérico

`libSceAgc+0x7b70`, NID `YUeqkyT7mEQ`, es un wrapper de tamaño/capacidad que
termina llamando al import del driver `libSceAgcDriver+0x71d0`, NID
`cwbxjPSJ7WQ`. Confianza: **alta**.

La decompilación del driver demuestra que `+0x71d0` integra el end-of-pipe flip:

- llama a una rutina identificada por su mensaje como
  `sceVideoOutSubmitEopFlip`;
- si el índice de display buffer es válido, llama a
  `sceVideoOutGetBufferLabelAddress`;
- calcula `flip_label = label_base + displayBufferIndex * 8`;
- emite otro `RELEASE_MEM` dirigido a `flip_label`;
- en DW5 escribe `1` cuando el índice es válido, y `0` cuando se usa el caso
  especial de índice negativo;
- DW7 contiene información devuelta por `sceVideoOutSubmitEopFlip` enmascarada
  a 28 bits.

Por tanto esa label pertenece al protocolo de presentación/backbuffers. No debe
usarse como sustituto del fence genérico de ownership de command buffers.

La función completa `AgcDriver+0x71d0` (636 bytes, SHA-256
`35cfe28edbb5c117edd83d29d8dd5feef62c81069338ef8b4829ac7d65078b83`)
coincide entre el módulo del sistema y el dump runtime autorizado. El verifier
ancla además los cuatro calls a submit EOP, obtención de label, estado VideoOut
y reserva del `RELEASE_MEM`, junto con los stores del packet. Esto demuestra la
existencia y forma de la ruta EOP; los bits exactos del evento de caché siguen
sin semántica suficiente para copiarla a un homebrew.

Artefacto: `captures/agc-eop-flip-proof.json`, generado por
`tools/verify_agc_eop_flip.py`.

El wrapper también fija cuál de las variantes del driver usa una DCB real.
`sceAgcDcbSetFlip` (`libSceAgc+0x7b70`, 188 bytes, idéntico en
sistema/runtime) pasa siempre `driver_mode=0` al thunk `+0x16df0`. El packet
resultante lleva `DW1=0x0620062f`. Con los campos públicos GFX10 se correlaciona
como `event_type=0x2f (CS_DONE)`, `event_index=6 (shader_done)` y
`gcr_cntl=0x200 (GL2 writeback)`. Aunque la rutina llama a
`sceVideoOutSubmitEopFlip`, PAL restringe formalmente los cache sync de
`RELEASE_MEM` a eventos EOP. Esta combinación EOS+GL2WB debe tratarse como una
extensión PS5 aún sin semántica contractual pública, no sustituirse por un
packet PAL inventado ni marcarse como coherencia demostrada.

El wrapper revela asimismo el ABI del builder privado del driver, sin necesidad
de cargar la capa alta de `libSceAgc`: `cwbxjPSJ7WQ(writer**, capacity_dwords,
mode=0, videoout_handle, buffer_index, flip_mode, flip_arg_u64)`. Su consulta
de tamaño devuelve 64 DWORD como capacidad máxima. El ABI está probado
estáticamente por el movimiento de argumentos del wrapper, pero resolver y
llamar ese NID desde `FAKE00000` aún no está probado y no forma parte de 0M.

Ese builder no es una función pura de serialización: llama a
`sceVideoOutSubmitEopFlip` en `+0x724c` y sólo después materializa el packet en
`+0x7372`. En consecuencia queda prohibido un experimento build-only con un
handle VideoOut vivo. La operación futura debe ser transaccional: construir
SetFlip, someter exactamente ese mismo stream y conservar writer, mapping,
buffers, labels y estado VideoOut hasta completion. Si no se puede garantizar
esa secuencia, no se llama al builder.

## Regla segura obtenida

Para un homebrew, el retorno exitoso de `submitGraphics` sólo autoriza a dejar
de tocar el descriptor de llamada. No autoriza reutilizar la memoria señalada
por él.

La condición conservadora demostrada es:

```text
submit retornó AND label GPU cambió de 1 a 0
```

Sólo después se puede reciclar el segmento y cualquier shader, textura,
descriptor o allocation retenida exclusivamente por ese submission. La lectura
CPU del juego es una comparación ordinaria de la label alojada dentro del mismo
segmento directo que el command buffer; el draft 0M usa una carga atómica
`acquire`, backoff de 1 ms y deadline de 2 s. Esto reproduce de forma
conservadora el ownership observado. Native Label v5 confirmó además en
hardware que la GPU del proceso homebrew ve el mapping: `DMA_DATA` cambió el
target y el `RELEASE_MEM` posterior cambió la label. Ante timeout, la regla
sigue siendo no liberar ni reutilizar memoria.

## Pendientes verificables

1. Integrar el protocolo ya demostrado en la transacción acotada de VideoOut.
2. Identificar todas las operaciones finales que decrementan las referencias.
3. Distinguir qué convenciones observadas son generales de AGC sin convertir el
   análisis de juegos comerciales en requisito de la ruta homebrew.
