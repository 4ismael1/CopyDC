# database.py
import sqlite3
from typing import List, Dict, Tuple, Optional

DB_FILE = "bot_database.db"
SQLITE_TIMEOUT_SEC = 8
SQLITE_BUSY_TIMEOUT_MS = 5000


def _column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)

def get_db_connection():
    """Crea y devuelve una conexión a la base de datos."""
    conn = sqlite3.connect(DB_FILE, timeout=SQLITE_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return conn

def setup_database():
    """Crea las tablas de la base de datos si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    
    # Tabla para roles exclusivos (boost o normales)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS boost_roles (
        role_id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        linked_to_boost INTEGER DEFAULT 0  -- 1 = sí, 0 = no
    )
    """)

    # Canal de logs del módulo BoostRoles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS boost_logs (
        guild_id INTEGER PRIMARY KEY,
        channel_id INTEGER NOT NULL
    )
    """)

    # Tabla para registrar los servidores
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guilds (
        guild_id INTEGER PRIMARY KEY,
        guild_name TEXT NOT NULL
    )
    """)
    
    # Tabla para la configuración de hilos automáticos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS thread_configs (
        channel_id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        mode TEXT NOT NULL
    )
    """)

    # Tabla para el conteo (con la indentación corregida y la columna high_score)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS counting_channels (
        channel_id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        current_number INTEGER DEFAULT 0,
        last_user_id INTEGER DEFAULT 0,
        high_score INTEGER DEFAULT 0
    )
    """)

    # Tabla para reacciones automáticas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auto_reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        trigger_word TEXT NOT NULL,
        emojis TEXT NOT NULL,
        case_sensitive INTEGER DEFAULT 0,
        UNIQUE(guild_id, trigger_word)
    )
    """)

    # Tabla para presets de presencia del bot (owner)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_presence_presets (
        name TEXT PRIMARY KEY,
        activity_type TEXT NOT NULL,
        status TEXT NOT NULL,
        activity_text TEXT NOT NULL,
        activity_emoji TEXT,
        is_active INTEGER DEFAULT 0
    )
    """)
    if not _column_exists(cursor, "bot_presence_presets", "activity_emoji"):
        cursor.execute("ALTER TABLE bot_presence_presets ADD COLUMN activity_emoji TEXT")

    # Índices para lecturas frecuentes por servidor.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_configs_guild_id ON thread_configs(guild_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_boost_roles_guild_id ON boost_roles(guild_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_boost_roles_guild_linked ON boost_roles(guild_id, linked_to_boost)")

    conn.commit()
    conn.close()

# --- Funciones para Guilds ---
def sync_guilds(guilds_from_bot: List[Dict]):
    """Sincroniza la tabla de guilds con la lista de servidores del bot."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Borra los datos antiguos para empezar de cero
    cursor.execute("DELETE FROM guilds")
    
    # Inserta los datos actualizados
    guild_data = [(guild.id, guild.name) for guild in guilds_from_bot]
    cursor.executemany("INSERT INTO guilds (guild_id, guild_name) VALUES (?, ?)", guild_data)
    
    conn.commit()
    conn.close()

def add_guild(guild: Dict):
    """Añade un servidor a la base de datos."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO guilds (guild_id, guild_name) VALUES (?, ?)", (guild.id, guild.name))
    conn.commit()
    conn.close()

def remove_guild(guild: Dict):
    """Elimina un servidor de la base de datos."""
    conn = get_db_connection()
    conn.execute("DELETE FROM guilds WHERE guild_id = ?", (guild.id,))
    conn.commit()
    conn.close()

def get_all_guilds() -> List[sqlite3.Row]:
    """Obtiene todos los servidores de la base de datos."""
    conn = get_db_connection()
    guilds = conn.execute("SELECT * FROM guilds").fetchall()
    conn.close()
    return guilds

