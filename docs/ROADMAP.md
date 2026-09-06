# Roadmap

Última reconciliación: 2026-09-06.

> Este documento conserva el roadmap histórico que produjo Gears. El roadmap
> vigente está en `projects/ps5-agc-gears/docs/ROADMAP.md` y la política del lab
> en `CURRENT.md`. El plan de evolución hacia GoldSrc está en
> `XASH3D_PS5_PLAN.html` y su checkpoint ejecutable en
> `XASH3D_CHECKPOINT.md`.

## Completado

- [x] Aplicación nativa `PPSA99998` y despliegue ShadowMountPlus.
- [x] AGC init, memoria directa propia y BatchMap.
- [x] DCB propio consumido: DMA, fence y cleanup.
- [x] VideoOut con doble buffer, `SetFlip` y evento exacto.
- [x] Clear visible de backbuffer completo mediante DMA.
- [x] Toolchain LLPC/PAL reproducible para `gfx1013`.
- [x] Shaders propios, `CreateShader`, `LinkShaders` y metadata CX/UC/SH.
- [x] Builders nativos de indirectos y draw con contrato de cinco DWORD.
- [x] Primer draw acelerado inequívoco: triángulo verde centrado sobre morado,
  285.120 píxeles, fence/evento/guardas/cleanup correctos.

## Objetivo siguiente: validación escalonada en hardware

1. [x] Stage G/21: Cube con DSV D32 completo, clear DMA sincronizado y depth
   desactivado. La tabla DSV en `shader + 0x3e00` produjo submit/fence/evento,
   cubo 3D centrado, efecto GPU verificable y cleanup completos.
2. [x] Stage G/22: el cambio exclusivo del count activó
   `DB_DEPTH_CONTROL=LESS_EQUAL`; completó submit/fence/evento/cleanup y el
   operador observó tres caras del cubo con oclusión visual coherente.
   Stage G/23 cerró además la prueba semántica: superficies coincidentes,
   cercana brillante primero y lejana oscura después, dieron oscuro con 21
   registros y brillante con 22. El operador confirmó una diferencia fuerte.
3. [x] Stage H: un solo frame con tres mallas, transformaciones independientes,
   iluminación, depth y tres `DrawIndexAuto`; ejecución y apariencia validadas.
4. [x] Stage I: 300 frames animados con dos pipelines/backbuffers, tokens
   monotónicos, clear color/depth, guardas y telemetría TCP estructurada.
   Completó 300/300, sin errores ni corrupción de guardas, con fence GPU y
   evento VideoOut exactos en cada frame y teardown limpio.
5. [x] Soaks hardware de 1.000 y 10.000 frames: conteos exactos, cero errores,
   guardas intactas, ownership GPU/VideoOut y teardown limpio.
6. [x] Dos frames realmente en vuelo, con command buffers y fences por slot,
   retiro por fence+token exacto y soak hardware 10K a 59,94 fps.
7. [x] Clear de color por triángulo fullscreen, sin DMA, validado en verde y
   negro y con soak hardware 10K completo.
8. [x] Extraer el backend nativo publicable sin constantes o material privado;
   publicado como `mpereiraesaa/ps5-agc-gears`.

## Después

- Varios pipelines y buffers de vértices/índices.
- Texturas, samplers y upload de recursos.
- Integración de entrada/audio y primer source port AOT.

## Reglas permanentes

- Target real: `gfx1013`; `build-gfx1030` es sólo un nombre histórico de caché.
- No publicar blobs, dumps ni shaders propietarios.
- Usar juegos comerciales únicamente como oráculo local autorizado y
  sanitizar toda evidencia.
- `SubmitDcb=0` no basta: exigir resultado, completion y teardown.
- Preferir cierre exacto; reiniciar sólo cuando el estado no sea recuperable.
- Usar `ps5log/1` TCP hacia `logging_server`; USB y `/download0` están
  deprecados. `PS5_NO_LOG=1` se reserva para controles A/B.
- Ninguna fase nueva se considerará cerrada sin
  HELLO/BYE, secuencia sin gaps, manifiesto/hash y clasificación fail-closed.
- Stage G exige `make agc-stage-g-check`: validar primero los 21 registros de
  DSV sin `DB_DEPTH_CONTROL`, y sólo después habilitar el par 22 en una
  iteración independiente con fence y evento VideoOut exacto.
- Todo span usado por un paquete de registros indirecto debe pertenecer por
  completo a una arena directa declarada GPU-visible; stack y heap ordinario
  son precondiciones inválidas aunque la composición CPU tenga éxito.
- Stage H puede construirse offline con `make agc-stage-h-build`, pero no se
  despliega antes de aprobar ambos gates Stage G; su existencia no constituye
  evidencia de tres draws ni depth en hardware.
- Stage I se construye con `make agc-stage-i-build` y ya está validado en
  hardware tras G/H. El runner conserva ownership exacto y mantiene dos frames
  realmente en vuelo; el soak 10K sostiene la cadencia VideoOut de ~59,94 fps.
