# Análisis inicial de libSceAgc

Programa Ghidra: `/gpu/game-libSceAgc.analysis.elf`.
Base runtime observada: `0x80058c000`. Los nombres terminados en `Candidate`
son hipótesis explícitas, no símbolos oficiales recuperados.

## Ciclo de vida del módulo

`AgcModuleInitializeCandidate` (`0x800599b30`) está referenciado por un puntero
de datos en `0x8005b4a18`, consistente con una tabla de constructores. La función:

1. obtiene información del entorno;
2. crea `SceAgcMutex`;
3. llama a `libSceAgcDriver+0x9d0` (NID `Um-jkyDy9rI`) para obtener base y
   tamaño de DMEM;
4. prepara una tabla interna y exige que quede en `0xfe0040000`;
5. consulta configuración/capacidades;
6. habilita opcionalmente GPU shader transcoding;
7. pasa un registro de 16 bytes a `libSceAgcDriver+0x6680` (NID
   `aCfbPzyjU90`).

`AgcModuleFinalizeCandidate` (`0x800599d10`) destruye `SceAgcMutex`, por lo que
encaja como finalizador del módulo.

Inferencia: una carga válida de `libSceAgc` ejecuta automáticamente parte
importante de la inicialización. No hay evidencia todavía de que cargarla sea
suficiente para crear una cola o de que `FAKE00000` tenga los permisos exigidos.

## Cruces confirmados hacia libSceAgcDriver

### `AgcDriverGetDmemCandidate` — driver `+0x9d0`, NID `Um-jkyDy9rI`

Firma inferida con confianza alta:

```c
uint64_t candidate(uint64_t *base_out, uint32_t *size_out);
```

- Devuelve `0x8a6d0003` si cualquiera de los outputs es nulo.
- Con outputs válidos devuelve cero.
- Entrega una base derivada del estado global del driver.
- Convierte un tamaño negativo/sentinel en cero.

### `AgcDriverRegisterInitMetadataCandidate` — driver `+0x6680`, NID `aCfbPzyjU90`

Firma provisional:

```c
uint64_t candidate(const Entry16 *entries, uint32_t count);
```

Recorre registros de 16 bytes, reconoce al menos el tipo `6`, almacena un valor
de ocho bytes y consulta información adicional del runtime. `libSceAgc` lo llama
con un registro y `count=1` al terminar su constructor.

## Transcodificación de shaders

`AgcShaderTranscodeWorkaroundInit` (`0x80059ab80`) sólo se ejecuta cuando una
capacidad/configuración lo habilita. Detecta procesos replay, carga
`libSceShaderTranscode_minimal`, reserva hasta `0x20000000` bytes para su estado
y puede crear un log bajo `/hostapp`. No parece ser el camino mínimo necesario
para nuestro primer submit y se pospone.

## Próxima pregunta

Identificar cómo el juego importa/carga `libSceAgc` y cuál es la primera API
pública que utiliza después del constructor. Para ello necesitamos reconstruir
NIDs/import slots desde el eboot o recuperar metadata dinámica del módulo; no se
debe llamar por offsets runtime desde el homebrew.

## Imports AGC observados en el juego

Un scan read-only de punteros alineados encontró 280 referencias hacia el
segmento ejecutable de `libSceAgc`:

- una tabla compacta del eboot en torno a `0x6bf8d90`, con aproximadamente 44
  destinos AGC directos;
- una tabla mucho más amplia dentro de `libSceVdecCore.native.sprx`;
- punteros transitorios en stacks/threads, que no son metadata estable;
- punteros internos del propio módulo, incluidos constructor y finalizador.

Se guardó únicamente el mapping read-only de 992 KiB que contiene la tabla del
eboot. La tabla ya está relocada y contiene direcciones resueltas; los NIDs no
aparecen como texto adyacente. Hace falta correlacionarla con la metadata
dinámica del eboot o con sus callsites para asignar nombres fiables.

Decisión: priorizar las ~44 entradas importadas directamente por el motor y no
la tabla completa del decodificador. Tampoco se usarán punteros de stack como
evidencia de imports.

## Eboot reconstruido y callsites

Se capturaron de forma read-only los siete mappings `executable` del juego y se
reconstruyó `/gpu/game-eboot-runtime.analysis.elf` con las direcciones virtuales
originales. La imagen contiene un segmento `r-x` de 94.896.128 bytes y conserva
la tabla relocada del proceso. No se adjuntó debugger, no se hicieron llamadas
remotas ni se escribió memoria del juego.

El barrido x86-64 RIP-relative confirmó una PLT especialmente limpia:

- 44 stubs `jmp [rip+disp32]` consecutivos en `0x5e7d3c0..0x5e7d6d0`;
- cada stub apunta a una de las 44 entradas AGC de `0x6bf8d90..0x6bf8f18`;
- existen 770 instrucciones `call rel32` hacia esos stubs;
- 30 de las 44 entradas tienen al menos un caller directo detectado;
- 11 offsets concentran aproximadamente el 95% de esas llamadas.