# --- Funciones para Threads ---
def add_thread_config(guild_id: int, channel_id: int, mode: str):
    """Añade o actualiza una configuración de hilo."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO thread_configs (guild_id, channel_id, mode) VALUES (?, ?, ?)", (guild_id, channel_id, mode))
    conn.commit()
    conn.close()

def remove_thread_config(channel_id: int):
    """Elimina una configuración de hilo."""
    conn = get_db_connection()
    conn.execute("DELETE FROM thread_configs WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def get_thread_config_for_channel(channel_id: int) -> Optional[sqlite3.Row]:
    """Obtiene la configuración de un canal específico."""
    conn = get_db_connection()
    config = conn.execute("SELECT * FROM thread_configs WHERE channel_id = ?", (channel_id,)).fetchone()
    conn.close()
    return config

def get_all_thread_configs_for_guild(guild_id: int) -> List[sqlite3.Row]:
    """Obtiene todas las configuraciones de hilos para un servidor."""
    conn = get_db_connection()
    configs = conn.execute("SELECT * FROM thread_configs WHERE guild_id = ?", (guild_id,)).fetchall()
    conn.close()
    return configs

# --- NUEVAS FUNCIONES PARA EL CONTEO ---
def set_counting_channel(channel_id: int, guild_id: int):
    """Establece un canal para el conteo, reseteando su progreso."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO counting_channels (channel_id, guild_id, current_number, last_user_id) VALUES (?, ?, 0, 0)",
                 (channel_id, guild_id))
    conn.commit()
    conn.close()

def get_counting_channel(channel_id: int):
    """Obtiene la información de un canal de conteo."""
    conn = get_db_connection()
    channel_data = conn.execute("SELECT * FROM counting_channels WHERE channel_id = ?", (channel_id,)).fetchone()
    conn.close()
    return channel_data


def get_counting_channels_for_guild(guild_id: int) -> List[sqlite3.Row]:
    """Obtiene todos los canales de conteo configurados en un servidor."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM counting_channels WHERE guild_id = ?", (guild_id,)).fetchall()
    conn.close()
    return rows

def update_count(channel_id: int, new_number: int, user_id: int):
    """Actualiza el número y el último usuario en un canal de conteo."""
    conn = get_db_connection()
    conn.execute("UPDATE counting_channels SET current_number = ?, last_user_id = ? WHERE channel_id = ?",
                 (new_number, user_id, channel_id))
    conn.commit()
    conn.close()

def reset_count(channel_id: int):
    """Resetea el conteo de un canal a 0."""
    conn = get_db_connection()
    conn.execute("UPDATE counting_channels SET current_number = 0, last_user_id = 0 WHERE channel_id = ?",
                 (channel_id,))
    conn.commit()
    conn.close()
# ───── Funciones BoostRoles ─────
def add_boost_role(guild_id: int, role_id: int, linked_to_boost: bool):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO boost_roles (role_id, guild_id, linked_to_boost) "
        "VALUES (?, ?, ?)",
        (role_id, guild_id, int(linked_to_boost)),
    )
    conn.commit()
    conn.close()

def get_boost_roles_for_guild(guild_id: int):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM boost_roles WHERE guild_id = ?", (guild_id,)
    ).fetchall()
    conn.close()
    return rows

def get_linked_roles_for_guild(guild_id: int):
    """Devuelve los role_id marcados como vinculados a Boost."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT role_id FROM boost_roles WHERE guild_id = ? AND linked_to_boost = 1",
        (guild_id,),
    ).fetchall()
    conn.close()
    return [r["role_id"] for r in rows]

def set_boost_log_channel(guild_id: int, channel_id: int):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO boost_logs (guild_id, channel_id) VALUES (?, ?)",
        (guild_id, channel_id),
    )
    conn.commit()
    conn.close()

def get_boost_log_channel(guild_id: int):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM boost_logs WHERE guild_id = ?", (guild_id,)
    ).fetchone()
    conn.close()
    return row

