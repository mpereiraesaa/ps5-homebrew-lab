# Stage E — DCB offline mínimo

Alcance: PS5 FW 12.02. Este artefacto no se despliega ni se ejecuta. No abre
VideoOut, no crea una cola y no importa ni llama submit. Su finalidad es cerrar
la composición CPU antes del primer experimento GPU con shaders propios.

## Entradas retenidas

El caller conserva durante toda la futura transacción:

- header y código de los shaders pre-raster y pixel ya construidos;
- 34 pares CX y tres pares UC producidos por `sceAgcLinkShaders`;
- seis pares SH de cada shader después de `sceAgcCreateShader`;
- 16 defaults de MRT0 obtenidos para el firmware activo;
- command buffer, backbuffer y fence dentro de mappings GPU válidos.

Los defaults son una entrada explícita. No se incrustan tablas de Sony ni
material procedente de juegos. `stage_e_build_color_target` valida los 16 IDs,
exige dirección no nula alineada a 0x20000 y dimensiones 1..0x3fff, conserva
los bits dependientes del firmware y deriva los campos SDR de dirección,
formato/tiling, dimensiones y control.

La transición al runtime dispone además de
`stage_e_select_runtime_color_defaults()`. El selector busca la clave semántica
pública MRT0 `0x38e92c91` en el objeto devuelto a la propia aplicación por
`sceAgcGetRegisterDefaults()`, exige el perfil observado de FW 12.02
(`count=137`, banco CX, índice único dentro de 84 entradas), y los 16 offsets
esperados. Cualquier discrepancia aborta antes de construir el DCB. Su prueba
host cubre count, banco, índice, duplicados, offsets y canarios.

## Registros

`stage_e_build_pipeline_registers` produce exactamente:

- CX: 16 pares de MRT0 + 15 pares de viewport/scissor + 34 pares enlazados;
- SH: seis pares pre-raster + seis pares pixel;
- UC: tres pares enlazados, incluido el tipo de primitiva.

La transformación de viewport cubre escala/offset XY, rango Z, guard bands,
screen scissor y modo de raster. Width y height son parámetros validados; no
se fija 4K como supuesto universal.

## Stream

El orden único es:

```text
WaitSafeForRendering(handle, buffer)
SetCxRegistersIndirect(65)
SetUcRegistersIndirect(3)
SetShRegistersIndirect(12)
DrawIndexAuto(3, draw_modifier)
SetFlip(handle, buffer, mode, flip_arg)
RELEASE_MEM(fence = 0)
```

Los tres arrays indirectos deben estar alineados a ocho bytes, ser disjuntos
entre sí y no solaparse con el command buffer. El stream reserva 64 DWORD para
SetFlip. Como ese builder efectúa una reserva EOP antes de serializar el
packet, `transaction_started` se fija antes del callback; cualquier fallo desde
ese punto exige retener los recursos. El cursor retornado se valida como entero,
incluyendo alineación, overflow, rango reservado y espacio para la fence.

El callback existe deliberadamente: en una futura integración será el builder
oficial ya validado. El test usa un mock determinista y nunca toca VideoOut.

## Evidencia reproducible

```sh
bash legacy/apps/agc-native-sce/build_stage_e_offline.sh
```

El script compila cuatro tests host con `-Werror -pedantic`, compila los mismos
builders con el toolchain PS5, enlaza y firma `PPSA99998`, inspecciona la
integridad del SELF y rechaza cualquier import AGC, VideoOut, submit o acceso a
procesos. El orden `CX -> UC -> SH` coincide con el camino de render funcional y
auditable de ProsperoTV. Esto demuestra una diferencia semántica respecto al
Stage E anterior; todavía no demuestra que el orden sea obligatorio ni que
explique por sí solo el fallo dentro de submit. Esa hipótesis sólo se considerará
confirmada mediante ejecución controlada.

El DCB normalizado tiene FNV-1a64 `0x39a2eb5496ae4d8a`; el plan de
registros sintético tiene `0x375efbf9fcb713aa`. Los valores sintéticos sólo
prueban integración y reproducibilidad; no sustituyen los defaults del runtime.

La prueba machine-readable está en
`captures/agc-stage-e-offline-proof.json`. Sus flags `deployed`, `submitted` y
`gpu_executed` permanecen en falso.
