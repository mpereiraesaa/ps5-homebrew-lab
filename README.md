# homebrew_ps5

Laboratorio privado y reproducible para homebrew nativo de PS5 en firmware
12.02. La implementación gráfica canónica es ahora
[`projects/ps5-xash3d`](projects/ps5-xash3d/README.md): el port nativo de
Xash3D (GoldSrc) sobre AGC, con shaders propios `gfx1013`, bifurcado de la demo
pública [`projects/ps5-agc-gears`](projects/ps5-agc-gears/README.md), que queda
congelada como demo Gears.

## Estado actual

`ps5-xash3d` renderiza el mapa `c1a0` con texturas base, lightmap dinámico,
mipmaps con filtrado trilineal/anisotrópico, alpha-test y cielo, con noclip
físico por DualSense y dos frames en vuelo. Las Fases 0–4 del plan están
cerradas en hardware con fences GPU, tokens VideoOut y guardas exactos, cero
errores del renderer y telemetría TCP estructurada. La Fase 4, estados de
render GoldSrc, está completa. Sus ocho gates ordenados
probaron pipelines, matriz de estados, viewport/scissor, 2D, iluminación BSP,
sprites/partículas, Studio animado, brush entities y visibilidad; una corrida
integrada final mantuvo agua, vidrio, efectos, Studio y HUD durante 60.000
frames con ownership exacto y cero errores.

La Fase 5 está completa: engine bootstrap, filesystem completo, ScePad,
SceAudioOut, memoria directa, threads/reloj, telemetría GPU/flip y los tres
shims propios ya están cerrados. El backend de input consume lotes
cronológicos de hasta 64 registros y traduce el DualSense a los eventos
canónicos de Xash3D; la
corrida aceptada probó movimiento, cámara, salto, agacharse, usar y disparar,
sin errores y con teardown exacto. El backend de audio saca PCM por
`libSceAudioOut` desde un ring productor/consumidor con un resampler continuo
147/160 y un worker que es el único dueño del handle: la corrida aceptada
transportó 1,5 s de PCM a 44,1 kHz como 282 grains completos de 48 kHz, con
hash coincidente, cero underruns y confirmación audible del operador. Todo el
allocator C/C++ del engine usa ahora una única raíz de 128 MiB sobre direct
memory; cuatro recursos GPU representativos probaron generaciones, retiro y
reclamación exactos, con guardas intactos y el arena vacío al terminar. El
gate de threads probó dos workers distintos con ownership `join`/`detach`
exacto, 32.768 incrementos protegidos, 8.192 lecturas monotónicas sin regresión
y 128 muestras `nanosleep`/`usleep` sin errores ni despertares anticipados. El
gate de telemetría correlacionó 60.000 submits, timestamps GPU end-of-pipe,
fences y eventos VideoOut exactos sin gaps ni regresiones. El cierre final
retuvo `__assert`, `getpwuid` y `dladdr` como definiciones locales del port,
probó sus contratos en FW 12.02 y cargó `c1a0` sin errores. La Fase 6 está
completa: loader híbrido, `filesystem_stdio.prx`, servidor HLSDK, MainUI,
cliente GoldSrc y `ref_agc` funcionan como módulos propios. La
combinación dinámica montó las 4.823
entradas, probó listing, lectura grande y path con case mixto; el servidor
publicó 251 exports del engine, ejecutó sus constructores C++, cruzó la ABI en
ambos sentidos, levantó `c1a0` y se descargó antes que el filesystem con
ownership exacto. MainUI publicó sus 16 callbacks base y 12 extendidos, se
activó y redibujó 5.127 veces sobre un framebuffer software no negro. El
cliente pasó interface 7 y ambos sentidos de la ABI sobre `c1a0`; el gate
final enlazó RefAPI 18 con el backend AGC, presentó 600 frames con hashes GPU
no nulos y descargó los cinco PRXs exactamente. La Fase 7 está activa: el
primer checkpoint ya extrae el mundo `c1a0` vivo del engine y somete 17.245
vértices, 29.565 índices y 3.695 superficies mediante AGC, con las 164
referencias de textura resueltas y teardown exacto. El A/B de FW 12.02 aisló
un handoff de scheduler de 10 ms después de inicializar la cámara viva. El
checkpoint siguiente construye el atlas de lightmaps desde los lightstyles del
engine, lo aloja en direct memory y enlaza los pipelines AGC nativos: 3.695
draws lightmapped y 1.075 frames emparejados pasaron con imagen visible,
ownership exacto y cero errores. El checkpoint fusionado siguiente añade el
skybox vivo de seis caras y el warp turbulento clásico dirigido por el tiempo
del engine, sin emulación OpenGL: 1.616 frames emparejados probaron 158
superficies sky, seis draws de cubo y 35 draws turbulentos, con ocho recursos
reclamados y cero errores. El checkpoint 2D traduce las listas vivas en orden
de fuente: 61.316 quads formaron 610 batches nativos durante 1.044 frames
emparejados. El checkpoint fusionado más reciente presenta MainUI mediante AGC
durante 223 frames y luego encola `map c1a0` dentro del mismo proceso: el mapa
aparece en el serial 224, con vídeo directo de ambos estados, ocho recursos
reclamados y teardown exacto. El trabajo inmediato es traducir entidades y
viewmodel antes de la comparación de cámara fija, gameplay, rendimiento,
transiciones, soaks y release.