def get_boost_role(guild_id: int, role_id: int):
    """Devuelve una fila (o None) con la configuración de un rol concreto."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM boost_roles WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id)
    ).fetchone()
    conn.close()
    return row

def delete_boost_role(guild_id: int, role_id: int):
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM boost_roles WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id)
    )
    conn.commit()
    conn.close()

# --- Funciones para Auto Reactions ---
def add_auto_reaction(guild_id: int, trigger_word: str, emojis: list):
    """Añade o actualiza una configuración de reacción automática."""
    import json
    conn = get_db_connection()
    emojis_json = json.dumps(emojis)
    conn.execute(
        "INSERT OR REPLACE INTO auto_reactions (guild_id, trigger_word, emojis, case_sensitive) "
        "VALUES (?, ?, ?, 0)",
        (guild_id, trigger_word.lower(), emojis_json)
    )
    conn.commit()
    conn.close()

def remove_auto_reaction(guild_id: int, trigger_word: str):
    """Elimina una configuración de reacción automática."""
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM auto_reactions WHERE guild_id = ? AND trigger_word = ?",
        (guild_id, trigger_word.lower())
    )
    conn.commit()
    conn.close()

def get_auto_reaction(guild_id: int, trigger_word: str) -> Optional[sqlite3.Row]:
    """Obtiene una configuración específica de reacción automática."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM auto_reactions WHERE guild_id = ? AND trigger_word = ?",
        (guild_id, trigger_word.lower())
    ).fetchone()
    conn.close()
    return row

def get_all_auto_reactions(guild_id: int) -> List[sqlite3.Row]:
    """Obtiene todas las configuraciones de reacciones automáticas de un servidor."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM auto_reactions WHERE guild_id = ? ORDER BY trigger_word",
        (guild_id,)
    ).fetchall()
    conn.close()
    return rows

def clear_auto_reactions(guild_id: int):
    """Elimina todas las configuraciones de reacciones automáticas de un servidor."""
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM auto_reactions WHERE guild_id = ?",
        (guild_id,)
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# BOT PRESENCE PRESETS
# ──────────────────────────────────────────────────────────────────────────────
def upsert_bot_presence_preset(
    name: str,
    activity_type: str,
    status: str,
    activity_text: str,
    activity_emoji: Optional[str] = None,
):
    """Crea o actualiza un preset de presencia."""
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT name FROM bot_presence_presets WHERE lower(name) = lower(?)",
        (name,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE bot_presence_presets
            SET activity_type = ?, status = ?, activity_text = ?, activity_emoji = ?
            WHERE name = ?
            """,
            (activity_type, status, activity_text, activity_emoji, existing["name"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO bot_presence_presets (name, activity_type, status, activity_text, activity_emoji)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, activity_type, status, activity_text, activity_emoji),
        )
    conn.commit()
    conn.close()


def list_bot_presence_presets() -> List[sqlite3.Row]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM bot_presence_presets ORDER BY is_active DESC, name COLLATE NOCASE"
    ).fetchall()
    conn.close()
    return rows


def get_bot_presence_preset(name: str) -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM bot_presence_presets WHERE lower(name) = lower(?)",
        (name,),
    ).fetchone()
    conn.close()
    return row


def set_active_bot_presence_preset(name: str) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT name FROM bot_presence_presets WHERE lower(name) = lower(?)",
        (name,),
    ).fetchone()
    if row is None:
        conn.close()
        return False

    conn.execute("UPDATE bot_presence_presets SET is_active = 0")
    conn.execute(
        "UPDATE bot_presence_presets SET is_active = 1 WHERE name = ?",
        (row["name"],),
    )
    conn.commit()
    conn.close()
    return True


