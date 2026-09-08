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
y cero errores. La Fase 5, platform layer, es el siguiente objetivo.

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

`projects/prospero-win` es una capa de compatibilidad Win32 de cero emulación
para PS5: los programas clásicos de PC no se interpretan ni se recompilan, su
código máquina se mapea manualmente en el espacio de direcciones de la consola
y se ejecuta directamente sobre Zen 2, mientras que la superficie de API que
esos programas invocan se reimplementa de forma nativa. Identidad de
desarrollo: `PPSA99995`.

La Fase 0.1 **pasó en FW 12.02 el 2026-09-08** (corrida
`20260908T111650513Z_PPSA99995_prospero-win_0xf65743b2ac43`): lector PE mínimo
sin dependencias del sistema operativo, planificación del layout mapeado,
relocalización base, protecciones a la granularidad real de página y
resolución recursiva de dependencias de terceros. La consola mapeó un
ejecutable de Windows y la DLL de terceros que importa, los rebasó fuera de
su base preferida aplicando relocalizaciones, los verificó byte a byte,
resolvió la cadena de dependencias y liberó todo: 25 registros, BYE sin gaps
y `PW_EXIT result=0`.
Los módulos Win32 (`kernel32`, `msvcrt`, `ddraw`...) nunca se cargan de disco:
se registran como *host bindings* que la propia capa implementará. Ese reparto
es el diseño completo del proyecto.

Frontera documentada antes de escribir código que dependa de ella. Ejecutar
código de 32 bits —la mayor parte del catálogo objetivo— es una pregunta
abierta, no una puerta cerrada: Zen 2 ejecuta instrucciones de 32 bits de
forma nativa en modo compatibilidad, y entrar en ese modo exige un descriptor
de segmento de código que el kernel instala mediante
`sysarch(I386_SET_LDT, ...)`. El SDK de payload fijado declara esa llamada,
pero ninguna corrida la ha ejercitado en este firmware, así que el gate 0.2a
es exactamente ese probe. Está construido y validado en host: en una máquina
x86-64 corriente los descriptores se instalan, el far transfer entra en modo
compatibilidad desde una página de código ya sellada como no escribible, se
ejecutan instrucciones genuinamente de 32 bits y el control vuelve; lo que
falta es la medida en consola, no el diseño. Esa corrida también estableció
que el puntero de pila de 64 bits no sobrevive al cruce, algo que cualquier
thunk futuro debe manejar. Si el probe pasa en consola, los juegos de 32 bits
corrían de forma nativa mediante ABI thunking estilo WoW64. El probe se
ejecutó y **falló**: todas las operaciones LDT devuelven `EINVAL`, también
con privilegio elevado y con una operación de control que sí funciona, y el
sysctl que dimensiona la tabla no existe. No hay ruta nativa para 32 bits en
este firmware.

Alcance decidido: **se soportan 32 y 64 bits**. El código de 64 bits se
ejecuta nativo; el de 32 bits pasa por un traductor JIT de misma ISA, que es
la Fase 4 del roadmap y va deliberadamente después de que un programa de 64
bits funcione de extremo a extremo. Sus prerrequisitos están medidos: una
dirección baja se concede si se pide, así que los punteros del guest pueden
vivir bajo 4 GiB y los operandos de memoria no necesitan reescritura; un
título obtiene 256 MiB contiguos ahí; y `mprotect` a lectura-escritura-
ejecución funciona, así que la caché de código no necesita doble mapeo.
Licencia: LGPL-2.1-or-later. Mientras no haya medida, el loader reporta `native=0`
para una imagen `i386` y el validador rechaza la corrida salvo `--allow-i386`.
El razonamiento completo, junto con el motivo por el que el contrato de
memoria lleva dos alias (escritura y ejecución) desde el primer día, está en
`projects/prospero-win/docs/EXECUTION_MODEL.md`.

La licencia sigue abierta a propósito: es una capa de compatibilidad destinada
a combinarse en runtime con código propietario, el caso que llevó a Wine de
GPL a LGPL. El razonamiento y los candidatos están en
`projects/prospero-win/LICENSING.md`.

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
`docs/XASH3D_CHECKPOINT.md`. Las Fases 0–4 están cerradas en hardware y la Fase
5, platform layer, es la siguiente. El probe de símbolos demuestra
que libc y C++ no son el bloqueo: sólo faltan tres símbolos C triviales; el
trabajo real es `platform/ps5`, `ref_agc` y la integración modular ya habilitada
por el loader PRX propio.

Half-Life requiere datos originales que no forman parte del código del engine
y nunca deben incorporarse a repositorios ni artefactos públicos.
