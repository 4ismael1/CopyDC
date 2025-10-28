# database.py
import sqlite3
from typing import List, Dict, Tuple, Optional

DB_FILE = "bot_database.db"

def get_db_connection():
    """Crea y devuelve una conexión a la base de datos."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    """Crea las tablas de la base de datos si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
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




