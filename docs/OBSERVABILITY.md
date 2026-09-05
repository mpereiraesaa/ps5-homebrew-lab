# Logging y observabilidad AGC

`ps5log/1` sobre TCP es el contrato vigente para la telemetría de `PPSA99998`.
Escribir logs en USB, `/download0` o cualquier otro filesystem de la consola
está deprecado. Cliente, servidor e integración nativa están validados.

```text
PPSA99998 (/app0/dev.conf)
    -> ps5log client: HELLO + registros secuenciados + BYE
    -> TCP 9300
    -> ps5logd en el PC
       -> vista en vivo
       -> projects/logging_server/runs/<run>.log
       -> projects/logging_server/runs/<run>.json
       -> copia inmutable en research/gpu/captures/runtime/
```

No hay mount, bind, FTP, sondeo de archivos de la consola, `fsync` ni fallback
silencioso. La configuración privada se empaqueta como `/app0/dev.conf`; el
binario no contiene una IP y el repositorio publicable excluye ese archivo.

Los títulos nativos usan el backend independiente
`projects/logging_server/client/ps5log_ps5_net.c`: los handles de red pasan por
`sceNet*` y `sceNetEpoll*`; el descriptor usado para leer `/app0/dev.conf`
permanece en libc y nunca se confunde con un socket.

El smoke nativo de FW 12.02 probó HELLO, ocho registros estructurados y BYE sin
gaps. El rechazo anterior era un layout RELRO incorrecto: el linker ubicaba el
segmento desde `.got` en vez de `.data.rel.ro`. El arreglo portado exige además
congruencia de 16 KiB para cada `PT_LOAD`. `PS5_NO_LOG=1` queda como control A/B.

## Arranque canónico

En el PC, mantener el servidor activo:

```sh
cd projects/logging_server
make check
make serve
```

En otra terminal, después del build/deploy mediante ShadowMountPlus:

```sh
python3 tools/agc_net_monitor.py --host "$PS5_HOST" --launch \
  --artifact legacy/apps/agc-native-sce/dist-stage-g/PPSA99998/eboot.bin
```

Añadir `--close-on-safe` sólo cuando se quiera cerrar automáticamente el título.
El monitor no arranca un servidor implícito: comprueba que `ps5logd` escucha y
falla antes de lanzar si no está disponible.

## Evidencia aceptable

Una ejecución sólo es atribuible y completa cuando el manifiesto de `ps5logd`
demuestra simultáneamente:

1. `protocol=ps5log/1`, `transport=tcp` y HELLO presente.
2. Identidad exacta `PPSA99998/agc-native-sce`.
3. Boot token de HELLO igual a `LOG_BOOT_MONOTONIC_NS`.
4. Registros estructurados, `raw_lines=0`, sin oversized records.
5. `gaps=[]`, BYE presente y su `seq` igual al último registro.
6. Tamaño y SHA-256 del transcript iguales al manifiesto.
7. El clasificador de la fase prueba fence GPU, evento VideoOut y teardown en
   el orden requerido.

El monitor copia transcript y manifiesto a `research/gpu/captures/runtime/` y
añade un capture manifest con el hash del artefacto desplegado. Una observación
visual sin estos artefactos no cuenta como evidencia reproducible.

## Semántica de fallos

- La conexión inicial está acotada a 500 ms y cada send a 200 ms.
- Si la red no está disponible, el logger se desactiva y la transacción GPU
  continúa; no intenta escribir un archivo alternativo.
- Si la red cae durante un run, aparecen gaps o falta BYE: nunca se autoriza
  cierre automático ni reutilización inferida.
- Nunca se reconecta entre submit y completion. Un eventual reconnect sólo
  puede ocurrir tras fence y evento exactos.
- Un park ambiguo envía su marcador y cierra la sesión con
  `reason=parked-retain`; `clean=true` no anula la decisión de retener del
  clasificador.

## Política del frame loop

Los tiempos de compose, GPU y VideoOut se acumulan en memoria. Se transmiten
el frame inicial, cada 60 frames, todos los errores y el resumen final. Los
cambios críticos de ownership siguen siendo inmediatos. Nunca se genera un
registro por frame sólo para telemetría.

## Gate permanente

Antes de cualquier build o deploy AGC:

```sh
make agc-check
```

Este gate ejecuta los tests completos de `logging_server`, validación de
manifiestos/tamper, cierre fail-closed, clasificadores y todos los contratos del
renderer. También impide reintroducir rutas USB, `/download0`, `nmount` o
`fsync` en la aplicación activa.

La especificación del transporte vive en
`projects/logging_server/PROTOCOL.md`; su integración de laboratorio está en
`projects/logging_server/INTEGRATION.md`.

Los experimentos anteriores y por qué no forman parte del flujo vigente están
inventariados en `research/gpu/LEGACY_FILESYSTEM_TELEMETRY.md`.
