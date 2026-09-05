# Evaluación de Piglet/GLSlim en PS5

## Qué aportó en PS4

La scene de PS4 utilizó `libScePigletv2VSH.sprx` junto con
`libSceShaccVSH.sprx` para obtener una ruta EGL/OpenGL ES, normalmente cargando
y parcheando módulos VSH. Proyectos como `orbisGlPerf` demostraron GLES 2.0 y
otros ports reutilizaron `scePigletSetConfigurationVSH` antes de `eglInitialize`.
Esto evitaba que cada homebrew tuviera que emitir GNM/PM4 directamente.

## Evidencia local en esta PS5 12.02

- Los inventarios capturados muestran `libSceGLSlimVSH.sprx` cargada en
  `SceNKUIProcess` tanto en menú como durante juegos.
- No aparece cargada en los procesos de RE2 o San Andreas.
- Los stubs locales de `libSceGLSlimVSH` contienen
  `scePigletAllocateSystemMemoryEx`, `scePigletAllocateVideoMemoryEx`, sus
  parejas de release y `scePigletGet/SetConfigurationVSH`.
- El WebKit de PS5 que probamos no expone WebGL, aunque la UI nativa pueda usar
  internamente GLSlim/Piglet. Son superficies y permisos distintos.

## Interpretación

Piglet sigue siendo una ruta de investigación válida y potencialmente mucho
más sencilla para ports 2D/3D basados en GLES. Sin embargo, su presencia dentro
de `SceNKUIProcess` no demuestra que un homebrew `FAKE00000` pueda cargarlo,
crear contexto, compilar shaders o presentar buffers. En PS4 la ruta conocida
dependía de módulos VSH y parches; no debe asumirse ABI ni permisos idénticos en
PS5.

## Probe mínimo propuesto

1. Resolver/cargar `libSceGLSlimVSH` sin parches y registrar sólo resultados.
2. Enumerar exports/NID de Piglet, EGL y GLES disponibles en firmware 12.02.
3. Consultar `scePigletGetConfigurationVSH` sin modificar configuración.
4. En una ejecución separada, probar configuración mínima, `eglGetDisplay` y
   `eglInitialize`, siempre con timeouts y cleanup.
5. Sólo si eso funciona: contexto GLES, clear de un backbuffer y swap.

Esta ruta no sustituye el análisis AGC: si Piglet está restringido al shell o
falla su compilador de shaders, AGC seguirá siendo la ruta nativa necesaria.

## Primer resultado en `FAKE00000`

La fase de resolución sin inicialización GPU intentó cargar directamente
`/system_ex/common_ex/lib/libSceGLSlimVSH.sprx`. `dlopen` falló de forma limpia
con `error_code=0xffffffff` y el proceso salió con `rc=10`. Por tanto la carga
directa por ruta no funciona en este host.

La segunda ejecución solicitó el sysmodule interno `0x800000a9`, pero
`sceSysmoduleLoadModuleInternal` devolvió `0x80020063` antes de llegar a
`dlopen` o a cualquier API EGL/Piglet. El ID coincide con la tabla del SDK;
los headers locales no permiten asignar un significado preciso al error.

En consecuencia, GLSlim/Piglet está **presente** en el firmware y expone la
superficie esperada, pero las dos vías de carga probadas desde `FAKE00000`
(pathname y sysmodule interno) no son utilizables. Se detienen aquí las fases
de inicialización gráfica: avanzar exigiría primero demostrar una ruta de carga
legítima o entender el contexto/dependencias con que `SceNKUIProcess` lo usa.
