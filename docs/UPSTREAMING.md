# Publicación y forks

## Intención

Conforme madure el proyecto, publicar en la cuenta personal del propietario
forks y parches clean-room que sean útiles para homebrew legal. La publicación
será deliberada y por componente; esta nota no autoriza un push automático.

## Estado actual

- LLVM (`GPUOpen-Drivers/llvm-project`): checkout limpio, commit
  `8fd93e26cf9b1235fc9573b68b96233818be0ed4`; no necesita fork por ahora.
- LLPC (`GPUOpen-Drivers/llpc`): un cambio local en
  `lgc/state/TargetInfo.cpp`, base
  `40cb8d95ad8d6f7f1652e3fd47d39667594cce08`.
- Parche exportado:
  `patches/llpc/0001-lgc-add-gfx1013-target.patch`.
- Resultado demostrado con ese toolchain: ELF PAL `gfx1013`, shaders GS 196 B
  y PS 16 B, y triángulo confirmado en hardware.

## Gate antes de publicar

1. Crear un fork personal del repositorio correcto, nunca mezclar LLVM y LLPC.
2. Partir del commit base documentado y aplicar el parche con `git apply`.
3. Añadir una prueba LLPC específica para que `gfx1013` no vuelva a desaparecer.
4. Ejecutar formato, build, prueba shader mínima y `git diff --check`.
5. Revisar licencia, autoría y mensaje de commit; explicar que el perfil heredado
   de `gfx1010` es una decisión conservadora, no una caracterización completa.
6. Auditar que el commit no incluya `build-gfx1030`, artefactos, rutas locales,
   capturas de consola ni material propietario.
7. Publicar primero la rama del fork; abrir upstream sólo cuando el cambio tenga
   test y justificación aceptables para el proyecto receptor.

## Organización futura sugerida

- Fork LLPC: soporte y tests de `gfx1013`.
- Repositorio `homebrew_ps5`: runtime, probes, documentación y shaders propios.
- Demo pública AGC: repositorio aislado en `projects/ps5-agc-gears`; debe poder
  construirse sin acceder al resto del laboratorio antes de convertirse en repo.
- Parches de SDK: repositorio/fork independiente cuando sus cambios tengan ABI,
  tests y procedencia clean-room claramente documentados.

Antes de cualquier publicación hay que confirmar el usuario/organización de
GitHub, nombres de repositorios, visibilidad y licencia deseada.
