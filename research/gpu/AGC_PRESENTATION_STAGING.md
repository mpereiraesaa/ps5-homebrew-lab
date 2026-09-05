# Escalones mínimos de presentación AGC

> Registro histórico de la progresión A–E. Stage E ya fue completado; para el
> estado vigente consulte `STAGE_E_TRIANGLE.md` y `../../docs/ROADMAP.md`.

Alcance: firmware 12.02. Este plan no autoriza deployment ni ejecución
desatendida. Separa visibilidad de memoria, flip in-stream y escritura del
backbuffer para que un resultado negativo tenga una sola interpretación.

## A. Label privado — completado por Native Label v5

Stream: `DMA_DATA` inmediato de cuatro bytes a memoria privada seguido por
`RELEASE_MEM` de ownership. No abre VideoOut ni toca una superficie visible.

Éxito único: `target 0xa5a55a5a -> 0` y `fence 1 -> 0`. Cualquier retorno de
submit sin ambos cambios, timeout o log ambiguo conserva proceso, módulo y
mapping; no se cierra `PPSA99998` automáticamente.

Native Label v5 probó fetch del command buffer, acceso GPU al mapping propio
`type=0x0c`/BatchMap `0x0cf2` y completion observable. No probó presentación.

El gate previo 0Q demostró que el kernel acepta memoria física propia
`type=0x0c` con la política nativa BatchMap `0x0cf2`, incluidos canarios CPU y
cleanup completo. Por sí solo no demostraba visibilidad GPU; v5 la confirmó
mediante el cambio ordenado `target -> fence`.

`stage_a_batch_mapping.c` es la máquina de estados
object-only que modela una única asignación física propia `type=0x0c` mapeada
con la política nativa de command buffers BatchMap `0x0cf2`. Exige
`processed==1` tanto al mapear como al desmapear y conserva todos los recursos
ante resultados ambiguos. No tiene `main`, imports directos, AGC ni submit; su
aceptación por el kernel fue demostrada por 0Q con el operador presente. Ese
payload completó map, canarios, unmap y releases sin cargar AGC ni hacer submit.
Native Label v5 reutilizó este lifecycle bajo presencia explícita del operador
y un SHA exacto auditado.

## B. Flip AGC de un buffer rellenado por CPU

Sólo después de A:

1. abrir VideoOut y registrar dos buffers con el contrato ya validado;
2. rellenar ambos con un color sólido desde CPU;
3. crear un DCB en mapping propio;
4. llamar al builder privado `cwbxjPSJ7WQ` con `mode=0`, handle exacto, índice
   0 y un `flip_arg` monotónico;
5. adjuntar después un fence genérico de ownership;
6. someter exactamente ese mismo stream;
7. exigir fence GPU y luego completion/evento VideoOut del `flip_arg` exacto.

Este escalón no necesita shader, render-target descriptor ni DMA de 32 MiB.
Prueba que una cola propia puede ejecutar SetFlip y que VideoOut consume el
buffer registrado. Como el builder llama a `sceVideoOutSubmitEopFlip` antes de
emitir el packet, build y submit son una sola transacción: no existe variante
build-only con handle vivo.

Ante error posterior a la llamada del builder se conservan command mapping,
buffers, labels, equeue, handle, módulo y host. No se desregistra, cierra ni
reutiliza nada automáticamente.

El contrato de superficie está materializado en `stage_b_surface.c` como un
planner puro, compilado para PS5 sólo como objeto relocatable y probado también
en host. Para salida 4K fija `3840×2160`, pitch lógico `3840×2176`, huella tiled
`0x02000000`, dos slots separados `0x04000000` dentro de una reserva de
`0x08000000`, alineación `0x20000`, tipo directo `3`, protección `0x33`, formato
`0x8000000022000000`, índices de registro `0..1`, flip mode `1` y flip rate `0`.
En 1080p la huella queda en `0x00880000`. El planner rechaza cualquier layout
que invada el siguiente slot o exceda la reserva. El planner continúa siendo
un componente puro, pero ya está enlazado dentro del ELF Stage B auditado.