Precaución interpretativa: muchas de estas llamadas están dentro de una capa de
validación/command-building del SDK enlazada en el eboot. Por tanto, `770` no es
el número de submits del juego ni implica 770 APIs llamadas directamente desde
gameplay. El registro reproducible está en
`sessions/game-eboot-agc-refs.json`; el generador es
`tools/find_rip_import_refs.py`.

## Bootstrap de estado de contexto

La función del eboot `0x5dc3b80` se ejecuta una sola vez bajo un guard atómico,
inicializa tablas globales y llama a tres imports AGC únicos:

- AGC `+0x9990`: inicialización grande dependiente de versión/capacidades;
- AGC `+0x9ed0`: obtiene/construye una familia de tablas de estado por versión;
- AGC `+0xa0b0`: obtiene/construye la familia complementaria.

El análisis de `libSceAgc` muestra que `+0x9990` reserva y combina mapas de
registros de contexto, ordena listas y finalmente construye tres tablas densas
de `0x800` entradas. También distingue generaciones/versiones mediante un
argumento pequeño y contiene diagnósticos explícitos sobre estado de contexto
incompleto. Los offsets `+0x9ed0` y `+0xa0b0` seleccionan implementaciones según
esa versión y capacidades de hardware.

Inferencia con confianza alta: este trío pertenece al bootstrap de tablas de
estado/context registers, no a creación de swapchain ni al submit por frame.
Es una pista valiosa para compatibilidad, pero el camino mínimo de homebrew debe
buscar primero las rutinas pequeñas que crean cola/contexto y presentan el
buffer. Los nombres `AgcOffset_*` usados en Ghidra siguen siendo etiquetas por
offset, no nombres oficiales.

## Clasificación inicial del ABI de command buffers

La forma repetida del primer argumento ya permite inferir una estructura común
de escritor de comandos:

```c
struct AgcCommandWriterCandidate {
    /* +0x10 */ uint32_t *cursor;
    /* +0x18 */ uint32_t *end;
    /* +0x20 */ bool (*grow)(void *self, uint32_t required_dw, void *cookie);
    /* +0x28 */ void *cookie;
    /* +0x30 */ uint32_t reserved_dw;
};
```

Las funciones comprueban `end-cursor`, descuentan `reserved_dw`, invocan el
callback de crecimiento si falta espacio, alinean el cursor a cuatro bytes,
escriben paquetes y adelantan `cursor`. Esto es construcción CPU-side; por sí
solo no demuestra ejecución ni submit.

Familias observadas entre las entradas más usadas:

- `+0x28d0` y `+0x2ab0`: escriben uno o varios paquetes variables con cabecera
  basada en `0xc0007600`; el segundo agrupa rangos consecutivos.
- `+0x2370`: paquete fijo de cinco DWORD, cabecera `0xc0031500`.
- `+0x200` y `+0x3830`: paquetes de ocho DWORD con cabecera `0xc0065800`,
  direcciones divididas/normalizadas y flags dependientes de capacidades.
- `+0x4c90` y `+0x4120`: paquetes de cinco DWORD con direcciones de 64 bits,
  cabeceras `0xc0036300` y `0xc0039f00`.
- `+0x49b0` y `+0xf10`: paquetes variables `0xc0003700`, casi gemelos pero con
  codificación de flags/dirección diferente; probablemente variantes por tipo
  de recurso o etapa.
- `+0x8f0` y `+0x5ce0`: paquetes de control/evento basados en `0xc0004600`.
- `+0x47d0`, `+0x4680` y `+0x1170`: comandos más especializados que incorporan
  direcciones de 64 bits y parámetros de sincronización/copia.
- `+0xef70`: valida y reloca una representación de shader identificada por la
  firma `0x34333231`; incluye el camino opcional de shader replacement.
- `+0xfd40`, `+0x10e90` y parte de `+0xd070..+0xd320`: clonado, ajuste y
  parcheo de descriptores/representaciones compiladas, no submit. La entrada
  `+0xd040` se corrige por evidencia de caller: es un resolvedor de payload de
  paquetes; con argumento no cero devuelve `packet+8` y se usa junto a
  `+0x28d0` para obtener la zona de datos de un paquete raw `0x76`.

Conclusión provisional: la muestra directa de `libSceAgc` está dominada por
serialización de paquetes PM4 y preparación de shaders. La creación de colas y
el submit probablemente se producen a través de la inicialización interna de
AGC/AGCDriver; la presentación final puede estar separada en VideoOut. Por eso
la próxima comparación debe observar simultáneamente imports de AGC,
AGCDriver y VideoOut en otro juego nativo.

## Comparación con San Andreas Definitive Edition

La captura durante gameplay encontró 7.621 mappings en el proceso, frente a
2.002 en la captura de RE2. Esto explicó los timeouts iniciales de inventario;
no era una restricción de permisos. `capture_inventory.py` admite ahora
`--timeout` y `--foreground-only` para casos así.

