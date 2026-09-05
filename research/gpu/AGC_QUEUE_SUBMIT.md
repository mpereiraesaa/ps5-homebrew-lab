# Cola gráfica y ABI de submit AGC

Alcance original: prueba estática del `libSceAgcDriver.sprx` de firmware 12.02
y su imagen runtime autorizada. Las fases numeradas conservan cronológicamente
qué se conocía en cada momento.

Estado vigente: Native Label v5 ya ejecutó desde `PPSA99998` un DCB propio con
`sceAgcInit`, BatchMap `0xcf2` y `SubmitDcb=0`; `DMA_DATA` cambió el target de
`0xa5a55a5a` a cero y el `RELEASE_MEM` posterior cambió la fence de uno a cero.
Por tanto, las frases “siguiente probe” de fases 0E–0W son decisiones históricas,
no pendientes actuales. La siguiente frontera global es VideoOut.

## Resultado byte a byte

`sceAgcDriverCreateQueue` (NID `zP4ZNlXLBVg`, `+0x2020`) sólo hace:

```asm
xor ecx, ecx
jmp +0x2030
```

Por tanto conserva los tres primeros argumentos de entrada y añade un cuarto
argumento interno igual a cero antes de saltar a la implementación extensa.
Esto prueba la forma del wrapper, no los tipos de esos tres argumentos.

`sceAgcDriverSubmitDcb` (NID `UglJIZjGssM`, `+0x2960`) hace:

```asm
mov rsi, rdi
lea rdi, [default_graphics_queue]
jmp +0x19b0
```

El export público recibe un único puntero al descriptor de submit; no recibe
un handle de cola. El wrapper selecciona internamente la cola gráfica global y
entra en `sceAgcDriverSubmitCommandBuffer` (`+0x19b0`).

El submit común copia del segundo argumento exactamente:

```c
struct AgcSubmitInfo12Candidate {
    const uint32_t *command_buffer; // +0x00
    uint32_t size_dwords;           // +0x08
    uint8_t field_0c;               // +0x0c
    uint8_t padding[3];
};
```

La forma coincide con el descriptor construido por el worker de San Andreas.
Los bytes completos de los dos wrappers y las tres cargas del descriptor son
idénticos entre el SPRX de sistema y el dump runtime.

## Implicación para el primer probe

No debemos inventar un handle ni pasarlo a `sceAgcDriverSubmitDcb`. Antes del
primer submit hay que encontrar y reproducir la inicialización que hace válida
la cola gráfica global del driver. `CreateQueue` podría pertenecer a otra clase
de cola o ser sólo una pieza de esa inicialización; su wrapper no demuestra por
sí solo que deba llamarse para graphics.

El primer submit sigue bloqueado hasta demostrar:

1. inicialización de la cola global y su contexto/owner;
2. acceso efectivo de esa cola al mapping privado;
3. mecanismo de completion con timeout y cleanup seguro;
4. vida del command buffer y de la etiqueta hasta completion.

## Verificación reproducible

Desde la raíz de `homebrew_ps5`:

```sh
python3 research/gpu/tools/verify_agc_queue_submit.py --json \
  --output research/gpu/captures/agc-queue-submit-proof.json
```

La salida mantiene `queue_initialized=false` y
`submitted_or_executed=false`: describe evidencia estática, no una prueba viva.

## Carga del módulo ya ejecuta el inicializador

El ELF de sistema cierra una ambigüedad importante. Su dynamic table declara
`DT_INIT=0x10`; el dispatcher en `+0x10` consulta el slot `+0x14108`. La
relocación de ese slot es `R_X86_64_RELATIVE` con addend `+0x8070`, y ese
trampoline salta directamente a `+0x7c20`, el inicializador completo descrito
abajo. Los bytes coinciden en la imagen runtime.