## C. Fill GPU privado grande

Sólo después de A y antes de tocar VideoOut con CPDMA, ampliar el mismo
`DMA_DATA src_sel=data` a un mapping privado guardado. El primer tamaño debe ser
pequeño y crecer por escalones; `0x02000000` es el máximo necesario para el
backbuffer 4K conocido, no el primer tamaño de prueba.

Cada escalón exige canarios fuera del rango, contenido esperado dentro del
rango y fence cero. Fallo o timeout conserva recursos.

## D. Clear sólido visible

Sólo después de A, B y C:

```text
DMA_DATA(fill backbuffer no activo)
sceAgcDcbSetFlip(mismo índice)
RELEASE_MEM(fence de ownership posterior)
SubmitDcb
esperar fence GPU
esperar completion VideoOut del flip_arg exacto
```

Se usa el builder oficial del driver para conservar su combinación PS5
específica `CS_DONE/shader_done + GL2 writeback`; no se sintetiza una barrera
PAL alternativa. El otro backbuffer permanece como recuperación visual y no se
modifica en esa submission.

## E. Triángulo

El triángulo empieza únicamente cuando D produce un color sólido repetible y
el segundo buffer puede alternarse sin corrupción. Añade descriptor de render
target, viewport/scissor, shaders, bindings y draw, pero conserva exactamente
el mismo protocolo de ownership y presentación validado en D.

## Estado actual

Actualización 2026-09-04: `PPSA99998` ya ejecutó `sceAgcCreateShader` para la
pareja pre-raster/pixel seleccionada y `sceAgcLinkShaders` con `primitive=6`
primero en almacenamiento estático y después dentro de un arena de memoria
directa. CX y UC coincidieron exactamente con el oráculo host; el arena se
limpió, desmapeó y liberó. Esto elimina la incertidumbre de construcción y
residencia CPU de shaders, pero no prueba fetch GPU: no hubo cola, DCB ni
submit.

El primer submit desde el título nativo usó `MapDirectMemory(type=0x0c,
prot=0x33)` y devolvió cero, pero ni target ni fence cambiaron. Native Label v2
cambió exclusivamente el ciclo del command buffer a la política observada en
el command pool comercial: `ReserveVirtualRange`,
`AllocateMainDirectMemory(type=0x0c)` y `BatchMap(protection=0xf2,
memoryType=0x0c)`. En hardware, reserve, allocate y BatchMap devolvieron cero,
`processed=1`, y `SubmitDcb` volvió a devolver cero; el fence permaneció en uno
durante el deadline de dos segundos. El proceso, módulo y mappings quedaron
retenidos conforme al guard. Evidencia:
`captures/agc-native-label-v2-runtime.json`.

Esto descarta la política `MapDirectMemory(0x33)` como explicación suficiente
del fallo anterior. A continúa sin demostrarse y el mismo stream no debe
repetirse con otra variante de mapping. El próximo frente es reproducir o
validar el bootstrap soportado que hace consumible la cola en las aplicaciones
nativas funcionales, manteniendo cualquier nuevo experimento sin submit hasta
probar primero su transición de estado.

Native Label v3 añadió exactamente el bootstrap público usado por ProsperoTV:
carga de `libSceAgc` y `sceAgcInit(&state, 8)` antes del mismo BatchMap y el
mismo stream. Carga, init, mapping y submit devolvieron cero. Esta vez el fence
sí cambió a cero antes del deadline, mientras el target no coincidió con cero.
Esto demuestra ejecución observable de `RELEASE_MEM` y que el bootstrap era
necesario para que la cola consumiera trabajo; todavía no satisface A porque el
efecto de `DMA_DATA` no fue observado. El guard retuvo todos los recursos.
Evidencia: `captures/agc-native-label-v3-runtime.json`.

