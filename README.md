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

## Convertir una imagen en sticker

Responde a una imagen adjunta con `c!sticker [nombre]` (alias `stickers` / `stk`).
Esta conversión no cambia `c!emoji` ni `c!copy` de emojis/stickers ya existentes.

- Recorta únicamente márgenes completamente transparentes; no elimina fondos blancos,
  sombras ni contenido semitransparente para llenar el lienzo.
- Ajusta el dibujo proporcionalmente dentro de 320×320, sin deformarlo. No reduce
  sucesivamente el dibujo ni los colores para forzar el límite de 512 KiB.
- Si exige más de 2× ampliación, queda muy estrecho/pequeño o casi invisible,
  muestra una vista previa y requiere confirmación antes de crear el sticker.
  La evaluación del tamaño visible es orientativa, no una garantía de nitidez.
- Solo quien ejecutó el comando puede confirmar, conservando el permiso Gestionar
  expresiones. Cancelar o dejar pasar 3 minutos no crea nada. Una vista previa
  nueva del mismo usuario en el mismo servidor reemplaza la anterior.
- Las animaciones GIF/APNG válidas se conservan byte por byte. Se comprueban
  dimensiones 320×320, peso hasta 512 KiB y duración de hasta 5 segundos.
  El límite local de validación es de 300 fotogramas. Las animaciones incompatibles
  se rechazan con instrucciones, sin convertirlas en imágenes fijas.
- El procesamiento se ejecuta fuera del bucle principal, una conversión a la vez,
  con límites de 8 MiB de entrada y 25 millones de píxeles.

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
