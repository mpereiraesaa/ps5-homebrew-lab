# PPSA99998 — aplicación AGC nativa

Aplicación de investigación nativa desplegada con ShadowMountPlus. Su variante
Stage E es el primer renderer propio confirmado: presenta un triángulo verde
centrado sobre morado usando shaders `gfx1013`, AGC y VideoOut.

## Build vigente

```sh
./build_stage_e.sh
python3 verify_stage_e.py
```

Salida conservada: `dist-stage-e/PPSA99998/eboot.bin`.

El gate recompila shaders propios con LLPC/PAL, valida símbolos y metadata
`gfx1013`, construye el fSELF, comprueba imports/estructura y ejecuta las pruebas
host del compositor. No usa ni empaqueta material propietario.

## Resultado hardware

- DCB 122 DWORD; pipeline 84 CX / 12 SH / 3 UC.
- Indirectos y draw emitidos por builders nativos de FW 12.02.
- `SubmitDcb=0`, fence cero y evento VideoOut exacto.
- 285.120 píxeles modificados; guardas y recovery intactos.
- Imagen sostenida 5 s y confirmada visualmente.
- Teardown y cierre exacto correctos.

La captura canónica es
`../../research/gpu/captures/agc-stage-e-centered-triangle-runtime.json`; el
contrato completo está en `../../research/gpu/STAGE_E_TRIANGLE.md`.

## Despliegue

Publicar el título completo en `/data/homebrew/PPSA99998`, recargar
ShadowMountPlus sin otra BigApp y lanzar por identidad exacta. Tras modificar
`eboot.bin` siempre se requiere refresh de ShadowMountPlus. El cleanup normal
cierra sólo `PPSA99998`; no requiere reiniciar la consola.

Los directorios y scripts Stage B–D permanecen como reproducción histórica.
`FAKE00000` no forma parte de esta ruta.
