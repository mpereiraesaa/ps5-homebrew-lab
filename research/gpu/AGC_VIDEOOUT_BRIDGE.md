# Puente mínimo entre AGC y VideoOut

Alcance: planificación estática para firmware 12.02. Ninguna conclusión de
este documento autoriza submit sobre una superficie viva.

## VideoOut ya comprobado en homebrew

El probe nativo existente validó en hardware:

- dos buffers;
- `sceVideoOutSetBufferAttribute2` con
  `format_word=0x8000000022000000`;
- dimensiones 1920×1080 o 3840×2160 según la salida;
- direcciones separadas dentro de Main Direct Memory;
- `sceVideoOutRegisterBuffers2(handle, 0, 0, buffers, 2, &attr, 0, NULL)`;
- flip events, `sceVideoOutSetFlipRate(handle, 0)` y
  `sceVideoOutSubmitFlip`.

El ciclo observado y conservado por el probe es estrictamente doble-buffer:

```text
idx = frame_id & 1
CPU escribe buffer[idx]
SubmitFlip(handle, idx, 1, frame_id)
WaitEqueue(un evento de flip)
siguiente frame
```

La espera impide que el bucle reutilice inmediatamente una superficie que aún
está en presentación. Es una confirmación de VideoOut, **no** un fence que
demuestre que una escritura AGC previa haya terminado. En la futura ruta GPU el
orden deberá ser `submit AGC -> fence GPU -> SubmitFlip -> evento VideoOut`.

El cleanup local ahora conserva estado explícito: sólo desregistra si el
registro terminó, elimina el evento y la equeue, cierra VideoOut, desmonta el
mapping y finalmente libera la memoria directa.

La ruta CPU usa memoria tipo `3`, mapping `0x33` y alineación `0x20000`.
La máscara pública independiente permite descomponer `0x33` como
`CPU_READ | CPU_WRITE | GPU_READ | GPU_WRITE`: la asignación solicita de forma
explícita acceso de ambas partes. Esto prueba que no faltan los bits básicos de
permiso GPU en el mapping, pero todavía **no** demuestra que una cola AGC creada
por nuestro proceso pueda acceder efectivamente a él ni cuál es el contrato de
coherencia antes de presentarlo.

## Layout tiled relevante

El backend SDL PS5 no escribe directamente el framebuffer lineal de SDL en la
superficie de VideoOut. `PS5_UpdateWindowFramebuffer` llama primero a
`PS5_Tilemap_Blit`; esa implementación define tiles de 512×128 píxeles BGRA de
cuatro bytes y ejecuta el swizzle antes de `sceVideoOutSubmitFlip`. Su huella
es:

```text
last_band = floor((height-1)/128) * (128*width)
last_tile = floor((width-1)/512) * (512*128)
bytes     = (last_band + last_tile + 512*128) * 4
```

Para 3840×2160, el resultado es exactamente `0x02000000` bytes (32 MiB).
Un color sólido repite el mismo DWORD en todos los píxeles, así que cualquier
permutación tiled produce la misma imagen; no hace falta ejecutar el swizzler
CPU para el primer frame uniforme.

El probe nativo y el `test.c` histórico de hbldr rellenan su memoria como una
secuencia lineal. Su éxito con un color uniforme valida registro, flip y
presentación, pero no prueba scanout lineal: un color uniforme es precisamente
invariante al swizzle. Los patrones no uniformes de ese probe tampoco se usan
como evidencia de una correspondencia correcta de coordenadas. Para un patrón
espacial se toma como referencia el `PS5_TileOffset` del backend SDL hasta que
se contraste contra un descriptor AGC real.

El builder `sceAgcDcbDmaData` limita el conteo a 26 bits. `0x02000000` cabe en
un único paquete porque es menor que `0x03ffffff`. La implementación primaria
AMD PAL GFX9 confirma además que `src_sel=data` repite el DWORD inmediato como
un fill sobre todo `byte_count`; su reset de occlusion queries usa exactamente
esa modalidad para poner a cero un rango completo. Por tanto, tamaño, swizzle y
semántica de fuente no impiden un clear 4K mediante un único packet. Esto no
prueba la transición de caché hacia el display.

## Hueco que permanece

El juego reserva backbuffers mediante pool 1, tipo de memoria `0x0c`,
protección `0x0f2` y flags de mapping `0x10`; el mismo puntero alimenta VideoOut
y el descriptor de render target AGC. El homebrew CPU usa tipo `3`/`0x33`, que
ya contiene los permisos `GPU_READ|GPU_WRITE`.

Antes de un submit hay que demostrar una de estas dos rutas:

1. que los permisos GPU solicitados por la asignación VideoOut tipo `3`/`0x33`
   son efectivos para la cola AGC creada por nuestro proceso; o
2. que podemos reproducir de forma segura el backing del juego
   `0x0c`/`0x0f2`/`0x10` dentro del host homebrew.

Después faltan todavía transición/coherencia hacia uso de display, fence con
timeout y flip sólo tras observar finalización. El primer submit no debe usar
32 MiB: debe escribir cuatro bytes en memoria privada y comprobar el fence. La
ampliación a 32 MiB será otro escalón independiente.

## Herramienta de cálculo

```sh
python3 research/gpu/tools/plan_solid_dma_fill.py 3840 2160
```

La salida incluye los siete DWORD exactos con dirección deliberadamente
sintética y conserva `gpu_visibility_proven`, `cache_transition_proven`,
`display_coherency_proven`, `flip_after_gpu_fence_proven` y `submitted` en
falso para evitar confundir composición estática con soporte hardware.

El contrato estático del ciclo y del cleanup se comprueba con:

```sh
python3 research/gpu/tools/verify_videoout_cycle.py
```

El resultado marca deliberadamente `gpu_fence_proven=false`,
`linear_scanout_proven=false` y `submitted_to_agc=false`.
