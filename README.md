# homebrew_ps5

Laboratorio privado y reproducible para homebrew nativo de PS5 en firmware
12.02. La implementación gráfica canónica es ahora el repositorio público
[`projects/ps5-agc-gears`](projects/ps5-agc-gears/README.md): una demo Gears
continua, acelerada por AGC, con shaders propios `gfx1013`.

## Estado actual

`ps5-agc-gears` dibuja tres engranajes 3D animados con depth, iluminación,
doble buffer y dos frames realmente en vuelo. El artefacto independiente pasó
soaks de 10.000 y 60.000 frames en hardware con fences GPU, tokens VideoOut y
guardas exactos, cero errores del renderer y telemetría TCP estructurada.

El repo público construye sin depender de dumps, Ghidra, juegos ni rutas
privadas del laboratorio. `main` está protegida; todo desarrollo nuevo ocurre
en branches/worktrees y entra mediante pull request.

## Estructura

- `projects/ps5-agc-gears/`: producto gráfico canónico y publicable.
- `projects/logging_server/`: infraestructura de telemetría `ps5log/1`.
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