def get_active_bot_presence_preset() -> Optional[sqlite3.Row]:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM bot_presence_presets WHERE is_active = 1 LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def delete_bot_presence_preset(name: str) -> bool:
    conn = get_db_connection()
    cursor = conn.execute(
        "DELETE FROM bot_presence_presets WHERE lower(name) = lower(?)",
        (name,),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def clear_bot_presence_presets():
    conn = get_db_connection()
    conn.execute("DELETE FROM bot_presence_presets")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# VANITY MODULE
# ═══════════════════════════════════════════════════════════════════════════════

def setup_vanity_table():
    """Crea las tablas de vanity si no existen."""
    conn = get_db_connection()
    
    # Configuración general del servidor
    conn.execute("""
    CREATE TABLE IF NOT EXISTS vanity_settings (
        guild_id INTEGER PRIMARY KEY,
        channel_id INTEGER,
        embed_title TEXT DEFAULT '✨ ¡Gracias por representarnos!',
        embed_description TEXT DEFAULT '{user} ahora tiene **{vanity}** en su estado y recibió {role}',
        embed_color INTEGER DEFAULT 5763719,
        embed_thumbnail TEXT,
        embed_image TEXT,
        remove_enabled INTEGER DEFAULT 0,
        remove_channel_id INTEGER,
        remove_title TEXT DEFAULT '👋 Vanity Removida',
        remove_description TEXT DEFAULT '{user} quitó **{vanity}** de su estado',
        remove_color INTEGER DEFAULT 15548997
    )
    """)
    
    # Múltiples vanitys por servidor
    conn.execute("""
    CREATE TABLE IF NOT EXISTS vanity_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        vanity_code TEXT NOT NULL,
        role_id INTEGER NOT NULL,
        UNIQUE(guild_id, vanity_code)
    )
    """)
    
    conn.commit()
    conn.close()

def get_vanity_settings(guild_id: int) -> Optional[dict]:
    """Obtiene la configuración general de vanity."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM vanity_settings WHERE guild_id = ?",
        (guild_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def set_vanity_settings(guild_id: int, **kwargs):
    """Guarda la configuración general de vanity."""
    conn = get_db_connection()
    
    if not kwargs:
        conn.execute(
            "INSERT OR IGNORE INTO vanity_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
    else:
        columns = ["guild_id", *kwargs.keys()]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(f"{k} = excluded.{k}" for k in kwargs.keys())
        conn.execute(
            f"INSERT INTO vanity_settings ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {update_clause}",
            [guild_id, *kwargs.values()],
        )
    
    conn.commit()
    conn.close()

def get_vanity_codes(guild_id: int) -> List[dict]:
    """Obtiene todas las vanitys configuradas."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM vanity_codes WHERE guild_id = ?",
        (guild_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_vanity_code(guild_id: int, vanity_code: str, role_id: int) -> bool:
    """Añade una vanity. Retorna False si ya existe."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO vanity_codes (guild_id, vanity_code, role_id) VALUES (?, ?, ?)",
            (guild_id, vanity_code, role_id)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except sqlite3.Error:
        conn.close()
        return False

def remove_vanity_code(guild_id: int, vanity_code: str) -> bool:
    """Elimina una vanity. Retorna True si se eliminó."""
    conn = get_db_connection()
    cursor = conn.execute(
        "DELETE FROM vanity_codes WHERE guild_id = ? AND vanity_code = ?",
        (guild_id, vanity_code)
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def delete_all_vanity(guild_id: int):
    """Elimina toda la configuración de vanity del servidor."""
    conn = get_db_connection()
    conn.execute("DELETE FROM vanity_settings WHERE guild_id = ?", (guild_id,))
    conn.execute("DELETE FROM vanity_codes WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CLAN TAG MODULE
# ═══════════════════════════════════════════════════════════════════════════════

def setup_clantag_table():
    """Crea la tabla de clan tag si no existe."""
    conn = get_db_connection()
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS clantag_settings (
        guild_id INTEGER PRIMARY KEY,
        role_id INTEGER,
        channel_id INTEGER,
        embed_title TEXT DEFAULT '🏷️ ¡Gracias por representarnos!',
        embed_description TEXT DEFAULT '{user} ahora tiene el tag **{tag}** y recibió {role}',
        embed_color INTEGER DEFAULT 5763719,
        remove_enabled INTEGER DEFAULT 0,
        remove_channel_id INTEGER,
        remove_title TEXT DEFAULT '😢 Tag removido',
        remove_description TEXT DEFAULT '{user} ya no tiene el tag **{tag}**',
        remove_color INTEGER DEFAULT 15548997
    )
    """)
    
    conn.commit()
    conn.close()

def get_clantag_settings(guild_id: int) -> Optional[dict]:
    """Obtiene la configuración de clan tag."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM clantag_settings WHERE guild_id = ?",
        (guild_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def set_clantag_settings(guild_id: int, **kwargs):
    """Guarda la configuración de clan tag."""
    conn = get_db_connection()
    
    if not kwargs:
        conn.execute(
            "INSERT OR IGNORE INTO clantag_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
    else:
        columns = ["guild_id", *kwargs.keys()]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(f"{k} = excluded.{k}" for k in kwargs.keys())
        conn.execute(
            f"INSERT INTO clantag_settings ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {update_clause}",
            [guild_id, *kwargs.values()],
        )
    
    conn.commit()
    conn.close()

def delete_clantag_settings(guild_id: int):
    """Elimina la configuración de clan tag del servidor."""
    conn = get_db_connection()
    conn.execute("DELETE FROM clantag_settings WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()