Por tanto, cargar AgcDriver mediante el loader ya intenta clasificación,
componentes, memoria interna y creación de las colas de la clase del proceso.
No existe un paso posterior legítimo en el que la aplicación deba llamar
`CreateQueue` por su cuenta. Un `dlopen` exitoso sólo demuestra que el módulo
quedó cargado: no prueba que el resultado interno de `+0x7c20` sea cero, porque
el contrato del loader no expone ese retorno como resultado de `dlopen`.

Esto afina el gate del homebrew: necesitamos observar de forma no invasiva el
estado que dejó el inicializador original, no diseñar otro inicializador ni
crear una cola duplicada.

## Probe 0E y límite observado

El primer intento de inspección read-only dentro de `FAKE00000` cargó
AgcDriver con retorno cero, pero terminó al derivar la base desde el resultado
de `dlsym`. La revisión con `dladdr` fue contenida y más informativa:
`dlopen` y la resolución de `SubmitDcb` sí funcionan, pero `dladdr` devuelve
cero en este runtime (`result=13`). En ambos intentos
`called_create_queue=no; submitted=no`; el segundo host fue cerrado y la salud
final se verificó dos veces.

No se debe repetir esa variante. La ruta siguiente es mantener nuestro propio
probe vivo tras cargar AgcDriver, localizar su mapping externamente mediante
la enumeración read-only de ps5debug y leer únicamente el rango del objeto
global. Esto evita depender de `dladdr` o de asumir que el puntero devuelto por
`dlsym` pertenece directamente al mapping del SPRX.

La fase 0F probó también esa alternativa. LNC identificó correctamente
`FAKE00000` y el probe registró carga de AgcDriver con retorno cero más el inicio
del hold, pero ps5debug no expuso un mapping ejecutable de AgcDriver bajo ninguno
de los procesos `eboot.bin` visibles. El supervisor abortó antes de cualquier
lectura de memoria, cerró el host identificado y confirmó dos veces la salud.
Como el cleanup ocurrió antes de terminar los 25 segundos, el log no prueba un
unload dentro del probe; sólo prueba cierre limpio del contenedor y servicios
sanos.

Las acciones 0E/0F se retiraron del CLI del supervisor para impedir reintentos
accidentales. El análisis de cola continúa únicamente sobre los dumps ya
autorizados hasta disponer de una identidad de proceso nueva y demostrable.

La fase 0G comprobó además si el resultado de `dlsym` podía aceptarse sólo tras
comparar el wrapper completo y dos firmas relativas. El NID se resolvió, pero
la primera lectura del supuesto código no produjo firma, fallo recuperable ni
línea final antes del timeout. No se alcanzó el cálculo de base ni la lectura
de la cola. El supervisor cerró limpiamente el `FAKE00000` identificado y
verificó dos veces los cuatro servicios. Esto demuestra que el valor resuelto
no es un puntero de código legible en este host; 0G también fue retirado del
build predeterminado y del CLI. No debe reintentarse.

## Estado contextual ya presente en los dumps

La comparación reproducible de los dumps runtime de `AgcCompositor.elf` y San
Andreas sí permite observar el objeto que selecciona `SubmitDcb`, en
`AgcDriver+0x228b8`, sin nueva actividad sobre la consola:

- ambos objetos comienzan con `size=0x38`;
- el campo `+0x38`, usado por el submit común como lock/context, es no nulo en
  ambos;
- el DWORD `+0x04` vale `3` en el compositor y `0` en el juego;
- otros campos cambian entre procesos, por lo que no es una plantilla constante
  que podamos copiar al homebrew.

Esto demuestra que el driver mantiene estado de cola inicializado y dependiente
del contexto. No demuestra todavía el nombre semántico del DWORD `+0x04`, ni
que el estado creado para `FAKE00000` sea válido para graphics.

```sh
python3 research/gpu/tools/compare_agc_queue_snapshots.py
```

La herramienta sólo informa presencia/ausencia de punteros y no persiste
direcciones runtime.

### Sentinel exacto de creación (`queue+0x48`)

