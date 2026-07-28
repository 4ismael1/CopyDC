# database.py
import sqlite3
from pathlib import Path

DB_FILE = str(Path(__file__).resolve().parent / "bot_database.db")
SQLITE_TIMEOUT_SEC = 8
SQLITE_BUSY_TIMEOUT_MS = 5000
VANITY_SETTING_COLUMNS = {
    "channel_id",
    "embed_title",
    "embed_description",
    "embed_color",
    "embed_thumbnail",
    "embed_image",
    "remove_enabled",
    "remove_channel_id",
    "remove_title",
    "remove_description",
    "remove_color",
}
CLANTAG_SETTING_COLUMNS = {
    "role_id",
    "channel_id",
    "embed_title",
    "embed_description",
    "embed_color",
    "remove_enabled",
    "remove_channel_id",
    "remove_title",
    "remove_description",
    "remove_color",
}


def _column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)


def get_db_connection():
    """Crea y devuelve una conexión a la base de datos."""
    conn = sqlite3.connect(DB_FILE, timeout=SQLITE_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
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
    if not _column_exists(cursor, "counting_channels", "high_score"):
        cursor.execute("ALTER TABLE counting_channels ADD COLUMN high_score INTEGER DEFAULT 0")
        cursor.execute(
            """
            UPDATE counting_channels
            SET high_score = COALESCE(current_number, 0)
            """
        )

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

    # Casos de soporte. Solo se conservan metadatos; el contenido queda en el
    # transcript publicado en el canal privado elegido por el servidor.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_settings (
        guild_id INTEGER PRIMARY KEY,
        archive_channel_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        support_role_id INTEGER NOT NULL,
        retention_days INTEGER NOT NULL DEFAULT 30
            CHECK(retention_days BETWEEN 1 AND 90)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_cases (
        case_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL UNIQUE,
        opener_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open'
            CHECK(status IN ('open', 'closed')),
        archive_channel_id INTEGER,
        archive_message_id INTEGER,
        created_at TEXT NOT NULL,
        closed_at TEXT
    )
    """)
    if not _column_exists(cursor, "support_cases", "archive_channel_id"):
        cursor.execute("ALTER TABLE support_cases ADD COLUMN archive_channel_id INTEGER")

    # LFG basado en actividad. assignments representa únicamente el estado
    # actual y se elimina cuando la actividad termina; no es un historial.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lfg_settings (
        guild_id INTEGER PRIMARY KEY,
        dashboard_channel_id INTEGER NOT NULL,
        dashboard_message_id INTEGER
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lfg_games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        activity_name TEXT NOT NULL COLLATE NOCASE,
        display_name TEXT NOT NULL,
        role_id INTEGER NOT NULL,
        UNIQUE(guild_id, activity_name)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lfg_enrollments (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        enrolled_at TEXT NOT NULL,
        PRIMARY KEY(guild_id, user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lfg_assignments (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        assigned_at TEXT NOT NULL,
        PRIMARY KEY(guild_id, user_id)
    )
    """)

    # Índices para lecturas frecuentes por servidor.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_configs_guild_id ON thread_configs(guild_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_boost_roles_guild_id ON boost_roles(guild_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_boost_roles_guild_linked ON boost_roles(guild_id, linked_to_boost)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_counting_channels_guild_id ON counting_channels(guild_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_auto_reactions_guild_id ON auto_reactions(guild_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_support_cases_guild_status ON support_cases(guild_id, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_support_cases_opener_status "
        "ON support_cases(guild_id, opener_id, status)"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_support_cases_one_open_per_user "
        "ON support_cases(guild_id, opener_id) WHERE status = 'open'"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_support_cases_closed_at ON support_cases(status, closed_at)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lfg_games_guild_id ON lfg_games(guild_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lfg_assignments_guild_id ON lfg_assignments(guild_id)")
    cursor.execute("PRAGMA user_version = 2")

    conn.commit()
    conn.close()


# --- Funciones para Guilds ---
def sync_guilds(guilds_from_bot: list[dict]):
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


def add_guild(guild: dict):
    """Añade un servidor a la base de datos."""
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO guilds (guild_id, guild_name) VALUES (?, ?)", (guild.id, guild.name))
    conn.commit()
    conn.close()


def remove_guild(guild: dict):
    """Elimina un servidor y toda la configuración que le pertenece."""
    conn = get_db_connection()
    guild_id = guild.id
    for table_name in (
        "thread_configs",
        "counting_channels",
        "auto_reactions",
        "boost_roles",
        "boost_logs",
        "vanity_codes",
        "vanity_settings",
        "clantag_settings",
        "support_cases",
        "support_settings",
        "lfg_assignments",
        "lfg_enrollments",
        "lfg_games",
        "lfg_settings",
    ):
        conn.execute(f"DELETE FROM {table_name} WHERE guild_id = ?", (guild_id,))
    conn.execute("DELETE FROM guilds WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()


def get_all_guilds() -> list[sqlite3.Row]:
    """Obtiene todos los servidores de la base de datos."""
    conn = get_db_connection()
    guilds = conn.execute("SELECT * FROM guilds").fetchall()
    conn.close()
    return guilds


# --- Funciones para Threads ---
def add_thread_config(guild_id: int, channel_id: int, mode: str):
    """Añade o actualiza una configuración de hilo."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO thread_configs (guild_id, channel_id, mode) VALUES (?, ?, ?)",
        (guild_id, channel_id, mode),
    )
    conn.commit()
    conn.close()


def remove_thread_config(channel_id: int):
    """Elimina una configuración de hilo."""
    conn = get_db_connection()
    conn.execute("DELETE FROM thread_configs WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()


def get_thread_config_for_channel(channel_id: int) -> sqlite3.Row | None:
    """Obtiene la configuración de un canal específico."""
    conn = get_db_connection()
    config = conn.execute("SELECT * FROM thread_configs WHERE channel_id = ?", (channel_id,)).fetchone()
    conn.close()
    return config


def get_all_thread_configs_for_guild(guild_id: int) -> list[sqlite3.Row]:
    """Obtiene todas las configuraciones de hilos para un servidor."""
    conn = get_db_connection()
    configs = conn.execute("SELECT * FROM thread_configs WHERE guild_id = ?", (guild_id,)).fetchall()
    conn.close()
    return configs


# --- NUEVAS FUNCIONES PARA EL CONTEO ---
def set_counting_channel(channel_id: int, guild_id: int):
    """Establece un canal para el conteo, reseteando su progreso."""
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO counting_channels (channel_id, guild_id, current_number, last_user_id)
        VALUES (?, ?, 0, 0)
        ON CONFLICT(channel_id) DO UPDATE SET
            guild_id = excluded.guild_id,
            current_number = 0,
            last_user_id = 0
        """,
        (channel_id, guild_id),
    )
    conn.commit()
    conn.close()


def remove_counting_channel(channel_id: int):
    """Desactiva el conteo en un canal sin afectar otros canales."""
    conn = get_db_connection()
    conn.execute("DELETE FROM counting_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()


def get_counting_channel(channel_id: int):
    """Obtiene la información de un canal de conteo."""
    conn = get_db_connection()
    channel_data = conn.execute(
        "SELECT * FROM counting_channels WHERE channel_id = ?", (channel_id,)
    ).fetchone()
    conn.close()
    return channel_data


def get_counting_channels_for_guild(guild_id: int) -> list[sqlite3.Row]:
    """Obtiene todos los canales de conteo configurados en un servidor."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM counting_channels WHERE guild_id = ?", (guild_id,)).fetchall()
    conn.close()
    return rows


def update_count(channel_id: int, new_number: int, user_id: int):
    """Actualiza el número y el último usuario en un canal de conteo."""
    conn = get_db_connection()
    conn.execute(
        """
        UPDATE counting_channels
        SET current_number = ?,
            last_user_id = ?,
            high_score = MAX(high_score, ?)
        WHERE channel_id = ?
        """,
        (new_number, user_id, new_number, channel_id),
    )
    conn.commit()
    conn.close()


def reset_count(channel_id: int):
    """Resetea el conteo de un canal a 0."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE counting_channels SET current_number = 0, last_user_id = 0 WHERE channel_id = ?",
        (channel_id,),
    )
    conn.commit()
    conn.close()


# ───── Funciones BoostRoles ─────
def add_boost_role(guild_id: int, role_id: int, linked_to_boost: bool):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO boost_roles (role_id, guild_id, linked_to_boost) VALUES (?, ?, ?)",
        (role_id, guild_id, int(linked_to_boost)),
    )
    conn.commit()
    conn.close()


