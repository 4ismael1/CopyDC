"""Migra las configuraciones JSON de versiones antiguas a SQLite."""

import json
import sqlite3
from argparse import ArgumentParser
from contextlib import closing
from pathlib import Path


def migrate(source_dir: Path, database_file: Path) -> None:
    print("Iniciando migración de JSON a SQLite...")
    database_file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_file)) as conn, conn:
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

        guilds_file = source_dir / "guilds.json"
        if guilds_file.exists():
            guilds_data = json.loads(guilds_file.read_text(encoding="utf-8"))
            for guild_id, guild_name in guilds_data.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO guilds (guild_id, guild_name) VALUES (?, ?)",
                    (int(guild_id), guild_name),
                )
            print(f"✅ Migrados {len(guilds_data)} servidores desde guilds.json.")
        else:
            print("ℹ️ No se encontró guilds.json, se omite.")

        threads_file = source_dir / "thread_channels.json"
        if threads_file.exists():
            threads_data = json.loads(threads_file.read_text(encoding="utf-8"))
            count = 0
            for guild_id, channels in threads_data.items():
                for channel_id, mode in channels.items():
                    cursor.execute(
                        "INSERT OR REPLACE INTO thread_configs (guild_id, channel_id, mode) VALUES (?, ?, ?)",
                        (int(guild_id), int(channel_id), mode),
                    )
                    count += 1
            print(f"✅ Migradas {count} configuraciones de hilos desde thread_channels.json.")
        else:
            print("ℹ️ No se encontró thread_channels.json, se omite.")

    print("Migración completada.")


def main() -> None:
    project_dir = Path(__file__).resolve().parent.parent
    parser = ArgumentParser()
    parser.add_argument("--source", type=Path, default=project_dir)
    parser.add_argument("--database", type=Path, default=project_dir / "bot_database.db")
    args = parser.parse_args()
    migrate(args.source.resolve(), args.database.resolve())


if __name__ == "__main__":
    main()