La siguiente única variable será la publicación explícita de las líneas de
caché antes del submit: la ruta funcional de ProsperoTV ejecuta `clflush` por
cada línea de 64 bytes y luego `mfence` sobre su arena GPU. v3 sólo usaba una
barrera atómica, que no sustituye esa operación de caché. No se añadirá
VideoOut, shader, draw ni un packet distinto.

Native Label v4 aplicó ese `clflush` sobre los 128 KiB completos y `mfence`
antes del submit; el verificador confirmó también las instrucciones y su orden
en el código máquina. El resultado fue idéntico y ahora cuantificado: fence
cero y target exactamente `0xa5a55a5a`, sin cambio alguno. Por tanto, la
publicación de caché CPU queda descartada como causa suficiente. Evidencia:
`captures/agc-native-label-v4-runtime.json`.

La comparación estática posterior comprobó que el template seguro observado
del builder oficial `sceAgcDcbDmaData` coincide DWORD por DWORD con los siete
DWORD del probe, así que sustituir el builder no habría cambiado el stream.

Native Label v5 cambió una sola propiedad: separó target (`+0x1000`) y fence
(`+0x1100`) en líneas de caché distintas, conservando init, BatchMap `f2/0c`,
`clflush`+`mfence` y el stream de 15 DWORD. En hardware, `SubmitDcb=0`; la GPU
cambió el target de `0xa5a55a5a` a cero y después la fence de uno a cero. El
arena fue limpiado, BatchMap deshecho (`processed=1`), memoria directa y virtual
liberadas y AGC descargado, todos con retorno cero; el supervisor cerró la app y
confirmó saludables los cuatro servicios. Esto completa A y demuestra una ruta
AGC mínima, nativa, acelerada y observable sin VideoOut, shaders, draw ni acceso
a procesos comerciales. Evidencia:
`captures/agc-native-label-v5-runtime.json`.

- A: completado por Native Label v5. El bootstrap `sceAgcInit`, BatchMap real,
  publicación de caché y separación de target/fence produjeron la transición
  GPU ordenada `target a5a55a5a -> 0; fence 1 -> 0`, seguida de cleanup total.