La implementación interna de `CreateQueue` ya está anclada byte a byte. Para
las colas simples selecciona el objeto global, publica `size=0x38`, índice,
token y `aux+0x40`; después consulta un solo byte en `+0x48`. Si ese byte es
distinto de cero omite la creación del mutex. Si era cero, inicializa el
contexto en `+0x38` y finalmente escribe exactamente `1` en `+0x48`.

Los dumps autorizados de AgcCompositor y San Andreas contienen ambos
`queue[0x48] == 1`, además de lock y token no nulos. Esto es evidencia runtime
de que sus colas respectivas completaron esa fase de creación. La captura
reproducible queda en `captures/agc-queue-snapshot-comparison.json`.

La fase 0K observó la cola de `FAKE00000` sin llamar `CreateQueue` ni submit:
tras exigir la geometría exacta de 0J leyó sólo 25 bytes del cuarto segmento.
Obtuvo `size=0x38`, tipo 0, token y lock no nulos, y sentinel `+0x48 == 1`.
Eso prueba la creación estructural del objeto y su mutex, pero **no** que la
cola esté configurada o habilitada para consumir trabajo GPU. La conclusión
anterior `hardware_queue_initialized=true` queda retirada tras 0S. El campo
`queue_initialized=false` del verificador estático se conserva deliberadamente:
ese artefacto no ejecuta hardware y no debe fingir evidencia runtime. La captura
es `captures/agc-phase0k-queue-metadata.json`.

El postmortem de 0S muestra por qué esa distinción importa. En `FAKE00000`,
`queue+0x08=0x20000`, exactamente el fallback que `CreateQueue+0x2385` escribe
cuando recibe configuración nula. San Andreas tiene `queue+0x08=0` y
`queue+0x0c=1`. El backend class-0 enmascara `queue+0x08` con `0x20000` y
desplaza ese bit 17 posiciones antes de incorporarlo al registro traducido;
por tanto los dos submits no son equivalentes aunque compartan clase e índice.
0S también dejó `driver_state+0x1cc=1`, demostrando que alcanzó el registro
lazy, pero no ejecutó el primer packet. Su inventario contiene AgcDriver pero
no `libSceAgc`; 0T comprobará de forma load-only si el constructor de esa capa
modifica la configuración. Evidencia reproducible:
`captures/agc-phase0s-queue-context-proof.json`.

La fase 0I probó una derivación de base legítima mediante la lista e información
de módulos del propio proceso. Encontró un único AgcDriver entre ocho módulos y
demostró que `base+0x228b8..+0x228ff` cae dentro de un segmento legible. El gate
de permisos del segmento de código no aceptó la codificación raw observada y el
probe abortó antes de leer wrapper o cola. Descargó el módulo, cerró el host y
mantuvo sanos los servicios. 0I fue retirado sin relajar el gate ni repetirlo.
El siguiente paso es inventariar sólo geometría relativa y protecciones raw en
una fase 0J; todavía se conserva `queue_initialized=false`.

0J obtuvo esa geometría sin leer código ni datos del módulo: segmentos
`0/0xc000/prot4`, `0xc000/0x8000/prot1`, `0x14000/0x4000/prot1` y
`0x18000/0xc000/prot3`. Coincide exactamente con los cuatro mappings de los
dumps nativos. El valor raw `4` explica por qué no se debe hacer `memcmp` del
wrapper desde este proceso; el segmento de la cola sí es el cuarto, raw `3`, y
contiene completamente `+0x228b8..+0x228ff`. 0J se retiró tras cleanup sano.
0K aplicó ese gate y cerró limpiamente la incógnita de creación de la cola. No
prueba acceso efectivo de GPU a memoria directa propia, coherencia ni submit.
El siguiente gate debe validar el ciclo de mapping y visibilidad CPU/GPU antes
del primer stream DMA_DATA+RELEASE_MEM de cuatro bytes con timeout acotado.

