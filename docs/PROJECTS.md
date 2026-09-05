# Proyectos y candidatos

## Demo GPU nativa — activa

Implementación canónica: `projects/ps5-agc-gears`, repositorio público,
standalone y validado en hardware. Su roadmap propio gobierna el desarrollo
nuevo; `GPU_RESEARCH.md` conserva la progresión experimental.

Estado: tres engranajes 3D animados, depth, iluminación, doble buffer, dos
frames en vuelo y soaks de hasta 60.000 frames. Los antiguos Stages A–I y
`PPSA99998` están archivados bajo `legacy/`.

La primera capa reutilizable ya existe en `sdk/agc`: headers sanitizados,
facades de enlace para `libSceAgc`/`libSceAgcDriver`, manifiesto de NIDs y test
host. Los builds del laboratorio consumen esa capa en vez de depender del stub
copiado desde un proyecto tercero.

## Observabilidad Remote Play — activa

`tools/ps5_remoteplay.py` integra Headless LinkDev y Chiaki como tooling del
laboratorio. El pairing, stream, captura PNG y grabación MP4 están validados en
FW 12.02. La evidencia visual se conserva en el árbol privado ignorado y
complementa, pero no reemplaza, la telemetría `ps5log/1`.

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

## GoldSrc — candidato posterior

Evaluar Xash3D FWGS y sus licencias. Half-Life requiere datos originales que no
forman parte del código del engine y no deben incorporarse al repositorio.
