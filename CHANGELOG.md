# Registro de cambios

## Próxima versión

### Añadido

- Sistema bilingüe español/inglés con detección automática del idioma del
  servidor y selección persistente mediante `/language`.
- Nuevo `/case` con canales privados, transcript HTML sanitizado, SHA-256,
  compresión y retención automática.
- Nuevo `/lfg` con inscripción voluntaria, juegos y roles configurables, panel
  persistente y actualización mediante actividades `Playing`.
- Persistencia SQLite limitada a metadatos de casos y asignaciones LFG activas,
  sin guardar contenido de mensajes ni historial de presencia.

### Corregido

- Protegidos los botones y confirmaciones para que solo pueda usarlos quien
  inició la operación, con una nueva comprobación de permisos.
- Corregidas la jerarquía de roles y la limpieza de configuraciones al salir de
  un servidor.
- Corregidas las carreras del sistema de conteo y la conservación de su récord.
- Corregida la creación de hilos para evitar reacciones huérfanas y duplicados.
- Corregido el manejo de errores HTTP y de permisos en tareas automáticas.
- Sustituida la consulta manual del clan tag por la API pública de `discord.py`.

### Mejorado

- Prueba de actualización automática de despliegue: 2026-07-28.
- Añadidos límites de descarga, tiempo y tamaño de imagen al módulo de
  expresiones.
- Añadidos índices, validación de columnas y claves foráneas en SQLite.
- El arranque se detiene si falta un módulo público requerido.
- Añadidas pruebas automatizadas y configuración de Ruff.
- Dependencias reducidas a las usadas realmente por el proyecto.
- Corregida la configuración de paquetes para instalaciones editables.
- Archivos heredados retirados del árbol activo y conservados en una copia de
  seguridad externa.