- B: el probe completo fue ejecutado una vez en hardware como `PPSA99998`.
  Registró dos buffers, escribió por CPU sólo el seleccionado, obtuvo
  `SetFlip/build/SubmitDcb=0` y la GPU llevó la fence de uno a cero. No llegó a
  confirmar el evento VideoOut del `flip_arg` exacto: la telemetría v1 no
  distingue timeout de evento inválido. El proceso y todos sus recursos quedaron
  retenidos deliberadamente; no hubo cleanup ni cierre. Evidencia:
  `captures/agc-stage-b-v1-runtime.json`.
  El guard de cleanup ya está integrado en el supervisor:
  sólo fence GPU, un evento VideoOut y exit normal permiten liberar recursos.
  El compositor reutilizable `stage_b_compose.c` ya está compuesto, probado en
  host y compila como objeto con el toolchain PS5. Marca la transacción antes de
  invocar SetFlip, valida por direcciones enteras un cursor incluso arbitrario
  o fuera de rango y anexa el fence exacto; no contiene submit ni llamadas
  VideoOut. El planner de superficie `stage_b_surface.c` fija y valida el layout
  4K/1080p, y también compila como objeto PS5. El probe PS5 completo fue
  construido, auditado y ejecutado. `stage_b_transaction.c` une de forma reusable
  `fence=1 → SetFlip → RELEASE_MEM → Submit`, exige superficie registrada,
  buffer prerrellenado y evento armado, rechaza solapamiento fence/command
  buffer y marca retención antes de SetFlip y Submit. Está probado sólo con
  callbacks simulados y compila como tercer objeto relocatable no ejecutable.
  La identificación exacta del evento ya no es una suposición: en firmware
  12.02, `sceVideoOutGetEventData` (`rWUTcKdkUzQ`, `libSceVideoOut+0x128f0`)
  valida el filtro `0xfff3`, exige el identificador interno Flip `6` y devuelve
  el `flip_arg` firmado de 48 bits de `kevent.data >> 16`. Sus 81 bytes son
  idénticos entre el módulo de sistema y la captura runtime. La ruta se integró
  en un homebrew real, pero esta primera ejecución no demostró una decodificación
  exitosa del evento.
  `stage_b_event_adapter.c` compone esa llamada real con
  `sceKernelWaitEqueue`, decodifica como máximo un evento por poll y alimenta
  el fence/flip classifier. Un error de decodificación o conteo contradictorio
  aparca la transacción conservando recursos; un wait sin evento sólo continúa
  hasta el deadline absoluto del caller, sin adivinar códigos `errno`. El
  adaptador pasa pruebas con mocks. Sus símbolos runtime ya quedan resueltos en
  el ELF Stage B junto con superficie, transacción y completion. El fSELF v1
  ejecutado tuvo SHA-256
  `95cbb5db5f2981c469b454db716fe4b617e5ab7fe54ab3a427d6d987922137bd`.
  El fSELF v2 instrumentado y auditado tiene SHA-256
  `98afbf828f5519b4d13edcf358808c90c0559d56b54841cdb78c0c2e6bdfe49e`;
  el supervisor dispone de una única acción con operador presente. Antes de
  repetir, el siguiente build debe registrar por intento el retorno y `out` de
  `sceKernelWaitEqueue`, el retorno de `sceVideoOutGetEventData` y el valor
  decodificado, manteniendo la misma política de retención.
  Stage B v2 aportó ese diagnóstico: el primer wait devolvió `rc=0`, `out=1`,
  `GetEventData=0` y `0x0000420000000001`. El marcador enviado,
  `0x5354420000000001`, excedía el dominio firmado de 48 bits y el resultado
  fue exactamente sus 48 bits bajos. Esto confirma que el evento sí llegó y
  que el fallo era de nuestro comparador, no un timeout de presentación.
  Evidencia: `captures/agc-stage-b-v2-runtime.json`.
  Stage B v3 conserva el mismo stream y usa un marcador positivo válido de
  48 bits. Su fSELF auditado tiene SHA-256
  `341f166a0c6b4f29dd421cef8440adef5c531b28c31e3e8304619856523a704c`.
  En hardware, v3 confirmó fence y evento exacto en orden. El teardown se
  detuvo porque `UnregisterBuffers` devolvió `0x80290009` para el set que seguía
  en scanout. La referencia pública ProsperoTV trata sólo ese código como
  diferido hasta `VideoOutClose`, que ocurre antes de desmontar el framebuffer.
  Evidencia: `captures/agc-stage-b-v3-runtime.json`.
  Stage B v4 implementa esa secuencia con fSELF SHA-256
  `64d9512ae5ab4d722fa9ee6394413d127ea2b38330c694839abc1c5216549571`.
- C: completado en hardware con progresión 256 B, 4 KiB y 64 KiB sobre
  memoria privada separada; target completo, canarios, exterior, fence y
  cleanup verificados en cada escalón. Evidencia:
  `captures/agc-stage-c-progression.json`.
- D: completado en hardware. Un DCB de 79 DWORD ejecutó `DMA_DATA` sobre los
  `0x00880000` bytes del backbuffer 1, `SetFlip` y `RELEASE_MEM`. Se verificaron
  target completo, guardas de 64 bytes, buffer 0 intacto, fence, evento exacto,
  cinco segundos visibles y cleanup. El operador confirmó el frame verde.
  Evidencia: `captures/agc-stage-d-runtime.json`.
- E: completado. El pipeline propio `gfx1013` presentó un triángulo verde
  centrado sobre morado; 122 DWORD, 285.120 píxeles, fence, evento, guardas y
  cleanup verificados. Evidencia canónica:
  `captures/agc-stage-e-centered-triangle-runtime.json`.
