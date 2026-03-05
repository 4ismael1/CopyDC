# migrate.py
import json
import sqlite3

print("Iniciando migración de JSON a SQLite...")

# Conexión a la base de datos y creación de tablas
conn = sqlite3.connect("bot_database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS guilds (
    guild_id INTEGER PRIMARY KEY,
    guild_name TEXT NOT NULL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS thread_configs (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    mode TEXT NOT NULL
)
""")

# Migrar guilds.json
try:
    with open("guilds.json", "r") as f:
        guilds_data = json.load(f)
    
    for guild_id, guild_name in guilds_data.items():
        cursor.execute("INSERT OR REPLACE INTO guilds (guild_id, guild_name) VALUES (?, ?)", (int(guild_id), guild_name))
    print(f"✅ Migrados {len(guilds_data)} servidores desde guilds.json.")
except FileNotFoundError:
    print("ℹ️ No se encontró guilds.json, se omite.")

# Migrar thread_channels.json
try:
    with open("thread_channels.json", "r") as f:
        threads_data = json.load(f)
    
    count = 0
    for guild_id, channels in threads_data.items():
        for channel_id, mode in channels.items():
            cursor.execute("INSERT OR REPLACE INTO thread_configs (guild_id, channel_id, mode) VALUES (?, ?, ?)", (int(guild_id), int(channel_id), mode))
            count += 1
    print(f"✅ Migradas {count} configuraciones de hilos desde thread_channels.json.")
except FileNotFoundError:
    print("ℹ️ No se encontró thread_channels.json, se omite.")

conn.commit()
conn.close()
print("Migración completada.")