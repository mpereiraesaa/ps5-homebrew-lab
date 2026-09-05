# Parches publicables

Este directorio guarda únicamente cambios clean-room reproducibles sobre
proyectos públicos. No debe contener dumps, blobs, shaders ni valores extraídos
de software propietario.

## Inventario actual

| Parche | Proyecto base | Commit base | Propósito |
| --- | --- | --- | --- |
| `llpc/0001-lgc-add-gfx1013-target.patch` | GPUOpen LLPC | `40cb8d95ad8d6f7f1652e3fd47d39667594cce08` | Permitir que LGC seleccione `gfx1013` usando el perfil conservador GFX10.1 de `gfx1010` |

LLVM no tiene modificaciones locales: el checkout de
`GPUOpen-Drivers/llvm-project` está limpio en
`8fd93e26cf9b1235fc9573b68b96233818be0ed4` y ya reconoce la CPU `gfx1013`.

Los archivos `build*` nunca forman parte de un fork ni de un parche.
