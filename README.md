# CopyDC

Bot modular de utilidades y automatización para Discord, construido con
`discord.py` y SQLite. Conserva comandos de texto con los prefijos `c!` y `!`,
y ofrece comandos slash para los módulos compatibles.

## Funciones

- Copia, creación y extracción de emojis y stickers.
- Hilos automáticos por canal para mensajes, texto o contenido multimedia.
- Sistema de conteo con récord, reinicio y protección frente a mensajes simultáneos.
- Reacciones automáticas por palabra o frase.
- Roles por vanity y por clan tag.
- Gestión y auditoría de roles para boosters.
- Información de usuarios, roles, servidores, avatares y boosts.
- Consulta protegida del registro de expulsiones.
- Casos privados de soporte con transcript HTML, hash de integridad y retención configurable.
- LFG voluntario con panel y roles temporales basados en actividades de juego en tiempo real.
- Herramientas privadas de diagnóstico para el propietario.

La ayuda completa está disponible dentro de Discord con `/help`, `c!help` o
`!help`.

## Idiomas

Los mensajes, embeds, menús y paneles públicos están disponibles en español e
inglés. Por defecto, Copy usa español cuando el idioma preferido del servidor
de Discord es una variante de español y usa inglés para cualquier otro idioma.

Un miembro con el permiso **Gestionar servidor** puede ejecutar `/language`,
`c!language` o `!language` y elegir:

- **Automático**: seguir el idioma preferido del servidor.
- **Español**: forzar español para todo el servidor.
- **English**: forzar inglés para todo el servidor.

La selección se guarda en la base de datos y se conserva después de reiniciar
el bot.

## Legal

