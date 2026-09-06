# Proyectos publicables

Cada subdirectorio de `projects/` representa el staging de un futuro repositorio
independiente. El laboratorio privado situado fuera de esta carpeta nunca se
publica en bloque.

## Proyectos

| Directorio | Estado | Futuro repositorio |
| --- | --- | --- |
| `ps5-xash3d/` | Activo: port Xash3D sobre AGC, Fases 0–3 validadas en hardware; público, `main` protegida pendiente | [mpereiraesaa/ps5-xash3d](https://github.com/mpereiraesaa/ps5-xash3d) |
| `ps5-agc-gears/` | Público, standalone y validado en hardware; congelado como demo Gears | [mpereiraesaa/ps5-agc-gears](https://github.com/mpereiraesaa/ps5-agc-gears) |
| `logging_server/` | Componente privado reutilizable; suite host activa | Telemetría TCP `ps5log/1` |

## Regla de aislamiento

Un proyecto sólo puede publicarse después de:

1. contener exclusivamente archivos propios o dependencias públicas con licencia;
2. pasar su auditor de publicación sobre una copia limpia;
3. construir sin depender de dumps, Ghidra, juegos o rutas privadas del laboratorio;
4. documentar firmware probado, límites y hashes de release;
5. recibir nombre, Title ID, licencia y repositorio remoto definitivos.

No se copian automáticamente archivos desde `research/`, `captures/`, `dumps/`,
`sessions/`, `third_party/` ni `apps/`.
