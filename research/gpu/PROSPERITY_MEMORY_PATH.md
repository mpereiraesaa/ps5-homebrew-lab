# Prosperity como referencia del ABI de memoria extendida

Revisión inicial: 2026-09-04. Fuente pública examinada:
`Force67/prosperity`, commit
`cbe5456b4176a0becad006346809d3f7cf4769c3`.

## Hallazgo aplicable a 0W

Prosperity reconstruye dos rutas distintas:

1. `sceKernelMapDirectMemory`, syscall 628, cuyo ABI kernel recibe VA, tamaño,
   protección, flags, un campo empaquetado alignment/type y offset físico.
   `flags & 0x10` solicita dirección fija.
2. `sceKernelBatchMap`, cuya operación 0 (`MAP_DIRECT`) compromete un rango ya
   elegido usando explícitamente la VA, el offset físico y el tamaño.

La entrada BatchMap reconstruida tiene 32 bytes:

```text
+0x00  u64 start
+0x08  u64 physical offset
+0x10  u64 length
+0x18  u8  protection
+0x19  u8  memory type
+0x1a  u16 padding
+0x1c  u32 operation
```

Esto confirma que nuestro `stage_a_batch_entry` posee el layout correcto aunque
lo exprese como dos `uint16_t`: el valor little-endian `0x0cf2` en `+0x18`
equivale exactamente a `protection=0xf2` y `memoryType=0x0c`.

## Interpretación de los resultados locales

- 0Q ya confirmó en hardware que BatchMap operación 0 acepta la combinación
  `protection=0xf2`, `memoryType=0x0c`, región 128 KiB y alineación 64 KiB.
- 0V confirmó que `0xfe0040000` puede reservarse exactamente.
- El primer 0W confirmó que reservar esa VA y asignar memoria física funciona,
  pero el wrapper `sceKernelMapDirectMemory` rechaza el commit con
  `0x80020016`.

Por tanto, el próximo experimento no debe variar más parámetros del wrapper.
Debe combinar las dos operaciones ya probadas por separado:

```text
ReserveVirtualRange(exact 0xfe0040000, 128 KiB, align 64 KiB)
AllocateMainDirectMemory(128 KiB, align 64 KiB, type 0x0c)
BatchMap({start=fixed, offset=physical, length=128 KiB,
          protection=0xf2, memoryType=0x0c, operation=MAP_DIRECT})
canarios CPU
BatchMap(operation=UNMAP)
ReleaseDirectMemory
munmap reservation
```

Este debe ser un probe **mapping-only**, sin cargar `libSceAgc`, modificar
punteros, crear DCB o hacer submit. Sólo si completa mapping, canarios y cleanup
se podrá recomponer 0W sobre esta ruta.

## Resultado de hardware 0X

0X reservó exactamente `0xfe0040000` y asignó 128 KiB físicos type `0x0c`,
pero BatchMap operación 0 devolvió `0x80020016` con `processed=0`. La liberación
física y el `munmap` de la reserva devolvieron cero; el resultado se clasifica
`map_rejected_clean`. No cargó AGC ni hizo submit y el host se cerró en 100 ms.

Esto descarta que la diferencia entre syscall 628 y BatchMap sea por sí sola la
solución. La variable común que queda es la VA `0xfe0040000` dentro del host
FAKE: puede reservarse, pero ambas interfaces de direct memory se niegan a
comprometerla. El próximo análisis debe determinar si la ventana está limitada
por clasificación de proceso, por el mapa DMEM concedido al host o por una
regla adicional del kernel; cambiar tamaños o repetir ambos wrappers ya no es
informativo.

## Límites de la referencia

Prosperity implementa el comportamiento en un host Linux; no es el código del
kernel PS5. Sus comentarios de ABI son hipótesis de interoperabilidad apoyadas
en wrappers y títulos, así que sirven para escoger una prueba, no sustituyen la
confirmación en FW 12.02. El repositorio es GPL-2.0: aquí se documentan hechos y
layouts; no se ha copiado su implementación.