Las regiones kernel/runtime relacionadas con GPU coinciden en nombre y tamaño
con RE2. San Andreas además deja visibles tres stacks de 256 KiB:

- `AgcSubmissionThread`;
- `AgcInterruptThread`;
- `AgcCleanupThread`.

Su eboot importa 62 offsets de `libSceAgc`: 41 son compartidos con los 44 de
RE2, 21 aparecen sólo en esta muestra y tres sólo en RE2. La intersección de 41
es nuestro candidato actual a núcleo AGC portable. El barrido del nuevo eboot
encontró 62 stubs exactos y 164 `call rel32` directos.

### Cruce directo con AGCDriver

San Andreas importa directamente sólo cuatro funciones de `libSceAgcDriver`,
con cinco callsites en total:

- driver `+0x29d0`, NID `gSRnr79F8tQ`: submit de async-compute; selecciona una estructura de cola
  mediante un identificador pequeño;
- driver `+0x2970`, NID `AhGvpITrf4M`: variante de submit graphics que usa la cola de
  interrupciones y devuelve `0x8a6d0003` si no está implementada;
- driver `+0x2960`, NID `UglJIZjGssM`: la otra variante de submit graphics;
- driver `+0x64d0`, NID `w2rJhmD+dsE`: registra una operación/evento mediante la capa kernel con
  selector interno `0x1fff2` y traduce el error del sistema.

Las cadenas UTF-16 referenciadas por esos callsites revelan:

- `Agc::submitAsyncCompute(...)` alrededor de la llamada a `+0x29d0`;
- `Agc::addEqEvent(AgcEqueue, AgcAsyncComputeQueue, nullptr)` alrededor de
  `+0x2970`;
- `Agc::addEqEvent(AgcEqueue, AgcGraphicsQueue, nullptr)` alrededor de
  `+0x2960`;
- una ruta vecina `sceKernelAddUserEventEdge(...)` durante la preparación del
  equeue.

La decompilación completa del worker `0x1f24bb0` permite precisar el flujo. Cada
trabajo contiene al menos puntero de command buffer, tamaño en DWORDs, tipo de
cola y un flag de variante. El worker espera trabajo, rechaza tamaños de
`0x100000` DWORDs o mayores, llama a `+0x29d0` para async-compute y a
`+0x2960/+0x2970` para graphics. Después libera/notifica el objeto de completion
y continúa. Las aserciones completas recuperadas son
`Agc::submitAsyncCompute(...)` y `Agc::submitGraphics(...)`.

Conclusión con confianza alta: los tres primeros offsets son anclas reales del
submit; `+0x64d0` queda asociado a la creación de eventos equeue. Los NID se
recuperaron de la tabla dinámica del SPRX original de firmware 12.02 y por ello
son identificadores de export reales. Los nombres semánticos siguen viniendo
de las aserciones y callsites del juego: el módulo no incluye nombres C/C++.

### ABI mínima observada del submit

El worker construye en su stack un descriptor compacto y pasa su dirección al
driver. La forma mínima compatible con la evidencia actual es:

```c
struct AgcSubmitInfoCandidate {
    const uint32_t *command_buffer; // +0x00
    uint32_t size_dwords;           // +0x08
    uint8_t field_0c;               // +0x0c, el worker escribe cero
    uint8_t padding[3];
};
```

Las dos variantes graphics reciben un único puntero a este descriptor. La ruta
async-compute calcula además un selector entero de cola y llama a una forma
equivalente a `(queue_selector, &submit_info)`. El trabajo interno del juego,
que no debe confundirse con el descriptor público del driver, contiene:

```c
struct SubmissionWorkCandidate {
    uint8_t unknown_00;
    uint8_t graphics_variant;       // +0x01: 0 -> +0x2960, 1 -> +0x2970
    uint16_t queue_event_selector;  // +0x02
    const uint32_t *submit_pointer; // +0x08
    uint32_t submit_size_dwords;    // +0x10
    uint8_t completion_flags;       // +0x14
    void *completion;               // +0x18
    uint8_t unknown_20[0x70];
    int32_t queue_type;             // +0x90: 0 graphics, 1 async-compute
};
```

El límite `< 0x100000` DWORDs pertenece al worker de este juego. No se debe
presentar todavía como límite contractual de AGCDriver. Antes de invocar estos
exports desde homebrew falta determinar inicialización, propiedad de memoria,
alineación y mecanismo de fence/completion; probarlos a ciegas podría colgar la
cola gráfica del sistema.

### Ownership y rotación de command buffers

El seguimiento hacia atrás desde `AgcSubmissionWorkerCandidate` identifica ya
una parte concreta del contrato de memoria usado por San Andreas:

- `FUN_01f22940` pide al allocator usado por el RHI un bloque de `0x100000`
  bytes con
  alineación `0x10000`;
- instala el rango como `[base, base + 0x100000)` en el command writer y pone
  tanto cursor como inicio en `base`;
