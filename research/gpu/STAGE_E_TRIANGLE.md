# Stage E: primer triángulo acelerado

Estado: **completado en PS5 FW 12.02 el 2026-09-05**.

## Resultado confirmado

La aplicación nativa `PPSA99998` presentó un triángulo verde centrado sobre un
fondo morado. El pipeline usa únicamente shaders propios compilados con LLPC/PAL
para `gfx1013`; no incorpora shaders, blobs ni comandos copiados de juegos.

- fSELF SHA-256:
  `18b4f4ccc46510e4aaac3bd37fba74d4d039a4722b2e0743e6cce9fad5f9d800`.
- DCB: 122 DWORD.
- Pipeline enlazado: 84 CX, 12 SH y 3 UC.
- Shaders extraídos del ELF PAL: GS 196 B, PS 16 B.
- Draw: `DrawIndexAuto(3)`.
- Resultado: `SubmitDcb=0`, fence `1 -> 0`, evento VideoOut exacto.
- Verificación CPU: 285.120 palabras/píxeles cambiados, igual al área esperada.
- Guardas y backbuffer de recuperación intactos; hold visual de 5 s.
- Unmap, releases, unload y cierre exacto completados.
- Confirmación humana inequívoca del triángulo.

Evidencia canónica:
`captures/agc-stage-e-centered-triangle-runtime.json`.

## Contrato que debe conservarse

Orden del stream:

```text
WaitSafeForRendering
  -> CX indirect
  -> UC indirect
  -> SH indirect
  -> DrawIndexAuto(3)
  -> SetFlip
  -> RELEASE_MEM ownership
```

Los indirectos **no se codifican manualmente**. En FW 12.02 los builders nativos
emiten cinco DWORD, no los cuatro que asumía el primer compositor:

- `sceAgcDcbSetCxRegistersIndirect`
- `sceAgcDcbSetUcRegistersIndirect`
- `sceAgcDcbSetShRegistersIndirect`
- `sceAgcDcbDrawIndexAuto`
- `sceAgcDcbSetFlip`

La discrepancia de 4/5 DWORD fue la causa concreta del stall previo. El builder
host valida avance, límites y canarios para impedir que reaparezca.

## Toolchain de shaders

La fuente es `shaders/stage-e/fullscreen_triangle.pipe`. El script
`tools/build_stage_e_gfx1013.py` obtiene dinámicamente offsets y tamaños desde
la tabla de símbolos del ELF PAL mediante `llvm-readelf`; no presupone un tamaño
fijo de GS. La metadata pública se traduce a los registros CX/SH, specials,
exports y modifier de draw. `BaseVertex` y `BaseInstance` presentes y
`DrawIndex` ausente producen `ShaderDrawModifier=5`.

El directorio `third_party/amd-llpc/build-gfx1030` conserva un nombre histórico
porque CMake incrustó su ruta absoluta. No expresa el target: todos los gates
Stage E exigen y verifican `gfx1013`.

## Bootstrap y diagnóstico visual

El bootstrap DMA usa rojo (`0xffff2020`) y el render target se inicializa en
morado. Así, rojo, morado y verde identifican fases distintas y evitan confundir
un clear residual con el draw. El backbuffer se mantiene cinco segundos antes
del teardown.

## Lecciones conservadas

- Un retorno cero de submit sólo prueba aceptación; el éxito requiere efecto,
  completion, presentación y cleanup.
- Mantener vivos shaders, headers, código, registros y buffers hasta la fence.
- Leer tamaños de artefactos, no fijarlos a una versión anterior.
- Los juegos comerciales pueden ser oráculos privados locales, pero sólo se
  conservan agregados y contratos reimplementados independientemente.
- Las capturas fallidas de Stage E son historial diagnóstico y están
  supersedidas por la captura canónica indicada arriba.

## Siguiente frontera

Extraer el contrato en un backend pequeño, implementar doble buffer continuo y
validar 120, 1.000 y 10.000 frames. Véase `../../docs/ROADMAP.md`.