def get_boost_roles_for_guild(guild_id: int):
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM boost_roles WHERE guild_id = ?", (guild_id,)).fetchall()
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
    row = conn.execute("SELECT * FROM boost_logs WHERE guild_id = ?", (guild_id,)).fetchone()
    conn.close()
    return row


def get_boost_role(guild_id: int, role_id: int):
    """Devuelve una fila (o None) con la configuración de un rol concreto."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM boost_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
    ).fetchone()
    conn.close()
    return row


def delete_boost_role(guild_id: int, role_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM boost_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
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
        (guild_id, trigger_word.lower(), emojis_json),
    )
    conn.commit()
    conn.close()


def remove_auto_reaction(guild_id: int, trigger_word: str):
    """Elimina una configuración de reacción automática."""
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM auto_reactions WHERE guild_id = ? AND trigger_word = ?", (guild_id, trigger_word.lower())
    )
    conn.commit()
    conn.close()


def get_auto_reaction(guild_id: int, trigger_word: str) -> sqlite3.Row | None:
    """Obtiene una configuración específica de reacción automática."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM auto_reactions WHERE guild_id = ? AND trigger_word = ?",
        (guild_id, trigger_word.lower()),
    ).fetchone()
    conn.close()
    return row


def get_all_auto_reactions(guild_id: int) -> list[sqlite3.Row]:
    """Obtiene todas las configuraciones de reacciones automáticas de un servidor."""
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM auto_reactions WHERE guild_id = ? ORDER BY trigger_word", (guild_id,)
    ).fetchall()
    conn.close()
    return rows


