# Proyectos y candidatos

## Port Xash3D sobre AGC — activo

Implementación canónica: `projects/ps5-xash3d` (`mpereiraesaa/ps5-xash3d`,
repositorio público), bifurcado de `ps5-agc-gears` en
`cbff264` con toda la historia el 2026-09-06. Ahí vive el renderer AGC, el
visor BSP de las Fases 1–3 y todas las fases siguientes del port. Su README
gobierna el desarrollo nuevo; `GPU_RESEARCH.md` conserva la progresión
experimental.

Estado: además de los tres engranajes 3D heredados, el port ya renderiza
`c1a0` con lightmap dinámico acotado, mipmaps deterministas, filtrado
trilineal/aniso 4:1 y pases separados opaco, alpha-test y sky. Las Fases 1 y 2
pasaron gates de 60.000 frames con cero errores; la Fase 3 también cerró sus
seis gates y su soak final de 60.000 frames con contabilidad exacta, tokens
VideoOut/fence exactos y guardas intactas. La implementación de Fase 2 se
fusionó mediante `mpereiraesaa/ps5-agc-gears#8` como `642d348`; la Fase 3 se
fusionó mediante `mpereiraesaa/ps5-agc-gears#9` como `cbff264`; ambos commits
son ya historia de `ps5-xash3d`, fijado por el submódulo canónico. Los antiguos
Stages A–I y `PPSA99998` están archivados bajo `legacy/`.

La Fase 4 está completa. Sus ocho gates cerraron catálogo/binding, matriz
blend/depth/cull/fog/lightmap, viewport/scissor, ruta 2D, lightstyles/luces
dinámicas, sprites/partículas, Studio animado, brush entities y visibilidad
PVS/frustum. El gate integrado final sostuvo agua, vidrio, efectos, Studio y
HUD durante 60.000 frames con ownership exacto, guardas intactas, BYE gap-free
y cero errores. Las Fases 5 y 6 están completas: platform layer, loader
híbrido, `filesystem_stdio.prx`, `server.prx`, `menu.prx`, `client.prx` y
`ref_agc` tienen evidencia FW 12.02 y teardown exacto. La Fase 7 está activa.
El mundo vivo de `c1a0`, sus 164 texturas y el atlas 1024x256 de lightmaps del
engine ya llegan al compositor mediante AGC nativo. El checkpoint fusionado
`4f9d38d` pasó 1.075 frames con 3.695 draws lightmapped, ocho reclaims y cero
errores. El checkpoint `77c742a` añade skybox vivo de seis caras y 35 draws
turbulentos animados por el tiempo del engine; pasó 1.616 frames, ocho reclaims
y teardown exacto, sin capa de emulación OpenGL. El checkpoint `0bdcbfb`
traduce las listas 2D vivas en orden: 61.316 quads, 367.896 índices y 610
batches pasaron 1.044 frames emparejados con evidencia visual. El checkpoint
`a975b86` presenta MainUI por AGC durante 223 frames y luego carga `c1a0`
mediante el command buffer del engine; el serial de mapa 1 aparece en el serial
renderer 224 y el vídeo muestra ambos estados. Siguen entidades, viewmodel,
gameplay, rendimiento, transiciones, soaks y release.

Identidades instaladas: Xash3D usa `PPSA99996` y la demo Gears usa
`PPSA99997`, cada una con helpers exactos independientes. El host histórico
`PPSA99998` fue desinstalado; no queda en las rutas de aplicación/montaje ni en
las filas vivas de `app.db`.

## Demo GPU nativa Gears — congelada

`projects/ps5-agc-gears` es el repositorio público de la demo Gears standalone,
validada hasta 60.000 frames. Queda congelado como demo: sólo recibe
correcciones propias. El PR fusionado `mpereiraesaa/ps5-agc-gears#10` revirtió
los merges de Fase 2/3 (#8, #9), devolvió el árbol de la demo a `8f035b7` y lo
etiquetó como `gears-demo-freeze`; el submódulo del laboratorio fija ese commit.

La primera capa reutilizable ya existe en `sdk/agc`: headers sanitizados,
facades de enlace para `libSceAgc`/`libSceAgcDriver`, manifiesto de NIDs y test
host. Los builds del laboratorio consumen esa capa en vez de depender del stub
copiado desde un proyecto tercero.

## Observabilidad Remote Play — activa

`tools/ps5_remoteplay.py` integra Headless LinkDev y Chiaki como tooling del
laboratorio. El stream directo desde consola reutiliza la entrada ya registrada
y evita abrir la ventana principal del cliente. El pairing, stream, captura PNG
y grabación MP4 están validados en FW 12.02. La evidencia visual se conserva en
el árbol privado ignorado y complementa, pero no reemplaza, la telemetría
`ps5log/1`.

La entrada de consola ya registrada se reutiliza. El flujo normal abre y cierra
el stream directo desde CLI. Tras una desconexión, `stop-stream` termina por PID
únicamente el proceso CLI aislado y `stream` hace la misma limpieza antes de
reiniciar; no se enfoca, confirma ni pulsa el diálogo `Session has quit`.

## Capability lab — archivo histórico

Objetivo: conocer de forma empírica los límites del entorno nativo antes de
invertir esfuerzo en un port grande. Código preservado en `legacy/probes/`.

## Capa SDL2 — pausada

Se conserva como referencia para VideoOut, audio, mando y tile mapping. Su
renderer PS5 actual es software y no es la línea activa.

## Primer juego nativo — candidato

Recomendación: un source port de Quake con render software. Es pequeño, no
requiere JIT y permite validar el pipeline completo. El repositorio no debe
contener assets comerciales (`pak*.pak`).

## Emulación DOS — exploración futura

Recomendación: evaluar DOSBox o DOSBox-X, empezando por intérprete y añadiendo
dynamic core después. El allocator JIT debe respetar los límites documentados de
concurrencia y memoria ejecutable.

## GoldSrc / Xash3D — objetivo activo

Plan vigente: `docs/XASH3D_PS5_PLAN.html`; checkpoint textual:
`docs/XASH3D_CHECKPOINT.md`. Las Fases 0–6 están cerradas en hardware. El
engine conserva su identidad `PPSA99996` y carga filesystem, servidor, MainUI,
cliente y renderer como PRXs propios, con lifecycle explícito, callbacks ABI
probados y teardown ordenado. La Fase 7 ya presenta el mundo, texturas base,
lightmaps, skybox, superficies turbulentas, listas 2D y MainUI vivos, con
transición nativa al mapa; el trabajo inmediato es entidades y viewmodel.

Half-Life requiere datos originales que no forman parte del código del engine
y nunca deben incorporarse a repositorios ni artefactos públicos.
