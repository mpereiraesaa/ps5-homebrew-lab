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
físico por DualSense y dos frames en vuelo. Las Fases 0–3 del plan pasaron
soaks de 60.000 frames en hardware con fences GPU, tokens VideoOut y guardas
exactos, cero errores del renderer y telemetría TCP estructurada. La Fase 4,
estados de render GoldSrc, es la siguiente.

`ps5-agc-gears` dibuja tres engranajes 3D animados con depth, iluminación,
doble buffer y dos frames realmente en vuelo; pasó soaks de 10.000 y 60.000
frames y es el origen del renderer.

El repo público construye sin depender de dumps, Ghidra, juegos ni rutas
privadas del laboratorio. `main` está protegida; todo desarrollo nuevo ocurre
en branches/worktrees y entra mediante pull request.

El laboratorio también puede observar la consola directamente mediante Remote
Play: `headless-linkdev` realiza el pairing por `elfldr`, Chiaki muestra el
stream y `tools/ps5_remoteplay.py` toma capturas o grabaciones sin depender de
la cámara del operador.

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

Ese gate ejecuta los contratos del repo Gears y la suite independiente del
servidor de telemetría. Para construir la aplicación se delega igualmente al
repo canónico:

```sh
make native-release AMDLLPC=/ruta/a/amdllpc LLVM_READELF=/ruta/a/llvm-readelf
```

Los stages A–I, `PPSA99998`, hbldr/elfldr y ShadowMountPlus permanecen sólo
como historia reproducible bajo `legacy/` y `research/`. No son el flujo de
desarrollo vigente.

En un clon nuevo, inicializar el renderer público fijado antes de ejecutar los
gates:

```sh
git submodule update --init
make check
```