- el bloque se guarda en un pequeño objeto con contador de referencias;
- al cerrar un submission, `FUN_01f21fd0` captura `base`, cursor final y tamaño
  en DWORDs, construye el trabajo de `0x98` bytes y lo entrega a la cola;
- `FUN_01f22770` no reutiliza simplemente el bloque entregado: incrementa su
  referencia y lo mueve a una lista de recursos retenidos antes de preparar el
  writer siguiente;
- el worker señala el objeto de completion después del retorno del driver, y
  la ruta productora puede esperar y liberar los recursos retenidos.

Por tanto, en este contexto **ownership** significa que el productor CPU no
puede modificar, liberar ni reciclar el command buffer mientras el submission
o su completion todavía lo retengan. Un puntero virtual válido no basta: la
memoria debe proceder de un allocator/mapeo aceptado por GPU, conservar su
alineación y vivir hasta la señal de finalización correspondiente.

Hay dos constantes distintas que no deben mezclarse:

- `0x100000` **bytes**: tamaño de segmento elegido por este RHI;
- `< 0x100000` **DWORDs**: validación del tamaño de submission en el worker.

La alineación de `0x10000` y el segmento de 1 MiB son evidencia del diseño de
este juego, no límites universales de AGC. Los submissions que cruzan segmentos
parecen enlazarse mediante paquetes AGC/PM4; falta cerrar esa transición y
resolver qué allocator se encuentra detrás de `PTR_PTR_06c72280`.

El primer cruce de su vtable matiza esa última pregunta: los métodos observados
en `+0x18`, `+0x28`, `+0x38`, `+0x40` y `+0x88` tienen la forma de
`Malloc(size, alignment)`, `Realloc`, `Free`, consulta de tamaño y consulta de
thread-safety de un allocator general de Unreal. Además, la inicialización
imprime `Used memory before allocating anything`. Así que todavía no es
correcto llamarlo directamente “allocator GPU”. La hipótesis más fuerte es que
el port de PS5 proporciona a ese interfaz memoria ya apropiada o mapeable para
el RHI, o que AGC realiza el registro implícitamente. Debemos localizar la
implementación concreta detrás de la vtable antes de copiar este patrón.

La implementación concreta ya se identificó como `FMallocBinned3`. Su ruta
grande redondea a páginas de 64 KiB y obtiene espacio de dos pools virtuales:

- pool principal desde `0x1000000000`, con ventana de `0x7fc0000000` bytes;
- pool secundario desde `0x8fc0000000`, con ventana de 1 GiB.

Estas ventanas son espacio virtual reservado, no RAM físicamente consumida de
una vez. El export `libkernel+0x178a0`, NID `pO96TwzOm5E`, quedó identificado
exactamente como `sceKernelGetDirectMemorySize`; informa el tamaño de direct
memory para configuración/telemetría, pero no es el allocator. El pool usa un
bump allocator virtual, metadata jerárquica y un hilo auxiliar. La rutina que
respalda/commitea páginas físicas todavía debe aislarse dentro de ese subsistema.

### Dos completions diferentes

La completion en `SubmissionWorkCandidate+0x18` es una señal **CPU**: el worker
la activa inmediatamente después de que retorna el export de submit del
driver. Demuestra que el trabajo fue entregado, pero por sí sola no demuestra
que la GPU haya terminado de ejecutar el command buffer.

El finalizador del command stream inserta además paquetes AGC antes de
encolarlo. Una ruta de presentación posterior consulta
`sceVideoOutGetFlipStatus`, espera con `sceVideoOutWaitVblank` y ajusta el flip
rate. Esto confirma que la espera de presentación es independiente de la
completion CPU. Queda pendiente identificar el writeback/fence GPU contenido
en esos paquetes AGC y la lectura que autoriza reciclar el segmento.

La extracción del SPRX original permite precisar dos anclas:

- `libSceAgc+0x2700`, NID `wr23dPKyWc0`, emite exactamente ocho DWORDs y
  comienza con `0xc0064900`: un paquete PM4 `RELEASE_MEM` (opcode `0x49`);
- `libSceAgc+0x7b70`, NID `YUeqkyT7mEQ`, es un wrapper de sincronización que
  termina entrando a `libSceAgcDriver+0x71d0`, NID `cwbxjPSJ7WQ`; esa rutina
  también construye un `RELEASE_MEM` y paquetes asociados según sus flags.

Esto confirma el mecanismo general del fence: la GPU ejecuta `RELEASE_MEM` al
final de la cola y escribe un valor en una dirección visible para CPU. El paso
restante es identificar en el objeto del RHI la dirección de label y el valor
esperado, y localizar el bucle/evento que lo consume antes de liberar recursos.

## Unión con VideoOut

El eboot de San Andreas tiene ocho imports ejecutables de `libSceVideoOut` y
diez callsites directos. La decompilación los clasifica así:

