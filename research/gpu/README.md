# Banco de investigación GPU

Este directorio contiene herramientas y metadatos reproducibles. Los dumps,
capturas, proyectos Ghidra y sesiones live se ignoran deliberadamente: pueden
ser grandes, depender del firmware o contener material que no debe versionarse.

El mapa específico del descriptor de backbuffer está en
[`AGC_RENDER_TARGET_DESCRIPTOR.md`](AGC_RENDER_TARGET_DESCRIPTOR.md).
La composición host-only del primer stream acotado está descrita en
[`AGC_DMA_DATA.md`](AGC_DMA_DATA.md) y su fence en
[`AGC_FENCE_ANALYSIS.md`](AGC_FENCE_ANALYSIS.md).
La progresión operativa desde el label privado hasta clear y triángulo está en
[`AGC_PRESENTATION_STAGING.md`](AGC_PRESENTATION_STAGING.md); su gate se
regenera con `python3 research/gpu/tools/verify_presentation_staging.py`.
El contraste con la capa de compatibilidad AGC→Vulkan Prosper, incluidos los
límites entre su ABI observada y sus paquetes PM4 privados, está en
[`PROSPER_REVERSE_PATH.md`](PROSPER_REVERSE_PATH.md).
El contraste del ABI de memoria extendida con Prosperity y la razón por la que
se usó BatchMap en la prueba de visibilidad ya completada está en
[`PROSPERITY_MEMORY_PATH.md`](PROSPERITY_MEMORY_PATH.md).

El estado experimental vigente es Stage E completado. Un homebrew nativo creó
y enlazó shaders propios `gfx1013`, emitió los bloques CX/UC/SH y draw mediante
builders nativos, presentó un triángulo verde centrado sobre morado y completó
fence, evento y teardown. Cambiaron exactamente 285.120 píxeles. La evidencia
canónica está en `captures/agc-stage-e-centered-triangle-runtime.json`.

`AGC_PRESENTATION_STAGING.md` y las capturas de intentos anteriores son historia
experimental, no instrucciones vigentes. El plan actual vive en
`../../docs/ROADMAP.md` y el contrato final en `STAGE_E_TRIANGLE.md`.

## Flujo

1. Capturar inventario read-only con `tools/capture_inventory.py`.
2. Guardar el JSON resultante bajo `sessions/` (ignorado por git).
3. Seleccionar módulos por nombre y contexto; no volcar regiones anónimas a
   ciegas.
4. Calcular SHA-256 de cada dump y crear un manifiesto desde
   `templates/module-manifest.json`.
5. Analizar una copia en Ghidra y documentar cada función con
   `templates/function-record.md`.

Los dumps runtime no incluyen necesariamente la cabecera ELF. Antes de
importarlos, envolverlos en un ELF de análisis con bases y permisos del
manifiesto:

```sh
python3 research/gpu/tools/rebuild_analysis_elf.py \
  research/gpu/dumps/module.bin research/gpu/dumps/module.bin.json \
  research/gpu/ghidra/module.analysis.elf
```

El contenedor es sólo una representación local para análisis: no debe cargarse
ni ejecutarse en la consola.

Ejemplo:

```sh
python3 research/gpu/tools/capture_inventory.py \
  --host "$PS5_HOST" --label menu \
  --output research/gpu/sessions/menu.json
```

La herramienta sólo enumera procesos y mapas. No escribe memoria, no adjunta el
debugger y no ejecuta funciones remotas.