def clear_auto_reactions(guild_id: int):
    """Elimina todas las configuraciones de reacciones automáticas de un servidor."""
    conn = get_db_connection()
    conn.execute("DELETE FROM auto_reactions WHERE guild_id = ?", (guild_id,))
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
    activity_emoji: str | None = None,
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


def list_bot_presence_presets() -> list[sqlite3.Row]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM bot_presence_presets ORDER BY is_active DESC, name COLLATE NOCASE"
    ).fetchall()
    conn.close()
    return rows


def get_bot_presence_preset(name: str) -> sqlite3.Row | None:
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


def get_active_bot_presence_preset() -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM bot_presence_presets WHERE is_active = 1 LIMIT 1").fetchone()
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


# ---------------------------------------------------------------------------
# SUPPORT CASES
# ---------------------------------------------------------------------------
def set_support_settings(
    guild_id: int,
    archive_channel_id: int,
    category_id: int,
    support_role_id: int,
    retention_days: int,
):
    if not 1 <= retention_days <= 90:
        raise ValueError("retention_days debe estar entre 1 y 90")
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO support_settings (
            guild_id, archive_channel_id, category_id, support_role_id, retention_days
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            archive_channel_id = excluded.archive_channel_id,
            category_id = excluded.category_id,
            support_role_id = excluded.support_role_id,
            retention_days = excluded.retention_days
        """,
        (guild_id, archive_channel_id, category_id, support_role_id, retention_days),
    )
    conn.commit()
    conn.close()


def get_support_settings(guild_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM support_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    conn.close()
    return row


def delete_support_settings(guild_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM support_settings WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()


def create_support_case(
    guild_id: int,
    channel_id: int,
    opener_id: int,
    subject: str,
    created_at: str,
) -> int:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO support_cases (guild_id, channel_id, opener_id, subject, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, opener_id, subject, created_at),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def get_support_case_by_channel(channel_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM support_cases WHERE channel_id = ?", (channel_id,)).fetchone()
    conn.close()
    return row


def get_support_case(guild_id: int, case_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM support_cases WHERE guild_id = ? AND case_id = ?",
        (guild_id, case_id),
    ).fetchone()
    conn.close()
    return row


def get_open_support_case_for_user(guild_id: int, opener_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT * FROM support_cases
        WHERE guild_id = ? AND opener_id = ? AND status = 'open'
        ORDER BY case_id DESC
        LIMIT 1
        """,
        (guild_id, opener_id),
    ).fetchone()
    conn.close()
    return row


