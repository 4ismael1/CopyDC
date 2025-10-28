# CopyDC

CopyDC es un bot de utilidades para Discord centrado en simplificar la gestion de recursos, la automatizacion de tareas repetitivas y la obtencion de datos del servidor. Se construye sobre `discord.py 2.x`, almacena configuraciones en SQLite y expone un conjunto modular de comandos de texto y slash.

## Capacidades
- **Clonado de recursos**: `c!copy`, `c!emoji` y `c!sticker` replican emojis o stickers entre servidores y generan nuevos desde adjuntos.
- **Recuperacion de origenes**: `c!get` devuelve el archivo de cualquier emoji o sticker previamente registrado.
- **Automatizacion de hilos**: `c!thread add/remove/list` define reglas por canal para abrir hilos de forma inmediata.
- **Canal de conteo asistido**: `c!counting` valida el flujo numerico y mantiene la secuencia sin intervencion manual.
- **Reacciones automaticas**: `c!react` asocia palabras clave con emojis que se aplican automaticamente a mensajes coincidentes.
- **Informes rapidos**: `c!user`, `c!roleinfo`, `c!serverinfo`, `c!boost` y `c!avatar` consolidan datos clave en embeds estructurados.
- **Roles para boosters**: `/boostrole` gestiona asignaciones, auditorias y retiros programados mediante tareas asincronas.
- **Panel propietario**: los cogs en `admin_modules/` ofrecen diagnosticos, sincronizacion de comandos y herramientas de depuracion exclusivas para `OWNER_ID`.

## Estructura del proyecto
```text
CopyDC/
|-- main.py            # Punto de entrada, inicializa intents y carga cogs
|-- database.py        # Operaciones sobre SQLite (guilds, hilos, conteo, boost roles)
|-- modules/           # Cogs generales expuestos a los servidores
|   |-- help_cog.py
|   |-- info_cog.py
|   |-- expression_cog.py
|   |-- threads_cog.py
|   |-- counting_cog.py
|   |-- auto_react_cog.py
|   |-- boost_roles_cog.py
|   `-- audit_kicks_cog.py
|-- admin_modules/     # Herramientas exclusivas para el propietario
|   |-- owner_cog.py
|   |-- perm_inspector_cog.py
|   |-- devtools_cog.py
|   `-- ...
|-- requirements.txt   # Dependencias fijadas
`-- .env.example       # Variables de entorno requeridas
```

## Requisitos
- Python 3.11 o superior.
- Una aplicacion de Discord con token activo y intents privilegiados habilitados.
- Permisos `Manage Guild`, `Manage Roles`, `Manage Channels` y `View Audit Log` en los servidores de destino.

## Instalacion
```bash
git clone https://github.com/4ismael1/CopyDC.git
cd CopyDC
python -m venv .venv
```

### Activar entorno y dependencias
```bash
# Windows
.\.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -U pip wheel
pip install -r requirements.txt
```

### Variables de entorno
```bash
cp .env.example .env  # Windows: copy .env.example .env
```
Completa los valores en `.env` antes de ejecutar el bot.

## Ejecucion
```bash
python main.py
```
El bot sincroniza comandos y crea `bot_database.db` al iniciar.

## Toolkit administrativo
- `owner_cog`: inspeccion de guilds, roles y canales.
- `perm_inspector_cog`: analisis puntual de permisos por miembro, rol o canal.
- `devtools_cog`: sincronizacion de slash commands, recarga de cogs y tareas de mantenimiento.