0L cerró la mitad CPU/lifecycle de ese gate. Con la cola validada viva,
`FAKE00000` pudo reservar y mapear 128 KiB (`type=3`, `prot=0x33`), alojar sin
solapamiento el stream exacto de 60 bytes, target con canary y fence inicial 1,
y ejecutar `munmap`, `ReleaseDirectMemory` y unload con retorno cero. No llamó
ningún export AGC ni submit. Esto prueba coexistencia y cleanup, no visibilidad
GPU: el siguiente escalón es necesariamente el primer submit acotado y sólo se
considerará éxito si target y fence cambian a cero antes del deadline.

### El unload no es un drain y SDMA blocking es un stub

La cadena de finalización también quedó anclada. `DT_FINI=0xb940` despacha al
callback normal `+0x8080`, cuyos bytes completos son `31 c0 c3`: sólo devuelve
cero. No espera la GPU ni drena la cola. En consecuencia, un timeout no puede
resolverse liberando memoria y confiando en `UnloadModuleInternal`; eso dejaría
sin demostrar si el backend aún referencia el mapping.

Se auditó además `sceAgcDriverSdmaCopyLinearBlocking` para buscar un primer test
de visibilidad más contenido. En firmware 12.02 el export NID
`bQ+En9GY3PM`, `+0x7ab0`, sólo registra la ruta no soportada y devuelve
constantemente `0x8a6d0001`. Sus 39 bytes coinciden entre ELF y dump runtime.
No ofrece una alternativa al submit graphics.

El export `sceAgcDriverWaitUntilSafeForRendering` tampoco es una espera CPU.
Su cuerpo completo de `0x1c3` bytes (NID `u8BkdHb1+Po`, `+0x7450`) coincide
entre sistema y runtime y modifica el cursor de un command writer para emitir
`WAIT_REG_MEM`/`WAIT_REG_MEM64`. Sólo ordena trabajo futuro dentro del command
buffer; no puede drenar una cola tras un timeout. El verificador fija su SHA-256
y los stores de cursor/header para impedir deducir seguridad sólo de su nombre.

## `SetupAsyncGraphics` no equivale a crear la cola graphics

El export `sceAgcDriverSetupAsyncGraphics` (NID `Vlaj1gwmIFA`, `+0x3f30`) quedó
verificado en las dos imágenes completas. Recibe un único entero público:

1. consulta el nibble bajo del estado global `+0x1c8`;
2. si aún es cero, llama al backend con el handle interno y modo literal `1`;
3. tras éxito publica el nibble como `1`;
4. guarda `argument != 0` en el campo global `+0x1c0`, que las demás rutas usan
   para seleccionar la variante AGR/interrupt;
5. devuelve cero o `0x8a6d0005` si el backend no confirma éxito.

Esto es configuración de la ruta async/AGR sobre un driver inicializado. No
prueba creación del objeto global de graphics y no debe invocarse como sustituto
de inicialización. El próximo probe tampoco debe llamar este export hasta
resolver el contexto de proceso y el significado del modo.

## Fase 0T: el constructor de AGC no configura la cola

El probe 0T cargó `libSceAgc.sprx` dentro de `FAKE00000` y tomó el mismo
snapshot acotado de la cola antes y después. Los once campos fueron idénticos:
`queue+0x08=0x20000`, `queue+0x0c=0`, contadores cero, sentinel uno y registro
cero. Por tanto, el constructor de módulo y su inicialización de FS Table no
son quienes llevan la cola al estado visto en San Andreas.

El import usado por el diagnóstico `FS Table offset has shifted` quedó resuelto
por NID contra el catálogo del SDK: `YQ0navp+YIc == puts`. La rama continúa en
`libSceAgc+0xdc34`; no es un `abort`. La descarga posterior no produjo el log
final y el watchdog terminó el host, que luego ya no aparecía como BigApp; los
cuatro servicios siguieron sanos. No se hizo mapping, llamada de cola, submit ni
VideoOut. 0T queda retirado y no debe repetirse.

