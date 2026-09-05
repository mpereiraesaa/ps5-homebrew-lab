# Memoria operativa

> Los puntos Stage A–I se conservan como memoria histórica. La fuente operativa
> actual es `docs/CURRENT.md` y el repo `projects/ps5-agc-gears`.

Leer primero `docs/STATUS.md`, `docs/ROADMAP.md`, `docs/OBSERVABILITY.md` y
`research/gpu/STAGE_E_TRIANGLE.md`. Registrar por separado evidencia observada,
inferencia e hipótesis. Nunca guardar datos de cuenta, número de serie, dumps,
shaders propietarios ni fragmentos sustanciales propietarios.

## Contexto vigente

- Consola de laboratorio: firmware 12.02; GPU objetivo: `gfx1013`.
- Aplicación activa: `PPSA99998`, título nativo servido por ShadowMountPlus.
- Hito: triángulo verde centrado sobre morado, shaders propios, DCB 122 DWORD,
  `SubmitDcb=0`, fence cero, evento exacto y cleanup completo.
- Causa del stall anterior: los paquetes indirectos CX/UC/SH manuales tenían
  cuatro DWORD; los builders nativos de este firmware emiten cinco. Usar siempre
  `sceAgcDcbSetCxRegistersIndirect`, `sceAgcDcbSetUcRegistersIndirect`,
  `sceAgcDcbSetShRegistersIndirect` y `sceAgcDcbDrawIndexAuto`.
- El script de shaders obtiene offsets y tamaños desde el ELF PAL; no fijar el
  tamaño de GS. El shader centrado actual mide 196 B (GS) y 16 B (PS).
- `sdk/agc` es la fuente común de declaraciones y stubs AGC: 16 firmas/NIDs
  confirmados, helper DMA fill L2+sync y test `make agc-sdk-check`. No añadir
  APIs NID-only hasta cerrar su ABI.
- El `cleanup` operativo significa cerrar exactamente `PPSA99998`; si hace falta
  sanear el estado, lanzar San Andreas, esperar su intro y cerrarlo. Reiniciar
  sólo ante recuperación real.
- `FAKE00000`/`hbldr` quedan únicamente como ruta histórica de probes.
- Toda iteración `PPSA99998` usa `tools/agc_net_monitor.py` y `ps5logd` TCP
  9300. El runtime sólo lee `/app0/dev.conf`; no escribe USB, `/download0` ni
  otro filesystem de consola y el launcher no hace mounts. Exigir HELLO/BYE,
  boot token coincidente, cero gaps/RAW/oversized y hash exacto.
- LLVM está limpio y ya soporta el nombre `gfx1013`; el parche local real está
  en LLPC/LGC. Mantener sincronizado
  `patches/llpc/0001-lgc-add-gfx1013-target.patch` y seguir
  `docs/UPSTREAMING.md` antes de publicar forks en GitHub.

## Otros límites ya medidos

- WebKit: Canvas 2D sí; WASM, WebGL, Web Audio y Gamepad no.
- 16 CPUs lógicas; mejor escalado observado hasta 12 workers.
- Heap anónimo: 432 MiB verificados; 448 MiB falló. Presupuesto conservador:
  320–384 MiB.
- Main Direct Memory: 3 GiB conservadores bajo soak multimedia; 4 GiB sólo en
  una prueba combinada corta.
- JIT preferido: doble mapping `jitshm` RW/RX; evitar transiciones `mprotect`
  concurrentes.

## Disciplina

1. Cambiar una variable por iteración y construir con cero warnings.
2. Ejecutar los gates host antes de tocar la consola.
3. Exigir efecto observable, fence, evento, guardas y cleanup; `SubmitDcb=0`
   por sí solo no demuestra ejecución.
4. Mantener viva toda memoria referenciada hasta completar su fence.
5. Actualizar captura, STATUS, FINDINGS y ROADMAP después de confirmar hardware.
6. Para Stage G ejecutar `make agc-stage-g-check`: 21 pares significa bind DSV
   sin depth activo; 22 pares es el gate posterior de consumo `LESS_EQUAL`.
7. El frame loop usa `gears_frame_tracker`: después de submit no se
   reutiliza ni cancela un slot hasta fence GPU + token VideoOut exacto.
8. `gears_animation` es la fuente de tiempo/buffer/token y parámetros por frame;
   el soak host obligatorio es `make agc-gears-animation-check`.
9. En animación usar `gears_telemetry`: acumular cada frame y transmitir sólo
   el inicial, cada 60, errores y final por `ps5log/1`; el runtime nunca escribe
   logs a archivos.
10. Antes de cualquier build/deploy AGC ejecutar `make agc-check`. Es el gate
    permanente que evita olvidar `logging_server`, evidencia, ownership,
    telemetría y el
    resumen terminal obligatorio del frame loop.
11. Stage I está integrado offline: 300 frames, doble pipeline/backbuffer,
    clears DMA color+D32, depth 22, tres draws, tokens exactos y guardas. Nunca
    saltar el orden hardware G/21 -> G/22 -> H -> I ni describirlo como probado
    en consola antes de disponer de captura `ps5logd` y confirmación visual.