def delete_support_case_record(case_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM support_cases WHERE case_id = ?", (case_id,))
    conn.commit()
    conn.close()


def get_support_cases_for_guild(guild_id: int, status: str | None = None) -> list[sqlite3.Row]:
    conn = get_db_connection()
    if status is None:
        rows = conn.execute(
            "SELECT * FROM support_cases WHERE guild_id = ? ORDER BY case_id DESC",
            (guild_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM support_cases WHERE guild_id = ? AND status = ? ORDER BY case_id DESC",
            (guild_id, status),
        ).fetchall()
    conn.close()
    return rows


def close_support_case(
    case_id: int,
    archive_channel_id: int,
    archive_message_id: int,
    closed_at: str,
) -> bool:
    conn = get_db_connection()
    cursor = conn.execute(
        """
        UPDATE support_cases
        SET status = 'closed', archive_channel_id = ?, archive_message_id = ?, closed_at = ?
        WHERE case_id = ? AND status = 'open'
        """,
        (archive_channel_id, archive_message_id, closed_at, case_id),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def clear_support_archive(case_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.execute(
        """
        UPDATE support_cases
        SET archive_channel_id = NULL, archive_message_id = NULL
        WHERE case_id = ?
        """,
        (case_id,),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def get_expired_support_archives(now_iso: str) -> list[sqlite3.Row]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.*, s.retention_days
        FROM support_cases AS c
        JOIN support_settings AS s ON s.guild_id = c.guild_id
        WHERE c.status = 'closed'
          AND c.archive_channel_id IS NOT NULL
          AND c.archive_message_id IS NOT NULL
          AND c.closed_at IS NOT NULL
          AND julianday(c.closed_at) <= julianday(?) - s.retention_days
        """,
        (now_iso,),
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# LIVE ACTIVITY LFG
# ---------------------------------------------------------------------------
def set_lfg_settings(guild_id: int, dashboard_channel_id: int):
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO lfg_settings (guild_id, dashboard_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            dashboard_channel_id = excluded.dashboard_channel_id,
            dashboard_message_id = CASE
                WHEN lfg_settings.dashboard_channel_id = excluded.dashboard_channel_id
                THEN lfg_settings.dashboard_message_id
                ELSE NULL
            END
        """,
        (guild_id, dashboard_channel_id),
    )
    conn.commit()
    conn.close()


def get_lfg_settings(guild_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM lfg_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    conn.close()
    return row


def set_lfg_dashboard_message(guild_id: int, message_id: int | None):
    conn = get_db_connection()
    conn.execute(
        "UPDATE lfg_settings SET dashboard_message_id = ? WHERE guild_id = ?",
        (message_id, guild_id),
    )
    conn.commit()
    conn.close()


def delete_lfg_settings(guild_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM lfg_assignments WHERE guild_id = ?", (guild_id,))
    conn.execute("DELETE FROM lfg_enrollments WHERE guild_id = ?", (guild_id,))
    conn.execute("DELETE FROM lfg_games WHERE guild_id = ?", (guild_id,))
    conn.execute("DELETE FROM lfg_settings WHERE guild_id = ?", (guild_id,))
    conn.commit()
    conn.close()


def upsert_lfg_game(
    guild_id: int,
    activity_name: str,
    display_name: str,
    role_id: int,
) -> sqlite3.Row:
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO lfg_games (guild_id, activity_name, display_name, role_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, activity_name) DO UPDATE SET
            display_name = excluded.display_name,
            role_id = excluded.role_id
        """,
        (guild_id, activity_name.strip(), display_name.strip(), role_id),
    )
    row = conn.execute(
        "SELECT * FROM lfg_games WHERE guild_id = ? AND activity_name = ? COLLATE NOCASE",
        (guild_id, activity_name.strip()),
    ).fetchone()
    conn.commit()
    conn.close()
    return row


def get_lfg_games(guild_id: int) -> list[sqlite3.Row]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM lfg_games WHERE guild_id = ? ORDER BY display_name COLLATE NOCASE",
        (guild_id,),
    ).fetchall()
    conn.close()
    return rows


def get_lfg_game_by_activity(guild_id: int, activity_name: str) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM lfg_games WHERE guild_id = ? AND activity_name = ? COLLATE NOCASE",
        (guild_id, activity_name.strip()),
    ).fetchone()
    conn.close()
    return row


def delete_lfg_game(guild_id: int, activity_name: str) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM lfg_games WHERE guild_id = ? AND activity_name = ? COLLATE NOCASE",
        (guild_id, activity_name.strip()),
    ).fetchone()
    if row is not None:
        conn.execute(
            "DELETE FROM lfg_assignments WHERE guild_id = ? AND game_id = ?",
            (guild_id, row["game_id"]),
        )
        conn.execute("DELETE FROM lfg_games WHERE game_id = ?", (row["game_id"],))
        conn.commit()
    conn.close()
    return row


def enroll_lfg_user(guild_id: int, user_id: int, enrolled_at: str):
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO lfg_enrollments (guild_id, user_id, enrolled_at)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO NOTHING
        """,
        (guild_id, user_id, enrolled_at),
    )
    conn.commit()
    conn.close()


def unenroll_lfg_user(guild_id: int, user_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    assignment = conn.execute(
        "SELECT * FROM lfg_assignments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    conn.execute(
        "DELETE FROM lfg_assignments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    conn.execute(
        "DELETE FROM lfg_enrollments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    conn.commit()
    conn.close()
    return assignment


def is_lfg_enrolled(guild_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT 1 FROM lfg_enrollments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_lfg_enrollments(guild_id: int) -> list[sqlite3.Row]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM lfg_enrollments WHERE guild_id = ?",
        (guild_id,),
    ).fetchall()
    conn.close()
    return rows


def set_lfg_assignment(
    guild_id: int,
    user_id: int,
    game_id: int,
    role_id: int,
    assigned_at: str,
):
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO lfg_assignments (guild_id, user_id, game_id, role_id, assigned_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            game_id = excluded.game_id,
            role_id = excluded.role_id,
            assigned_at = excluded.assigned_at
        """,
        (guild_id, user_id, game_id, role_id, assigned_at),
    )
    conn.commit()
    conn.close()


def get_lfg_assignment(guild_id: int, user_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM lfg_assignments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    conn.close()
    return row


def delete_lfg_assignment(guild_id: int, user_id: int) -> sqlite3.Row | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM lfg_assignments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    conn.execute(
        "DELETE FROM lfg_assignments WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    conn.commit()
    conn.close()
    return row


def get_lfg_assignments(guild_id: int) -> list[sqlite3.Row]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT a.*, g.activity_name, g.display_name
        FROM lfg_assignments AS a
        JOIN lfg_games AS g ON g.game_id = a.game_id
        WHERE a.guild_id = ?
        ORDER BY g.display_name COLLATE NOCASE, a.assigned_at
        """,
        (guild_id,),
    ).fetchall()
    conn.close()
    return rows


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


def get_vanity_settings(guild_id: int) -> dict | None:
    """Obtiene la configuración general de vanity."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM vanity_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_vanity_settings(guild_id: int, **kwargs):
    """Guarda la configuración general de vanity."""
    invalid_columns = set(kwargs) - VANITY_SETTING_COLUMNS
    if invalid_columns:
        raise ValueError(f"Columnas de vanity no permitidas: {sorted(invalid_columns)}")

    conn = get_db_connection()

    if not kwargs:
        conn.execute(
            "INSERT OR IGNORE INTO vanity_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
    else:
        columns = ["guild_id", *kwargs.keys()]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(f"{k} = excluded.{k}" for k in kwargs)
        conn.execute(
            f"INSERT INTO vanity_settings ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {update_clause}",
            [guild_id, *kwargs.values()],
        )

    conn.commit()
    conn.close()


def get_vanity_codes(guild_id: int) -> list[dict]:
    """Obtiene todas las vanitys configuradas."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM vanity_codes WHERE guild_id = ?", (guild_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_vanity_code(guild_id: int, vanity_code: str, role_id: int) -> bool:
    """Añade una vanity. Retorna False si ya existe."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO vanity_codes (guild_id, vanity_code, role_id) VALUES (?, ?, ?)",
            (guild_id, vanity_code, role_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except sqlite3.Error:
        conn.close()
        raise


def remove_vanity_code(guild_id: int, vanity_code: str) -> bool:
    """Elimina una vanity. Retorna True si se eliminó."""
    conn = get_db_connection()
    cursor = conn.execute(
        "DELETE FROM vanity_codes WHERE guild_id = ? AND vanity_code = ?", (guild_id, vanity_code)
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


def get_clantag_settings(guild_id: int) -> dict | None:
    """Obtiene la configuración de clan tag."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM clantag_settings WHERE guild_id = ?", (guild_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_clantag_settings(guild_id: int, **kwargs):
    """Guarda la configuración de clan tag."""
    invalid_columns = set(kwargs) - CLANTAG_SETTING_COLUMNS
    if invalid_columns:
        raise ValueError(f"Columnas de clan tag no permitidas: {sorted(invalid_columns)}")

    conn = get_db_connection()

    if not kwargs:
        conn.execute(
            "INSERT OR IGNORE INTO clantag_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
    else:
        columns = ["guild_id", *kwargs.keys()]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(f"{k} = excluded.{k}" for k in kwargs)
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