- `+0x109b0`: apertura del dispositivo (`sceVideoOutOpen`, confianza alta);
- `+0x124c0`: cierre/liberación del handle (`sceVideoOutClose`, alta);
- `+0x2c20`: inicialización de atributo de 64 bytes
  (`sceVideoOutSetBufferAttribute2`, alta);
- `+0x11920`: registro de buffers/atributos con ocho argumentos
  (`sceVideoOutRegisterBuffers2`, alta);
- `+0x116f0`: operación handle+entero consistente con
  `sceVideoOutSetFlipRate` (media-alta);
- `+0x138d0`: contiene literalmente `sceVideoOutWaitVblank` (confirmado);
- `+0x11c50`: obtiene/copia un estado de 64 bytes
  (`sceVideoOutGetFlipStatus`, confianza alta);
- `+0x12220`: obtiene estado de resolución/display y el juego inspecciona su
  segundo DWORD (`sceVideoOutGetResolutionStatus`, confianza alta).

No aparece un callsite PLT directo inequívoco de `sceVideoOutSubmitFlip` entre
estos ocho imports. Existe un noveno puntero relocado en datos hacia VideoOut
`+0x4bc`, pero carece de referencia RIP-relative directa y no se ha demostrado
que apunte al comienzo de una API pública. La presentación puede realizarse de
forma indirecta mediante una tabla/vtable del RHI; esa pasa a ser la siguiente
búsqueda concreta.

El examen de los callsites aclara su fase de uso: primero se construye el
atributo con `+0x2c20` y se registran los backbuffers con `+0x11920`. En otra
ruta se consulta repetidamente `+0x11c50`, se espera vblank mediante `+0x138d0`
mientras quedan flips pendientes y finalmente se aplica `+0x116f0`.

El supuesto noveno puntero resultó formar parte de metadata de relocación, no
de una vtable ejecutable, y se descarta. No hay llamada directa a
`sceVideoOutSubmitFlip` por frame en el eboot. Esto sugiere que el camino nativo
PS5 integra la presentación en el trabajo enviado por `Agc::submitGraphics`,
mientras VideoOut se ocupa de registro, estado y sincronización. Es una
inferencia fuerte para este título, pendiente de confirmar en un segundo juego
nativo.

### Descriptor de superficie recuperado en San Andreas

El callsite `0x1f57014` permite reconstruir los ocho argumentos de
`sceVideoOutSetBufferAttribute2` sin inferirlos por nombres:

```c
sceVideoOutSetBufferAttribute2(&attr, format_word, 0,
                               width, height, 0, 0, 0);
```

`width` y `height` provienen de los DWORDs `+0x20/+0x24` del objeto de salida.
El formato por defecto es `0x8000000000000000`; una rama de configuración usa
`0x8100070400000000`. Aún no se asignan nombres oficiales a esos bits. El
atributo resultante se pasa intacto al callsite `0x1f5703d`:

```c
sceVideoOutRegisterBuffers2(handle, 0, 0, buffers, count, &attr, 0, NULL);
```

La matriz `buffers` tiene stride `0x20` y el primer QWORD de cada descriptor es
la dirección obtenida del recurso del motor en `resource+0x98`. Esto confirma
que VideoOut recibe direcciones de backbuffer ya creadas por el subsistema GPU;
no demuestra que un mapping de memoria directa arbitrario sea apto para AGC.

Nuestro probe CPU ya validó por hardware una ruta separada con dos buffers
BGRA, `format_word=0x8000000022000000`, dimensiones de salida y pitch lógico
redondeado a 64 píxeles. Por tanto VideoOut/open/register/flip no es ya una
incógnita absoluta; el hueco específico es hacer que **la misma superficie**
tenga registro/acceso AGC y atributos coherentes con el render target. Para el
primer clear no debemos copiar ciegamente el formato del juego: primero se
comparará el descriptor AGC del recurso correspondiente con el `format_word`
entregado a VideoOut.

El constructor que alimenta esa ruta está en `0x1f57fd0`. Recibe resolución y
dimensiones, abre VideoOut y fija explícitamente `buffer_count=2` en el objeto
de salida (`+0x18`). Crea dos objetos de recurso mediante la misma factory y
los conserva en un vector de punteros en `output+0x38`. El registro posterior
itera exactamente ese vector y extrae `resource+0x98` para el primer QWORD de
cada descriptor VideoOut. La destrucción libera primero el registro VideoOut y
después las referencias de ambos recursos.

Layout parcial confirmado:

```c
struct NativeOutputCandidate {
    // ...
    uint32_t buffer_count;       // +0x18, inicializado a 2
    uint32_t width;              // +0x20
    uint32_t height;             // +0x24
    int32_t videoout_handle;     // +0x30
    ResourceCandidate **buffers; // +0x38
};

struct ResourceCandidate {
    // ... descriptor/ownership AGC aún por separar ...
    void *display_address;       // +0x98, pasado a VideoOut
};
```

