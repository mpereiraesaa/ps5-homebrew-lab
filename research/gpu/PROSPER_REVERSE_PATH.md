# Prosper como oráculo inverso para AGC

Revisión inicial: 2026-09-04. Fuente pública examinada:
`mattias800/prosper`, commit
`df1bbae324714bbfc2c0b1a2743c2ab8c1d60bb6` (copia temporal, no vendorizada).

## Conclusión

Prosper es muy útil para esta investigación, pero no es un SDK AGC ni un
generador directamente reutilizable de command buffers nativos. Su valor se
divide en dos:

1. **Oráculo semántico:** documenta qué significa una operación AGC, qué estado
   persiste entre submits, cómo se ordenan DMA, waits, writes, fences, EOP y
   presentación, y cómo los registros y shaders RDNA2 terminan en un pipeline.
2. **Catálogo ABI/NID contrastable:** contiene firmas reconstruidas, layouts de
   objetos y callsites observados en distintos engines y revisiones de SDK.

Su limitación principal para nosotros es igualmente importante: varias
funciones HLE no emiten el PM4 de hardware. Prosper serializa operaciones en
paquetes privados `IT_NOP + R_*` y después su propio decoder los interpreta.
Esos DWORD **no se deben enviar a la GPU de PS5**.

## Coincidencias fuertes con FW 12.02

| Elemento | Prosper | Evidencia local | Lectura |
|---|---|---|---|
| Submit gráfico | NID `UglJIZjGssM` | mismo NID, driver `+0x2960` | identidad confirmada |
| Descriptor | `{uint32_t *addr; uint32_t dw_num; pad[4]}` | prefijo idéntico en `submit_info` | ABI pública de 16 bytes confirmada |
| DCB | ring de DWORD con `bottom/top/cursor_up/cursor_down`, callback y reserva | nuestros builders escriben streams DWORD | modelo útil para el writer futuro |
| DMA | `sceAgcDcbDmaData`, NID `WmAc2MEj6Io`, 7 DWORD | mismo NID y tamaño 7 DWORD | identidad/tamaño confirmados |
| Inicialización | `23LRUSvYu1M` aparece como init de dispositivo/contexto | 0U lo llamó con versión 8 y alteró el flag de cola | refuerza que 0U alcanzó init real, no submit |
| Estado | registros gráficos persisten entre submits; draws se consumen por submit | pendiente de probar en hardware | hipótesis prioritaria para un clear/draw |

`oFb2hMcoJa4`, el setter exacto del bit `0x20000` localizado en nuestro
AgcDriver FW 12.02, no aparece en el snapshot revisado de Prosper. Esto no
contradice el hallazgo local: Prosper reemplaza la parte nativa de driver/cola
y no necesita reproducir toda su inicialización interna.

## Diferencias que no se deben mezclar

### Submit

Prosper recibe directamente un puntero al `Packet`, valida `addr` y `dw_num`,
serializa el fold y ejecuta el stream sin pasar por el kernel gráfico de PS5.
Esto confirma el contenedor ABI, pero no explica:

- creación/publicación de la cola nativa;
- las tablas fijas de `libSceAgc` en `0xfe0040000`;
- traducción de VA y registro de memoria ante el driver/kernel;
- por qué 0R/0S obtuvieron retorno cero sin ejecución visible.

### DMA_DATA y RELEASE_MEM

Prosper conoce los opcodes de hardware `DMA_DATA=0x50` y
`RELEASE_MEM=0x49`, pero sus builders HLE actuales codifican estas operaciones
como sub-operaciones privadas de `IT_NOP`:

- `R_DMA_DATA=0x19`;
- `R_RELEASE_MEM=0x18`.

El decoder y el ejecutor consumen ese dialecto privado. En cambio, nuestros
streams de FW 12.02 usan los headers nativos observados:

- `0xc0055000` para DMA_DATA de 7 DWORD;
- `0xc0064900` para RELEASE_MEM de 8 DWORD.

Usaremos Prosper para validar **la intención y el orden** de estas operaciones,
no sus bytes.

### Completion

Prosper realiza el fold sincrónicamente en CPU, materializa las escrituras y
luego publica EOP. En hardware la GPU debe consumir la cola, completar los
efectos de memoria y sólo después hacer observable el evento/fence. Su modelo
sí aporta invariantes valiosos:

1. `WAIT_REG_MEM` bloquea su cola; no es un simple polling decorativo.
2. Una señal EOP no puede adelantarse a `RELEASE_MEM`, `WRITE_DATA` o DMA.
3. Estado gráfico y colas async necesitan contextos separados.
4. El tamaño lógico exacto del stream importa: ejecutar una cola stale puede
   repetir escrituras hacia direcciones ya reutilizadas.

## Qué podemos reutilizar de forma segura

- Tabla NID/nombre/signatura como índice de investigación, siempre confirmada
  contra los módulos de nuestro FW.
- Layout DCB y estrategia de callback de buffer lleno como diseño de un writer.
- Tablas de registros/defaults como candidatos que deben verificarse contra
  `libSceAgc` 12.02 antes de usarse.
- Decoder de shaders AGC/RDNA2, layout de shaders y traducción de descriptores
  como documentación ejecutable.
- Modelo de estado gráfico para enumerar el conjunto mínimo de registros de un
  clear o triángulo.
- Tests de orden DMA/fence/wait como especificación para nuestros guards.

No se copiará código hasta aclarar la licencia del repositorio raíz: el
snapshot revisado no contiene un archivo de licencia general detectable. Por
ahora sólo se conservan hechos, nombres públicos y conclusiones independientes.

## Integración en nuestra ruta mínima

Prosper ayudó a ordenar estas prioridades. Los tres primeros pasos históricos
ya quedaron completados por Native Label v5:

1. `sceAgcInit` completó el bootstrap nativo.
2. La cola consumió un DCB propio con `SubmitDcb=0`.
3. `DMA_DATA` y el fence posterior produjeron cambios observables y ordenados.
4. Mantener un validador offline dual:
   - dialecto **native-1202**, derivado de nuestros módulos/capturas;
   - semántica **prosper**, usada únicamente para comparar operación y orden.
5. Para el primer frame, completar primero la transacción VideoOut con un
   buffer rellenado por CPU; después contrastar el estado mínimo de render para
   clear o triángulo con register defaults y builders de nuestra revisión.

## Preguntas dirigidas para la segunda pasada

- ¿Qué campos exactos de shader header usa `sceAgcCreateShader` y cuáles son
  estables entre SDK 8 y los títulos observados por Prosper?
- ¿Qué defaults de CX/SH/UC son imprescindibles antes del primer draw?
- ¿Qué secuencia mínima lleva de render target + viewport + shader a
  `DrawIndexAuto(3)`?
- ¿Qué parte del SetFlip es estado VideoOut y qué parte es sólo orden EOP?
- ¿Podemos alimentar capturas propias sanitizadas a un decoder separado sin
  adoptar los paquetes privados de Prosper?

## Archivos upstream de mayor valor

- `prosper/src/hle/graphics/hle_agc.cpp`
- `prosper/src/gpu/pm4/pm4_decode.{hpp,cpp}`
- `prosper/src/gpu/pm4/command_processor.cpp`
- `prosper/src/gpu/state/render_state.cpp`
- `prosper/src/gpu/state/vk_translate.cpp`
- `prosper/src/gpu/agc/agc_shader_layout.cpp`
- `prosper/src/gpu/recompiler/rdna2_*`
- `prosper/docs/GRAPHICS.md`
- `prosper/docs/AGC_TRACE.md`
