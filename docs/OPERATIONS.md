# Operaciones de desarrollo

> Las instrucciones Stage A–I de este documento son históricas. Para el flujo
> vigente usar `../Makefile`, `CURRENT.md` y
> `../projects/ps5-agc-gears/docs/DEVELOPMENT.md`.

## Servicios esperados

- FTP anónimo `2121`, `shsrv` `2323`, `elfldr` `9021` y `ps5debug`.
- Pasar la consola con `--host`; no fijar aquí IP ni credenciales.

## Ruta AGC histórica

```text
build auditado -> /data/homebrew/PPSA99998
ShadowMountPlus -> mount/registro
PPSA99998 -> sceAgcInit -> BatchMap -> SubmitDcb -> fence -> cleanup
```

`legacy/apps/agc-native-sce` produce el executable nativo. No sustituir archivos bajo
`/system_ex/app`; ShadowMountPlus administra el mount desde
`/data/homebrew/PPSA99998`.

Después de cambiar `eboot.bin`, recargar ShadowMountPlus sólo sin BigApp. Para
una ejecución normal usar cierre exacto de `PPSA99998`; no reiniciar por rutina.

El auto-cierre limpio está validado. Después de completion, BYE y teardown
explícito, el runtime usa `_exit(0)` y vuelve al menú sin diálogo. No retornar
desde `main()` en esta ruta: el `exit/atexit` del CRT retiró BigApp pero produjo
“Something went wrong with this game or app” en FW 12.02. El cierre
exacto/cleanup queda para builds históricas estacionadas. Un `park()` por estado
GPU ambiguo continúa siendo fail-closed y no se auto-cierra.

## Comandos actuales

```sh
python3 tools/night_supervisor.py --host "$PS5_HOST" health
python3 tools/night_supervisor.py --host "$PS5_HOST" status
python3 tools/night_supervisor.py --host "$PS5_HOST" launch-xash3d
python3 tools/night_supervisor.py --host "$PS5_HOST" close-xash3d
python3 tools/night_supervisor.py --host "$PS5_HOST" restart-shadowmount
python3 tools/night_supervisor.py --host "$PS5_HOST" --operator-present cleanup
```

`launch-xash3d` and `close-xash3d` are pinned to `PPSA99996`; they refuse an
unexpected BigApp and never target the frozen `PPSA99997` Gears demo. The
historical `PPSA99998` host is uninstalled and is not part of the current
console workflow.

`run-native-label-submit` ya cumplió su pregunta experimental y queda como
historial. Para Stage E usar su build/verificador dedicado:

```sh
cd legacy/apps/agc-native-sce
./build_stage_e.sh
python3 verify_stage_e.py
```

`cleanup` es la recuperación rutinaria autorizada: cierra `PPSA99998` sólo si
su marcador demuestra estado seguro, lanza `PPSA03524`, espera ocho segundos,
lo cierra limpiamente y exige shell más cuatro servicios sanos. Rechaza títulos
inesperados y no adjunta debugger, lee memoria de proceso ni reinicia la consola.

## Protocolo para submits

1. Dos checks de salud y ausencia de BigApp.
2. Build reproducible y SHA-256 esperado.
3. Swap verificado, refresh controlado y lanzamiento por identidad exacta.
4. Log persistente y deadline acotado.
5. Cleanup sólo tras completion inequívoca.
6. Confirmar shell sin BigApp y cuatro servicios saludables.

## Logs de ejecución

El contrato completo está en `OBSERVABILITY.md`. Cliente, servidor y backend
nativo están validados en FW 12.02. El linker debe conservar congruencia de
16 KiB en todos los `PT_LOAD` para evitar el antiguo rechazo `0x80aa001a`.

- `projects/logging_server/dev.conf` es privado y se empaqueta como
  `/app0/dev.conf`; el runtime sólo lee esa ruta. El swap sincroniza y verifica
  tanto `eboot.bin` como este sidecar. Los backups existen sólo durante la
  promoción y se eliminan al completarla; nunca se acumulan dentro del título.
- `ps5logd` escucha TCP 9300 en el PC y conserva transcript más manifiesto.
- El único transporte de archivos canónico es
  `ps5-payload-dev/ftpsrv` en TCP 2121. Para verificar un fSELF, el helper
  desactiva la conversión transparente con `SELF` en esa misma conexión y
  exige tamaño y SHA-256 exactos de los bytes almacenados. `shsrv` en TCP 2323
  sigue siendo un shell/launcher; no es un segundo FTP ni participa en la
  verificación de uploads. El gate `client.prx` verificó así, antes de una
  única promoción transaccional, `eboot.bin`, `filesystem_stdio.prx`,
  `server.prx`, `menu.prx` y `client.prx` por tamaño y SHA-256 exactos.
- El runtime no abre archivos de log, no usa USB/download0 y no necesita que
  el helper modifique mounts.
- El supervisor valida HELLO/BYE, boot token, secuencia sin gaps, tamaño, hash
  y clasificador antes de permitir cierre.
- `--allow-missing-dev-conf` existe únicamente para una build A/B creada con
  `PS5_NO_LOG=1`; el deploy normal rechaza siempre un sidecar ausente.

La vía canónica combina lanzamiento, streaming y captura local:

```sh
python3 tools/agc_net_monitor.py --host "$PS5_HOST" --launch \
  --artifact legacy/apps/agc-native-sce/dist-stage-g/PPSA99998/eboot.bin
```

`SubmitDcb=0` no autoriza liberar memoria. Stage E exige además fence cero,
evento VideoOut del `flip_arg` exacto, guardas intactas, efecto verificable y
teardown completo.

## Ambigüedad y recuperación

- No desmapear, liberar, descargar AGC ni cerrar si la GPU podría retener
  referencias.
- No usar `SIGKILL`, terminar procesos del sistema ni lanzar un segundo submit.
- Conservar log, proceso y mappings para el runbook específico.
- Reiniciar sólo si ese runbook lo exige; normalmente basta cierre exacto.

## ShadowMountPlus

No ofrece remount por título ni socket de control. Su mecanismo soportado es
single-instance: una nueva instancia solicita teardown ordenado y ejecuta
startup sync. El supervisor sólo lo hace sin BigApp y verifica los marcadores.

## Ruta heredada

`hbldr -> FAKE00000` se conserva sólo para probes antiguos de VideoOut,
AudioOut, mando, JIT y memoria diseñados para ese host. No es la ruta AGC actual.
Las fases retiradas 0E–0W/0R no se reintroducen; su evidencia está en
`research/gpu/captures/`.

## Material comercial

Los juegos propios pueden ser referencias privadas read-only. Dumps, blobs,
shaders y fragmentos sustanciales propietarios no entran en el árbol publicable;
sólo hashes, ABI, medidas sanitizadas e implementación independiente.