La factory observada devuelve objetos desde pools globales específicos del
backend y no es una simple llamada de memoria directa. Esto refuerza que el
paso correcto es identificar el constructor/vtable de `ResourceCandidate` y
su registro AGC, no imitar sólo el puntero `+0x98`.

### Correlación del administrador de memoria con VideoOut

La función `0x1f56c20` crea para cada buffer un objeto de `0x180` bytes y llama
a `0x1f466c0` con una descripción de textura que incluye formato, dimensiones,
usage y flags. Dentro de esa rutina se calcula primero el layout de memoria. El
backbuffer lleva el bit especial `0x04` en `texture_subobject+0xa0`; por ello
los resultados de tamaño/alineación se entregan al método virtual `+0x28` de
la vtable de textura (`0x1f62870`), no al fallback global `0x6c72280`.
`0x1f62870` selecciona pool 1 y acaba en Main Direct Memory tipo `0x0c`,
protección `0x0f2`, map flags `0x10`. El puntero devuelto se guarda exactamente
en `texture_subobject+0x38`, que corresponde a `ResourceCandidate+0x98`; ese
mismo valor termina como QWORD 0 del descriptor entregado a VideoOut.

El fallback ordinario tiene una semántica consistente en callsites
independientes:

```c
address = allocator->vtable[3](allocator, size, alignment); // slot +0x18
allocator->vtable[7](allocator, address);                   // slot +0x38
```

En `0x1f229df` ese slot reserva un segmento de command buffer con
`size=0x100000` y `alignment=0x10000`, entrando al pool 0 y BatchMap `0x0cf2`.
El backbuffer, en cambio, usa la ruta virtual especial descrita arriba. Ambos
participan del mismo administrador de rangos del backend, pero no pertenecen a
la misma instancia/ruta final de `FMallocBinned3` ni comparten protección.

No se observa una llamada separada de “registrar esta dirección” entre la
reserva especial y la construcción de descriptores. La accesibilidad GPU se
establece en el backing/protección y en el descriptor AGC, no mediante un
registro posterior por recurso visible aquí. La clasificación concreta es:
command stream en pool 0/`0x0cf2`; superficie presentable en pool 1/type
`0x0c`/`0x0f2`/flags `0x10`. Los nombres de los bits privados y su semántica de
caché siguen pendientes.

El método de contexto `0x1f2f9e0` fue descartado como consumidor del descriptor
de render target aunque también lee un campo `+0x98`: llama a
`libSceAgc+0x4590` (NID `xSAR0LTcRKM`), que emite `0xc0023f00`/PM4
`INDIRECT_BUFFER`, y a `+0xcf60` (NID `w6Dj1VJt5qY`) para ajustar el bit 0 del
registro. Esa ruta ejecuta command buffers indirectos y el offset coincidente
pertenece a otro tipo de objeto.

Los dos consumidores verdaderos quedaron identificados y, con ello, se corrigió
la clasificación de los descriptores. La ruta `0x1f37f80` corresponde a
depth/stencil: el recurso sale de `context+0xee8`, `0x1f37fa5` carga
`resource+0x30` en `RSI`, fija `EDX=0x10` y llama al thunk `0x4dc0d30`. La ruta
color MRT es `0x1f382f0`: lee `view+0x28`, copia exactamente `0x80` bytes,
ajusta los IDs por slot y entrega los 16 pares al cache writer `0x4db80e0`.

Ambas rutas acaban materializándose mediante `libSceAgc+0x4120`, NID
`ZvwO9euwYzc`. Esta función emite un paquete de cinco DWORDs con header
`0xc0039f00`, dirección de lista y conteo limitado a 14 bits. La reproducción
exacta está automatizada en `tools/verify_rt_descriptor_consumer.py`.

### La misma dirección en VideoOut y el descriptor de render target

La correlación puede hacerse dentro de una sola invocación de `0x1f466c0`:

1. `0x1f46934` reserva la superficie principal y `0x1f4694b` guarda el
   resultado en `texture_subobject+0x38`, o `ResourceCandidate+0x98`.
2. En la rama de render target, `0x1f4745b` y `0x1f47463` copian ese mismo
   valor a los primeros slots de direcciones de la descripción temporal.
3. `0x1f476a2` reserva un descriptor de `0x80` bytes y `0x1f476a5` guarda su
   puntero en `texture_subobject+0x30`, o `ResourceCandidate+0x90`.
4. `0x1f47f57..0x1f47f6f` toma el primer slot, desplaza la dirección ocho bits
   y almacena sus partes en `descriptor+0x14` y `descriptor+0x34`. La segunda
   copia se codifica análogamente en `+0x24/+0x44`.
5. VideoOut lee `ResourceCandidate+0x98` en `0x1f56fb0` y escribe el valor sin
   transformación en el QWORD inicial de su descriptor de registro.