- [Política de privacidad](https://copy.tyr.lat/privacy)
- [Términos de servicio](https://copy.tyr.lat/terms)

Los mismos enlaces están disponibles desde los botones `Privacy` y `Terms` del
menú de ayuda del bot.

## Requisitos

- Python 3.11 o superior.
- Una aplicación y un bot de Discord configurados.
- Permisos del bot acordes con cada módulo: enviar mensajes, insertar enlaces,
  gestionar canales, gestionar roles, gestionar expresiones y ver el registro de
  auditoría cuando corresponda.
- Los intents `Message Content`, `Guild Members` y `Guild Presences` activados
  en el portal y en el cliente. Los módulos de casos y LFG explican dentro de
  Discord qué datos procesan mediante `/case privacy` y `/lfg privacy`.

## Instalación

```powershell
git clone https://github.com/4ismael1/CopyDC.git
cd CopyDC
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

En Linux o macOS, activa el entorno con `source .venv/bin/activate` y copia el
archivo con `cp .env.example .env`.

Configura `.env`:

```dotenv
BOT_TOKEN=token_del_bot
OWNER_ID=id_numerico_del_propietario
```

Después inicia el bot:

```powershell
python main.py
```

## Casos de soporte

1. Crea una categoría para los casos, un rol para el equipo y un canal de
   archivo oculto para `@everyone`.
2. Ejecuta `/case setup`.
3. Los usuarios abren casos con `/case open`.
4. `/case close` consulta el historial completo, publica el transcript en el
   archivo privado y deja el caso en modo de solo lectura.

La base de datos solo conserva metadatos e IDs. El transcript escapa contenido
HTML, incluye un SHA-256 y no descarga los archivos adjuntos. Los expedientes
se eliminan automáticamente según la retención de 1 a 90 días.

## LFG por actividad en vivo

1. Publica el panel con `/lfg setup`.
2. Añade cada nombre exacto de actividad y un rol temporal dedicado con
   `/lfg game_add`.
3. Cada usuario decide participar con `/lfg enroll` o el botón del panel.

El rol y el panel se actualizan con eventos de presencia. Solo se conserva la
inscripción y la asignación activa; al terminar el juego o usar `/lfg leave`,
la asignación se elimina. No se crea un historial de presencia.

La base de datos `bot_database.db` se crea o actualiza automáticamente en la
raíz del proyecto. El archivo está excluido de Git.

## Panel de servidores (solo propietario de Copy)

- `c!servers`: lista paginada con selector, búsqueda, refresco y navegación.
- `c!servers ID` o `c!servers parte del nombre`: filtra sin distinguir mayúsculas.
- `c!servers info nombre`: muestra la ficha si hay un resultado, o un selector si hay varios.
- Las pestañas mantienen resumen, miembros/canales, roles/emojis, seguridad/Nitro y permisos.
- Al volver de una ficha se conserva la búsqueda y página. Los conteos de humanos/bots son de caché.

## Espejo experimental (mensajes de todos los usuarios)

**Úsalo únicamente en servidores de prueba propios. El setup destruye los canales y
el historial del DESTINO, incluidos sus hilos. No hay recuperación automática.**

1. Copy debe estar en ambos servidores. Solo el dueño de Copy puede usar `c!mirror`; para
   cualquier otro usuario los comandos no responden nada, como si no existieran.
2. El destino debe tener Comunidad desactivada y Copy debe tener Administrador allí.
   En el origen requiere ver canales y leer historial; Message Content debe estar habilitado.
3. Desde el **destino**, ejecuta `c!mirror setup ID_ORIGEN`.
4. Revisa el inventario adjunto, pulsa el botón y escribe el ID del **destino** para confirmar.
5. Se reemplazan sus canales por categorías, texto y voz del origen. No se copian roles,
   permisos, historial, hilos, foros o escenarios. Los permisos del destino se heredan;
   no introduzcas otros participantes sin revisar sus accesos.

Se replican los mensajes nuevos de todos los usuarios humanos, ignorando bots y webhooks.
El origen es de solo lectura: no se crean webhooks allí, no se envían respuestas ni se
modifican canales o mensajes. Las acciones administrativas del destino sí aparecen en
su auditoría; esto no desactiva auditorías, registros ajenos ni registros internos de Discord.

Las ediciones actualizan la copia. Los borrados, incluidos los masivos, conservan el
contenido y adjuntos copiados y añaden una marca. Se dividen textos largos sin truncarlos.
Se intenta copiar adjuntos con un máximo total de 25 MiB por mensaje y respetando el
límite del destino. Los archivos no copiados se indican; no se archivan tarjetas enriquecidas.
Las menciones se envían sin notificar. Las respuestas se imitan con una cita del autor/texto original y un enlace a su copia en el destino (los webhooks no admiten respuestas reales).
No se transmite audio ni se sincronizan posteriores cambios de estructura.
Las copias normales no llevan etiqueta, ID ni fecha adicional. Las marcas de edición/borrado
se mantienen. Esto no cambia las copias antiguas ya publicadas ni la hora nativa de Discord.

Controles desde el destino:

- `c!mirror status`: estado y canales enlazados.
- `c!mirror history CANTIDAD` (o `historial`): importa los últimos 1–1000 mensajes (de cualquier usuario)
  únicamente del origen enlazado al **canal espejo donde ejecutas el comando**, anteriores
  al inicio de la importación. No recorre los demás canales. Rechaza canales sin enlace. Ignora bots/webhooks,
  omite los ya copiados y publica los seleccionados en orden cronológico. No borra canales.
  Discord los añade al final; no pueden insertarse antes de mensajes existentes. La réplica
  en vivo continúa y puede intercalarse. Repetir el comando omite duplicados: no busca otros
  mensajes más antiguos para compensarlos. El límite es por ejecución en el canal actual.
- `c!mirror historycancel`: cancela la importación después del mensaje en curso.
  Pausar/detener el espejo también interrumpe el trabajo. Las copias terminadas se conservan.
- `c!mirror pause` / `c!mirror resume`: pausar/reanudar.
- `c!mirror stop`: desconectar sin borrar las copias, canales ni webhooks existentes.
  Permite volver a ejecutar setup, con otra confirmación destructiva.

La base de datos guarda configuración e IDs de canales/webhooks/mensajes, no contenido
ni tokens de webhooks. Los archivos se procesan temporalmente en memoria. Reiniciar
conserva las relaciones ya guardadas, pero no hay recuperación de eventos perdidos
durante pausas, apagados o fallos ni garantía de entrega exactamente una vez. Una cola
llena o un fallo de réplica pausa el espejo y deja un aviso técnico sin contenido/tokens
en consola. Una configuración interrumpida queda en `error`: revisa el destino y usa
`stop` antes de repetir `setup`. No se continúa borrando automáticamente al reiniciar.

## Desarrollo

Instala las dependencias de desarrollo:

```powershell
python -m pip install -e ".[dev]"
```

Ejecuta las verificaciones antes de publicar:

```powershell
ruff check .
ruff format --check .
pytest -q
```

## Estructura

```text
CopyDC/
├── main.py                     # Inicio, eventos y carga de extensiones
├── database.py                 # Persistencia SQLite
├── command_utils.py            # Utilidades compartidas y vistas protegidas
├── modules/                    # Módulos visibles para los servidores
├── admin_modules/              # Herramientas exclusivas del propietario
├── scripts/
│   └── migrate_legacy_json.py  # Migración opcional desde JSON antiguo
├── tests/                      # Pruebas automatizadas
├── requirements.txt            # Dependencias de ejecución
└── pyproject.toml              # Configuración del proyecto y herramientas
```

Los módulos de usuario son obligatorios: si uno falla al cargar, el bot detiene
el arranque para evitar quedar activo a medias. Un módulo administrativo
defectuoso se registra como advertencia sin interrumpir las funciones públicas.

## Datos y copias de seguridad

Antes de actualizar el bot, detén el proceso y copia `bot_database.db` a una
ubicación segura. No publiques `.env`, bases de datos, logs, cachés ni archivos
comprimidos; todos están cubiertos por `.gitignore`.

Para migrar configuraciones antiguas desde `guilds.json` y
`thread_channels.json`:

```powershell
python scripts/migrate_legacy_json.py --source <carpeta_json> --database bot_database.db
```

## Compatibilidad

Los nombres y flujos de los módulos existentes se mantienen para no romper el
uso de los servidores actuales. Los nuevos módulos deben vivir en `modules/` y
exponer una función asíncrona `setup(bot)`.