La búsqueda de escritores directos identifica ahora la transición exacta. El
export de AgcDriver NID `oFb2hMcoJa4`, `+0x3fd0`, serializa ambas colas y pone o
quita el bit `0x20000` de `queue+0x08` según su único argumento. `libSceAgc`
lo importa y sólo lo llama desde su inicializador interno `+0x8a20`; los exports
`+0x9930` y `+0x9990` terminan en ese inicializador. En el callsite autorizado
de San Andreas se llama `+0x9990` con versión `8`; la rama `version >= 6`
invoca el setter con cero, que explica exactamente `queue+0x08=0` en el juego.
Esto vincula el bit faltante al bootstrap de contexto AGC, no al mero `dlopen`.

### Fase 0U: transición confirmada y siguiente fallo exacto

0U llamó una vez el export `23LRUSvYu1M` (`libSceAgc+0x9990`) con versión 8,
replicando el callsite autorizado de San Andreas. El resultado de hardware fue:

```text
before-bootstrap flags_08=0x20000
context bootstrap rc=0x8a6c002f context_word=0
after-bootstrap  flags_08=0x0
```

Los demás campos observados quedaron iguales. Esto confirma causalmente la
transición de cola. También confirma que la inicialización completa falla: el
código `0x8a6c002f` se genera en `libSceAgc+0x80a0/+0x80d0` cuando el puntero
global de FS Table no es exactamente `0xfe0040000`. Es la comprobación
ejecutable del mismo problema que anticipaba el diagnóstico del constructor.
El bit cero aislado no autoriza un nuevo submit.

El probe no reservó ni mapeó memoria, no emitió comandos y no llamó SubmitDcb o
VideoOut. `FAKE00000` se cerró por la API limpia, la salida fue verificada en
100 ms y los cuatro servicios conservaron salud estable. 0U queda retirado.

La captura de mapas de 0S muestra que en este host sólo
`0xfe0000000..0xfe0010000` está ocupado en la ventana preferida, mientras
`0xfe0040000` no aparece mapeado. El próximo gate útil es comprobar una reserva
no destructiva y exacta de una página en `0xfe0040000`; sólo si el kernel
devuelve la misma VA se podrá evaluar una tabla FS propia y revertible dentro
de nuestro proceso. No se sobrescribirá ningún mapping existente.

### Fase 0V: la VA fija está disponible

El gate de hardware devolvió `rc=0`, preservó exactamente `0xfe0040000` para
una reserva de `0x4000` bytes y la liberó con `munmap rc=0`. No cargó AGC, no
asignó memoria física y no hizo submit. El host se cerró limpiamente en 100 ms
y todos los servicios quedaron sanos.

Esto elimina la colisión virtual como obstáculo inmediato. El siguiente probe
puede crear allí una página propia, verificarla, cambiar exclusivamente el
puntero RW `libSceAgc+0x45f90` desde la tabla reubicada a esa página y repetir
el bootstrap v8. Debe conservar el mapping hasta terminar el proceso, porque el
bootstrap publica punteros dentro de la tabla; no se permitirá ningún submit en
ese experimento.

### Fase 0W: el mapping directo fijo aún no está resuelto

El primer 0W reservó exactamente `0xfe0040000` y asignó 16 KiB físicos type
`0x0c`, ambos con retorno cero. `sceKernelMapDirectMemory` rechazó la operación
con `0x80020016`; el probe terminó antes de cargar AGC, modificar
`libSceAgc+0x45f90` o llamar bootstrap. `submitted=no`, cierre exacto en 100 ms
y servicios estables.

Una segunda revisión cambió únicamente la granularidad reserve/allocate/map a
64 KiB, conservando la copia lógica en 16 KiB. `FAKE00000` apareció, pero no se
observó un log nuevo ni entrada a `main`; por tanto no proporciona evidencia
sobre `MapDirectMemory`. Como el ELF auditado no contiene submit, se cerró
exactamente el host y los cuatro servicios permanecieron sanos. No se hará un
tercer intento sin aislar primero, en un probe mapping-only, si la combinación
VA fija + `MapDirectMemory` o el mecanismo de lanzamiento explica el fallo.

## Inicializador real y clasificación del proceso

