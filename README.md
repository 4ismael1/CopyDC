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
