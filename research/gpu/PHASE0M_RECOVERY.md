# Recuperación conservadora de la fase 0M

Este procedimiento sólo aplica al futuro primer submit 0M. El ELF sigue sin
estar aprobado, desplegado ni disponible desde el supervisor.

## Regla principal

Después de entrar en `SubmitDcb`, sólo la secuencia registrada
`fence=0 -> target=0 -> exit normal` demuestra que la GPU terminó y que el
mapping puede liberarse. Un retorno de submit, la salud de los servicios o una
UI todavía fluida no sustituyen esa evidencia.

## Estados del guard

| Estado | Cierre automático | Interpretación |
|---|---:|---|
| `pre_submit_exit` | sí | Falló y salió antes de entrar al submit. |
| `gpu_complete` | sí | Fence y target llegaron a cero y hubo exit normal. |
| `parked` | no | El proceso conserva driver y mapping deliberadamente. |
| `unknown_retain` | no | Log truncado/activo; completion no demostrada. |
| `not_started` | no | Dentro de una ejecución esperada, log vacío es ambiguo. |

## Respuesta automática ante `parked`, `unknown_retain` o `not_started`

La automatización debe limitarse a:

1. registrar el estado y detener la secuencia;
2. comprobar sólo la disponibilidad de los cuatro puertos, sin attach;
3. dejar `FAKE00000`, AgcDriver y la memoria directa vivos;
4. no lanzar ningún título o payload adicional.

Quedan prohibidos `Close Game`, kill, unload, `munmap`, release, nuevos submits,
reintentos del probe y entrada en Rest Mode. El hecho de que ps5debug, FTP,
shsrv o elfldr respondan no cambia esta regla.

## Recuperación con operador presente

Si 0M queda aparcado, no se intenta recuperación remota automática. Con el
operador despierto y la UI del sistema disponible, se realiza un reinicio
completo y controlado de la consola desde el menú de alimentación; no se cierra
sólo `FAKE00000` y no se usa Rest Mode. Tras volver a arrancar, no se reanuda
ningún probe hasta restaurar explícitamente jailbreak/servicios y pasar dos
health checks separados.

Si la UI no responde, la sesión se considera detenida y requiere decisión
manual en presencia de la consola. No se encadenan comandos remotos ni se
automatiza un apagado forzado.

## Verificación local

```sh
python3 -m unittest discover -s research/gpu/tools -p 'test_phase0m_guard.py' -v
python3 research/gpu/tools/phase0m_guard.py /ruta/a/log
```

El segundo comando devuelve código 2 para todo estado que exige conservar los
recursos y detener la automatización.