El inicializador interno `AgcDriver+0x7c20` quedó localizado mediante las
cadenas `Cannot initialize internal components`, `Cannot initialize internal
memory` e `Initialized, submit.mode`. Su cuerpo completo también coincide entre
el SPRX y el runtime autorizado.

Antes de crear colas obtiene una clasificación empaquetada del proceso, guarda
sus mitades de 16 bits en el estado global e inicializa componentes y memoria.
Las ramas posteriores contienen llamadas directas verificadas al wrapper
`CreateQueue+0x2020`:

```text
process_class == 0: CreateQueue(0, &local0, 0)
                    CreateQueue(4, &local1, 0)

process_class == 1: CreateQueue(3, &local0, 0)
```

Después, la clase 0 inicializa además las entradas de cola `0x20..0x57` y ambas
rutas continúan con memoria interna, backend y workloads. La correlación con
los snapshots es exacta: San Andreas expone índice `0` en el objeto que usa
`SubmitDcb`; `AgcCompositor` expone índice `3`.

Conclusión: la cola graphics global es propiedad del ciclo de inicialización
del driver y depende de la clase de proceso. No debemos copiar su objeto ni
llamar `CreateQueue` una segunda vez; el mensaje interno `Queue %d already
created` refuerza esa restricción. Para homebrew, el gate real pasa a ser
demostrar qué clase recibe el host y si el inicializador completo termina en
modo compatible, no inventar una estructura de cola.

### Origen de la clasificación

El helper `AgcDriver+0x8090` que alimenta esa rama no lee directamente metadata
del título. La secuencia verificada es:

```text
open("/dev/gc", 2)
ioctl(fd, 0xc004812e, &packed_mode)
```

Devuelve el descriptor al estado global y el DWORD del ioctl al inicializador,
que separa sus dos mitades de 16 bits. Si la mitad baja y otro estado global
son cero, el helper intenta además un mapping fijo de `0x4000` bytes en
`0xfe0200000` con protección `0x22` antes de continuar.

Esto reduce el problema del host: los atributos del paquete pueden influir en
lo que `/dev/gc` devuelve, pero no sustituyen el contrato kernel/driver. La
diferencia de DMEM de 4 GiB observada en `FAKE00000` es coherente con una clase
o layout distinto, aunque todavía no prueba por sí sola qué valor devolvió ese
ioctl. No se debe llamar el ioctl ni reproducir el mapping fijo manualmente; la
ruta correcta es conseguir un contexto de proceso que haga completar al
inicializador original.

La correlación runtime queda cerrada por el estado global que escribe ese
helper. En `AgcDriver+0x22910`:

| Proceso | clase baja del ioctl | `queue+0x04` |
|---|---:|---:|
| `AgcCompositor` | 1 | 3 |
| San Andreas | 0 | 0 |

En ambos dumps el handle de `/dev/gc` también es no nulo. Por tanto, para estas
dos muestras está demostrada la cadena completa
`ioctl → rama del inicializador → índice CreateQueue → objeto elegido por
SubmitDcb`. No es sólo una correlación por nombre del proceso.

### Exports de owner no disponibles

Los nombres públicos sugerían una posible consulta encapsulada, pero los bytes
de firmware 12.02 la descartan. Estos cuatro exports userland son stubs idénticos
`mov eax,0x8a6c9018; ret`:

- `sceAgcDriverRegisterOwner` (`+0x6b00`);
- `sceAgcDriverRegisterDefaultOwner` (`+0x6b70`);
- `sceAgcDriverGetDefaultOwner` (`+0x6b80`);
- `sceAgcDriverGetOwnerName` (`+0x6c60`).

No existe, por tanto, un probe read-only útil basado en esos exports para
consultar la clase del host. Ejecutarlos sólo devolvería el error constante y
no aportaría evidencia nueva.

## Fase 0H: clase cero mediante un getter público

La tabla pública 3.20 correlaciona el NID `CP-kVAMmWVw` con
`sceAgcDriverGetRegShadowInfo`; los bytes de nuestro firmware 12.02 en
`AgcDriver+0x3430` cierran su comportamiento exacto:

