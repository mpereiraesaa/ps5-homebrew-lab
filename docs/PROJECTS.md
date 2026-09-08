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
y cero errores. La Fase 5, platform layer, está completa. La Fase 6 está
activa y sus cinco primeros gates ya probaron el loader híbrido,
`filesystem_stdio.prx`, `server.prx`, `menu.prx` y `client.prx` en FW 12.02.
El cliente ejecutó video/HUD real sobre `c1a0` y descargó los cuatro módulos
en orden; `ref_agc` es el único checkpoint restante de la fase.

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

## Capa de compatibilidad Win32 — activa

`projects/prospero-win` (PPSA99995) busca ejecutar binarios Windows originales.
PE64 necesita puentes ABI Win64; PE32 requiere ejecución por software. La ruta
LDT probada está rechazada en FW 12.02. La ejecución de aplicaciones sigue
pendiente; el primer juego objetivo es el Space Cadet Pinball original.

El mapeo del Pinball original pasó en PS5 el 2026-09-08:
`20260908T145242477Z_PPSA99995_prospero-win_0x1021ed623a4eb`.
Base 0x01000000, 311296 bytes reservados, tres secciones verificadas sin
discrepancias y cierre limpio. Una página de 16 KiB combina permisos WX.
Las ocho DLLs se clasificaron como interfaces host aún sin implementar.

El traductor acotado ejecutó en host 385 instrucciones del arranque original (límite de 4096 eventos),
GetModuleHandleA(NULL), __set_app_type, los dos getters CRT, _controlfp, _initterm y __getmainargs. Enlaza 205 funciones y dos datos;
los getters de modos CRT tienen pruebas unitarias y los demás handlers
siguen pendientes. El callback original ya retorna junto con su _initterm;
hay dieciocho llamadas completadas a dieciséis APIs distintas. GetStartupInfoA, LoadStringA, lstrlenA y malloc retornan y
el siguiente stop es lstrcpyA; el anidamiento de callbacks sigue validado sólo con pruebas sintéticas.
Esto no acredita ejecución del juego en PS5 ni
inicialización Win32. Detalles: `projects/prospero-win/docs/X86_EXECUTION.md`.

Próximos pasos: ampliar y validar ejecución x86/ABI, APIs Win32 y presentación AGC.
Audio y control partirán de los contratos validados de Xash3D; WinMM, mensajes
Windows y MIDI necesitan adaptación. Licencia declarada LGPL-2.1-or-later;
la extracción de componentes GPL de Xash3D requiere resolver su licencia.

Estado y evidencias: `projects/prospero-win/docs/PINBALL_TARGET.md`.
Plan vigente: `projects/prospero-win/docs/ROADMAP.md`.

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
`docs/XASH3D_CHECKPOINT.md`. Las Fases 0–5 están cerradas en hardware y la Fase
6 tiene tres gates cerrados. El engine conserva su identidad `PPSA99996` y ya
carga filesystem y servidor como PRXs propios, con lifecycle explícito,
callbacks ABI probados y teardown ordenado. El trabajo inmediato es convertir
`menu`; después siguen `client` y `ref_agc` como checkpoints independientes.

Half-Life requiere datos originales que no forman parte del código del engine
y nunca deben incorporarse a repositorios ni artefactos públicos.