Así, el descriptor AGC y `sceVideoOutRegisterBuffers2` sí apuntan a la
**misma asignación**: VideoOut recibe la dirección completa y el descriptor
hardware la codifica en unidades de 256 bytes. La reserva adicional de
`0x1f475fe`, guardada en `ResourceCandidate+0xe8`, alimenta otro slot según el
layout y no debe confundirse con la superficie principal. Falta nombrar con
certeza esos campos auxiliares y recuperar los demás DWORD necesarios para el
clear mínimo.

## Prueba en homebrew — fase 0

El probe `legacy/probes/ps5-agc-phase0` se ejecutó dos veces mediante
`hbldr -> FAKE00000`. Sólo solicitó el sysmodule interno AGC `0x80000094` y lo
descargó; no abrió VideoOut, no reservó memoria, no llamó exports AGC y no creó
ni envió command buffers. En ambas ejecuciones:

```text
LoadModuleInternal(AGC=0x80000094) rc=0x00000000
UnloadModuleInternal(AGC=0x80000094) rc=0x00000000
```

AGCDriver informó inicialización, pero el constructor de AGC emitió:

```text
[Agc] FS Table offset has shifted. This is not survivable.
```

La decompilación localiza el diagnóstico en `libSceAgc+0xdc28`. El constructor
obtiene `base` y `size` desde AGCDriver, alinea una dirección derivada y compara
el resultado con el valor ABI fijo `0xfe0040000`. El mensaje aparece cuando no
coinciden. En RE2 y San Andreas, las capturas sí contienen esa dirección dentro
del mapping RW `SceAgcDriver` (`0xfe003c000..0xfe0200000`).

La variante 0B mantuvo el módulo cargado 20 segundos para inspección read-only.
El ciclo terminó y `FAKE00000` se cerró limpiamente, pero ps5debug representa el
host como `SceCloudClientApp` y rechazó/listó cero mappings para ese proceso; el
ELF hijo no hereda un title ID seleccionable. No se repite este método.

### Fase 0C: causa exacta del desplazamiento FS

El probe acotado `ps5-agc-phase0c-driver-dmem.elf` cargó únicamente el
sysmodule `libSceAgcDriver` (`0x80000080`) dentro de `hbldr -> FAKE00000`,
resolvió por NID el mismo getter `Um-jkyDy9rI` que usa el constructor y no cargó
`libSceAgc`, VideoOut, contexto, cola ni comandos. Resultado en hardware:

```text
GetDmem rc=0x0000000000000000
base=0x0000000ff0040000
size=0x001b0000
```

La copia de firmware 12.02 de `libSceAgc` calcula la tabla así:

```c
driver_get_dmem(&base, &size);
fs_table = (base + 3) & ~3ULL;
fs_end = base + size;
memset(fs_table, 0, 0x60);
if (fs_table != 0xfe0040000)
    log("FS Table offset has shifted. This is not survivable.");
```

En `FAKE00000`, `fs_table=0xff0040000`: exactamente `0x100000000` (4 GiB)
por encima de la dirección ABI esperada. El mensaje es sólo diagnóstico y el
constructor continúa, lo que explica que la carga del sysmodule devolviera
cero; no convierte los exports posteriores en seguros. Esta evidencia descarta
un error de detección o un simple fallo de carga. El bloqueo concreto es el
layout DMEM asignado al tipo/contexto de proceso de `FAKE00000`.

El probe descargó AgcDriver con retorno cero. Su ELF terminó, el contenedor que
quedó activo fue identificado exactamente como `FAKE00000`, se cerró mediante
la ruta limpia allowlisted en 100 ms y los cuatro servicios permanecieron
sanos. No se debe avanzar a contexto/cola mientras no exista un host cuya base
sea `0xfe0040000` o evidencia estática de una API soportada que abstraiga este
desplazamiento; parchear la constante o llamar por offsets no es una solución
segura.

Conclusión: **cargar AGC está validado, inicializarlo para uso no**. Un retorno
cero del loader no invalida el diagnóstico interno “not survivable”. Quedan
bloqueados los probes de submit, fence y dibujo hasta determinar la disposición
DMEM/FS Table requerida o encontrar una ruta de host que reproduzca el mapping
de los juegos nativos.

### Corrección: layout completo reubicado, no modo reducido

El resultado de fase 0C contradice y reemplaza la interpretación anterior de
“modo reducido”. Aunque el log dice `submit.mode=1`, GetDmem devuelve
`size=0x1b0000`. Ese tamaño sólo corresponde a la entrada
`{offset=0x40000,size=0x1b0000}` del layout completo de 2 MiB. Por tanto el
campo que selecciona las tablas en `driver+0x4f0` no puede equipararse sin más
al texto `submit.mode` del log.

El getter `AgcDriver+0x9d0` calcula:

```c
base_out = driver_window_base + profile[5].offset;
size_out = profile[5].size;
```