1. rechaza un output nulo con `0x8a6d0003`;
2. comprueba el DWORD `driver_state+0x08`, ya identificado como la clase baja
   devuelta por `/dev/gc`;
3. si es distinto de cero devuelve `0x8a6d0001`;
4. si es cero copia exactamente 40 bytes desde el bloque de register-shadow al
   buffer del caller y devuelve cero.

No contiene ioctl, llamadas de queue ni submit. La única ejecución contenida
en `FAKE00000` devolvió cero y los cinco QWORD copiados fueron no nulos. Esto
demuestra que el host sí recibe clase 0 y que la inicialización del bloque de
register-shadow progresó. AgcDriver cargó y descargó con retorno cero;
`FAKE00000` fue cerrado limpiamente en 100 ms y los cuatro servicios quedaron
sanos.

La acción 0H se retiró del supervisor después de responder esa pregunta. El
resultado no permite promover `queue_initialized`: el getter no inspecciona
el objeto de cola ni demuestra acceso GPU a memoria privada. Sí elimina la
clasificación incorrecta del proceso como explicación del bloqueo; el problema
restante se concentra en la ventana DMEM reubicada y en comprobar la cola por
una interfaz soportada.

## Fase 0P: selección real del backend de clase 0

Una lectura acotada de 16 bytes confirmó en `FAKE00000` clase de proceso 0,
selector 0 y callback igual a `AgcDriver+0x1100`. El nombre `ready` usado en el
log de la sonda era provisional; el análisis completo confirma que es el mismo
DWORD de clase observado en 0H. En `+0x1100`, clase 1 usa una ruta rápida que
codifica directamente VA y conteo. Las demás clases saltan a `+0x1450`; no es
una salida de error.

La función clase 0 ocupa `0x4cd` bytes y coincide entre sistema y runtime con
SHA-256 `10068a320dc9dc667f897197a66732d2c04d0f901d110f0cf7fc83a2fed3603c`.
Traduce los dos registros internos preparados por el submit común y termina
llamando al helper driver `+0xad80`. No copia el contenido DWORD del command
buffer antes de esa llamada. Falta cerrar qué garantiza el kernel respecto a
pinning/copia y finalización; por ello no se autoriza todavía la fase 0M. La
0P se descargó y cerró limpiamente y quedó retirada tras su única ejecución.

El helper final `+0xad80` también coincide en ambas copias (116 bytes, SHA-256
`9a21be82c69e7a7020cfbf6f77e429f0896a4d47ba585fd320ecf96c75c6cefb`).
Construye un argumento de 24 bytes con tipo/cola, dos veces el número de
registros, puntero a los registros traducidos y un estado de salida inicializado
a uno; después ejecuta ioctl `0xc0188132` sobre `/dev/gc`. Devuelve éxito sólo
si el ioctl retorna cero y el estado bajo vuelve en cero. Ese contrato prueba
aceptación del submit, no ejecución ni finalización GPU. Tampoco demuestra que
el kernel copie los DWORD del command buffer o mantenga fijado su mapping. El
único permiso de cleanup continúa siendo observar el fence final esperado.

La inicialización del registro clase 0 es perezosa y forma parte del propio
primer submit. Si el contador por cola está a cero, `+0x1450` llama al builder
`+0x5480`, que emite tres DWORD comenzando por `0xc0012800`, y entrega el
registro resultante al helper `+0xac60`. Este último copia 56 bytes del registro
primario, permite superponer 16 bytes opcionales y ejecuta ioctl
`0xc0488131` con un argumento de 72 bytes. Sólo después de aceptar ese registro
se incrementa el contador y se continúa al ioctl de enqueue `0xc0188132`.

Por tanto, una aplicación clase 0 no debe llamar ni reproducir manualmente ese
registro privado: el driver lo realiza automáticamente. Esto cierra la
existencia del paso de registro de submit, pero no demuestra que cualquier VA
privada sea GPU-visible ni reemplaza el fence de finalización.
