# Proyectos y candidatos

## Demo GPU nativa — activa

Implementación canónica: `projects/ps5-agc-gears`, repositorio público,
standalone y validado en hardware. Su roadmap propio gobierna el desarrollo
nuevo; `GPU_RESEARCH.md` conserva la progresión experimental.

Estado: además de los tres engranajes 3D, la rama de Xash3D ya renderiza
`c1a0` con texturas base y lightmaps, cámara noclip, constantes por frame y un
overlay pulsante desde recursos transitorios. Las Fases 1 y 2 pasaron gates de
60.000 frames con cero errores. La implementación consolidada se fusionó
mediante `mpereiraesaa/ps5-agc-gears#8` como `642d348`, commit que fija ahora el
submódulo canónico. Los antiguos Stages A–I y `PPSA99998` están archivados bajo
`legacy/`.

La primera capa reutilizable ya existe en `sdk/agc`: headers sanitizados,
facades de enlace para `libSceAgc`/`libSceAgcDriver`, manifiesto de NIDs y test
host. Los builds del laboratorio consumen esa capa en vez de depender del stub
copiado desde un proyecto tercero.

## Observabilidad Remote Play — activa

`tools/ps5_remoteplay.py` integra Headless LinkDev y Chiaki como tooling del
laboratorio. El pairing, stream, captura PNG y grabación MP4 están validados en
FW 12.02. La evidencia visual se conserva en el árbol privado ignorado y
complementa, pero no reemplaza, la telemetría `ps5log/1`.

La entrada de consola ya registrada se reutiliza. Tomar el DualSense físico
desconecta la sesión de streaming y deja un diálogo `Session has quit`; el PR
abierto `mpereiraesaa/ps5-homebrew-lab#8` añade detección de estado y
`acknowledge-quit` explícito sin asumir el foco de la ventana.

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
`docs/XASH3D_CHECKPOINT.md`. Las Fases 0–2 están cerradas y la Fase 3, ruta de
texturas dinámicas/mipmapped, es la siguiente. El probe de símbolos demuestra
que libc y C++ no son el bloqueo: sólo faltan tres símbolos C triviales; el
trabajo real es `platform/ps5`, `ref_agc` y la integración modular ya habilitada
por el loader PRX propio.

Half-Life requiere datos originales que no forman parte del código del engine
y nunca deben incorporarse a repositorios ni artefactos públicos.
