# Estado guardado del laboratorio

> Registro histórico de artefactos privados. El release publicable vigente se
> construye exclusivamente desde `projects/ps5-agc-gears`; sus gates están en
> `projects/ps5-agc-gears/docs/RELEASING.md`.

Generado y reconciliado: 2026-09-05.

## Artefacto canónico

| Elemento | Valor |
| --- | --- |
| Firmware validado | PS5 12.02 |
| Title ID | `PPSA99998` |
| GPU | `gfx1013` |
| fSELF | `legacy/apps/agc-native-sce/dist-stage-e/PPSA99998/eboot.bin` |
| SHA-256 fSELF | `18b4f4ccc46510e4aaac3bd37fba74d4d039a4722b2e0743e6cce9fad5f9d800` |
| ELF host | `legacy/apps/agc-native-sce/build-stage-e/eboot.elf` |
| SHA-256 ELF | `a6270b4ac7a646943cbdd5c4b760c78049ad65d319c3262c777e5102e1635408` |
| ELF PAL shader | `research/gpu/build/stage-e-shaders/fullscreen_triangle.pal.elf` |
| SHA-256 shader | `28827f2ae972bc4ccbb72fa9ebd0d013aabe5acd4f4330785421f6e76e64ade9` |
| Evidencia hardware | `research/gpu/captures/agc-stage-e-centered-triangle-runtime.json` |

## Verificación local

```sh
cd legacy/apps/agc-native-sce
./build_stage_e.sh
python3 verify_stage_e.py
```

Ambos comandos pasaron desde un build limpio durante esta reconciliación. El
verificador confirma que el hash del artefacto coincide con la captura hardware
y marca `gpu_executed: true`.

## Retención y limpieza

- Conservados: fuentes, toolchain fijado, análisis Ghidra, dumps privados,
  capturas históricas y build/dist Stage E final.
- Retirados del árbol (recuperables desde la papelera): cachés Python y
  build/dist reproducibles de Stage B, C, D y checkpoints Stage E superados.
- `third_party/amd-llpc/build-gfx1030` se conserva porque el cache CMake depende
  de su ruta absoluta; el nombre no describe el target compilado.

## Control de versiones

Esta carpeta no contiene metadatos `.git`; por tanto este estado está guardado
en el filesystem, con hashes reproducibles, pero no existe un commit local que
lo proteja. Inicializar o conectar un repositorio será una decisión separada.

El único cambio local de toolchain está inventariado en
`patches/llpc/0001-lgc-add-gfx1013-target.patch`; LLVM permanece limpio. La
política para futuros forks personales está en `docs/UPSTREAMING.md`.

## Stage G/21 confirmado

La build G/21 del 2026-09-05 mueve la tabla DSV indirecta desde el
stack a `shader + 0x3e00` y añade un guard host-tested de procedencia
GPU-visible. `make agc-check`, Stage G y Stage I pasan offline; en hardware G/21
completó submit, fence, efecto GPU, evento, BYE y teardown. Su fSELF es
`6f5d1bd7153f152a26847d8aa3b74c4a36d4cd91afd9fcd73ba6dc3f83526ba3`
y la evidencia está en
`research/gpu/captures/runtime/20260905T105717802Z_PPSA99998_agc-native-sce_0x989598b55e8.capture.json`.
Stage E continúa como artefacto mínimo canónico; G/21 añade la evidencia visual
confirmada de un cubo 3D centrado sobre fondo uniforme.

La variante lifecycle SHA-256
`af53c3abbd149821cc9d226214b5615275417d33505f21abbbed9c909167624c`
completó GPU y teardown, pero `return 0` produjo después un diálogo de error del
shell. Se conserva como evidencia negativa. La variante `_exit(0)`, SHA-256
`850a8938c8bd1e4bd3b446e8e84c1013f201d3c8c4febfd5d4d7120ac43991c5`,
volvió al menú sin diálogo y sin BigApp residual; es el auto-cierre limpio
confirmado en FW 12.02.

## Stage G/22 confirmado

G/22 difiere de G/21 únicamente al consumir los 22 pares, incluido
`DB_DEPTH_CONTROL=0xb6` (`LESS_EQUAL`, lectura y escritura). El fSELF
`912056bc1e3739953589e3c56aa642905f3a1a2f7fbe9bf1130be2b338efa7e7`
completó el contrato GPU y el operador observó tres caras correctamente
ocluidas. La demostración semántica final se realizó con un litmus de
superficies superpuestas diseñado para producir colores distintos con depth
on/off.

Ese litmus quedó aprobado como Stage G/23. Con geometría, shader y orden
idénticos, OFF/21 dejó que la superficie lejana oscura sobrescribiera a la
cercana, mientras ON/22 conservó la cercana brillante mediante `LESS_EQUAL`.
El operador confirmó una diferencia visual fuerte y ambos contratos de
completion fueron `present_complete`.

## Stage H confirmado

La primera escena Gears propia quedó ejecutada y confirmada visualmente en PS5:
tres mallas procedurales, tres materiales, MVP/quaternion independientes,
iluminación, D32 `LESS_EQUAL` y tres `DrawIndexAuto` en un submit. El artefacto
`5f510b7572e04a32d3c0988b989aef64b6488ddf44dcb19cdef3477deebedbf3`
completó fence, VideoOut, guardas, teardown y `_exit(0)`. La captura canónica es
`research/gpu/captures/runtime/20260905T115308530Z_PPSA99998_agc-native-sce_0xc957db3aa4d.capture.json`.

## Stage I confirmado

La animación Gears completó 300/300 frames con dos backbuffers, depth D32,
tres draws por frame, tokens monotónicos, fence GPU y evento VideoOut exacto.
No hubo errores ni corrupción de guardas y el proceso terminó con BYE y teardown
limpio. fSELF:
`0acab82e79e1a0a6685367a6f84c63b78b75d8992623d68b18fa23860ebb4292`.
Captura:
`research/gpu/captures/runtime/20260905T120527429Z_PPSA99998_agc-native-sce_0xd4186f0c894.capture.json`.

Los soaks seriales de 1.000 y 10.000 frames quedaron aprobados con conteos
exactos, cero errores, guardas intactas y teardown limpio. La evidencia 10K es
`research/gpu/captures/runtime/20260905T123120692Z_PPSA99998_agc-native-sce_0xeab2b589547.capture.json`
y su fSELF es
`868ef4c150ef800c4f73d60ce6b89e0f98f6d5a7cc44f2d6f198f94701c23ca7`.
La revisión pipelined mantiene dos command buffers y fences independientes y
somete dos frames antes de retirar el slot más antiguo. La prueba final completó
10.000/10.000 con `max_frames_in_flight=2`, cero errores, guardas intactas,
fences finales cero, token VideoOut exacto y teardown limpio. Sostuvo 16,682904
ms/frame (59,9416 fps). fSELF
`f05759892259dc0087273d4e2038722a0f2eb2ec17f132118a0fd887e0472234`;
captura
`research/gpu/captures/runtime/20260905T124347472Z_PPSA99998_agc-native-sce_0xf590a3bdbe1.capture.json`.