La inicialización propone `driver_window_base=0xfe0000000` y solicita una
ventana total de `0x200000`. San Andreas confirma el resultado ideal mediante
sus mapas completos `0xfe0000000..0xfe0200000`, incluida la región principal
`0xfe003c000..0xfe0200000`. En `FAKE00000` la misma tabla completa termina
reubicada a `0xff0000000`, pues GetDmem entrega
`0xff0000000+0x40000,0x1b0000`.

Una captura anterior del proceso anfitrión `SceCloudClientApp` ya contenía una
reserva `SceAgcDriver` en `0xfe0000000..0xfe0010000` y memoria de compositor.
Esto encaja con `hbldr`: lanza una copia del eboot de Game Streaming
`NPXS40106`, espera hasta justo antes de su llamada a `main` y sólo entonces
reemplaza el programa por nuestro ELF. Para ese momento las dependencias y
constructores del anfitrión ya pudieron ocupar la dirección preferida. La
hipótesis de trabajo era que esa reserva heredada fuerza la reubicación 4 GiB
más arriba. Una prueba posterior descartó específicamente que la reserva nazca
en los constructores propios del eboot.

Se probó además una modificación reversible sólo en el `param.json` de
`FAKE00000`: `attribute 1->0` y `attribute3 4->0`, igualando los flags básicos
de San Andreas. GetDmem permaneció en `0xff0040000`; el JSON original se
restauró y verificó por SHA-256 antes de cerrar limpiamente el host. Esos flags
no seleccionan la ventana.

No se desmapeará ni reutilizará a la fuerza la reserva heredada: puede pertenecer
al compositor. La salida segura es reemplazar el proceso antes de que el host
inicialice esa memoria, usar una plantilla BigApp que no la ocupe, o resolver
el lanzamiento del eboot nativo aislado.
## Native BigApp phase-0 gate

A standalone title, `FAKE0AGC0`, is now built locally to distinguish host
policy from AGC-library behavior. Its eboot is a freestanding static `ET_EXEC`
wrapped as a fake-signed executable with the SDK `install_app` recipe. It loads
only `libSceSysmodule`, resolves the two internal sysmodule lifecycle exports,
loads/unloads AGC, writes a bounded result log, and exits. There is no VideoOut,
GPU allocation, queue creation, command buffer, PM4, or submit in this build.

The isolated registration helper builds cleanly with `-Werror`.
`sceAppInstUtilAppInstallAll` subsequently returned zero and registered the
title, but `sceSystemServiceLaunchApp` reproducibly returned `0x80940005`; no
process started. It must not be reinstalled, removed, or relaunched until the
firmware-12 appmeta/indexing contract is understood.

The decisive observation, once that launch is legitimately available, is
whether the native process preserves AgcDriver's preferred `0xfe0000000`
window and therefore returns GetDmem `0xfe0040000/0x1b0000`.
`submit.mode=1` is no longer a failure criterion by itself: phase 0C proved the
full-size layout can coexist with that log value.

## Resultado del reemplazo temprano

Se compiló la implementación moderna y ya validada de hbldr como un ELF
autónomo separado, deteniendo `NPXS40106` en `entry+0x2d`: después de tres
llamadas importadas iniciales, pero antes del dispatcher de constructores. Sólo
ejecutó fase 0C y no sustituyó el shsrv desplegado. GetDmem volvió a entregar
exactamente `0xff0040000/0x1b0000`.

Esto descarta que los constructores del eboot sean la causa del desplazamiento.
La política/reserva relevante existe antes: durante creación del proceso,
carga de dependencias o las tres llamadas importadas tempranas. El payload
terminó por sí mismo, no quedó BigApp y los cuatro servicios conservaron salud.
No se repetirán los offsets `0x2d` ni `0x3a`; el próximo trabajo seguro es
identificar esas importaciones y comparar dependencias del host con un juego
nativo, antes de considerar un breakpoint en `entry+0x00`.

La resolución posterior de PLT cerró esa rama: `entry+0x14` llama `_init_env`
(NID `bzQExy189ZI`) y `entry+0x1c` y `entry+0x28` llaman `atexit` (NID
`8G2LB+A3rzg`). Ninguna es una inicialización AGC. En cambio, el ELF declara
directamente `libSceAgcDriver.prx` y `libSceAgc.prx` entre sus 53 entradas
`DT_NEEDED`; el enlazador las procesa antes de transferir control a `e_entry`.
Por ello tampoco se justifica probar `entry+0x00`: ya sería demasiado tarde
para impedir la carga de esas dependencias.

Se compararon además los eboots firmados de Remote Play (`NPXS40074`), Share
Play (`NPXS40099`) y HRTF Personalization (`NPXS40250`). Los tres enlazan AGC y
AGCDriver, aunque HRTF sólo tiene 27 dependencias. Todos conservan exactamente
la misma forma de prólogo y los puntos `+0x2d`/`+0x3a`, por lo que HRTF es un
control estructural compatible pero no un host libre de AGC. Probarlo exige
autorización explícita para sustituir temporalmente el SELF de `FAKE00000`, con
backup server-side, comparación byte a byte y restauración obligatoria.