La identidad de consola también está separada y validada: Xash3D usa
`PPSA99996` y la demo Gears congelada conserva `PPSA99997`. El host histórico
`PPSA99998` fue desinstalado de la consola y no deja rutas ni filas vivas en su
base de aplicaciones.

`ps5-agc-gears` dibuja tres engranajes 3D animados con depth, iluminación,
doble buffer y dos frames realmente en vuelo; pasó soaks de 10.000 y 60.000
frames y es el origen del renderer.

El repo público construye sin depender de dumps, Ghidra, juegos ni rutas
privadas del laboratorio. `main` está protegida; todo desarrollo nuevo ocurre
en branches/worktrees y entra mediante pull request.

El laboratorio también puede observar la consola directamente mediante Remote
Play. `tools/ps5_remoteplay.py` reutiliza la entrada Chiaki ya registrada para
abrir el stream CLI y tomar capturas o grabaciones; el flujo normal no repite
pairing, no abre el cliente principal y no depende del foco ni de la cámara del
operador.

## Estructura

- `projects/ps5-xash3d/`: port Xash3D sobre AGC, implementación canónica.
- `projects/ps5-agc-gears/`: demo Gears pública, congelada.
- `projects/logging_server/`: infraestructura de telemetría `ps5log/1`.
- `tools/ps5_remoteplay.py`: streaming y captura visual mediante Chiaki.
- `legacy/`: apps por stages y probes históricos; evidencia opt-in, nunca base
  para una nueva implementación.
- `research/gpu/`: análisis, capturas y dumps privados; jamás se publica.
- `sdk/agc/`: primera API AGC sanitizada conservada como referencia del lab.
- `third_party/`: toolchains y fuentes públicas fijadas localmente.
- `docs/CURRENT.md`: frontera vigente y flujo de desarrollo.

## Flujo normal

```sh
make check
```

Ese gate ejecuta, en orden, los contratos del port canónico `ps5-xash3d`, la
demo Gears congelada, la suite independiente del servidor de telemetría y los
contratos del helper Remote Play. Para construir la aplicación se delega
igualmente al repo canónico:

```sh
make native-release AMDLLPC=/ruta/a/amdllpc LLVM_READELF=/ruta/a/llvm-readelf
```

Los stages A–I y el código de `PPSA99998` permanecen sólo como historia
reproducible bajo `legacy/` y `research/`; `PPSA99998` no permanece instalado
en la consola. hbldr/elfldr y ShadowMountPlus siguen siendo infraestructura del
laboratorio, no la implementación del port.

En un clon nuevo, inicializar el renderer público fijado antes de ejecutar los
gates:

```sh
git submodule update --init
make check
```
