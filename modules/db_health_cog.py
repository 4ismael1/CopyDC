import json
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Any, Dict, Optional

import discord
from discord.ext import commands, tasks

import database as db


READ_DB_FUNCS = {
    "get_all_guilds",
    "get_thread_config_for_channel",
    "get_all_thread_configs_for_guild",
    "get_counting_channel",
    "get_boost_roles_for_guild",
    "get_linked_roles_for_guild",
    "get_boost_log_channel",
    "get_boost_role",
    "get_auto_reaction",
    "get_all_auto_reactions",
    "get_vanity_settings",
    "get_vanity_codes",
    "get_clantag_settings",
}

WRITE_DB_FUNCS = {
    "setup_database",
    "sync_guilds",
    "add_guild",
    "remove_guild",
    "add_thread_config",
    "remove_thread_config",
    "set_counting_channel",
    "update_count",
    "reset_count",
    "add_boost_role",
    "set_boost_log_channel",
    "delete_boost_role",
    "add_auto_reaction",
    "remove_auto_reaction",
    "clear_auto_reactions",
    "setup_vanity_table",
    "set_vanity_settings",
    "add_vanity_code",
    "remove_vanity_code",
    "delete_all_vanity",
    "setup_clantag_table",
    "set_clantag_settings",
    "delete_clantag_settings",
}


class DBHealthCog(commands.Cog):
    """
    Monitorea tráfico del bot y operaciones reales a SQLite para decidir
    cuándo mantener SQLite y cuándo migrar a PostgreSQL/MySQL.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = threading.RLock()
        self._started_at = time.time()
        self._last_sqlite_snapshot: Dict[str, Any] = {}
        self._latency_samples_ms: deque[float] = deque(maxlen=5000)

        self._db_stats: Dict[str, Any] = {
            "ops_total": 0,
            "reads": 0,
            "writes": 0,
            "errors": 0,
            "locked_errors": 0,
            "total_ms": 0.0,
            "max_ms": 0.0,
            "by_op": {},
        }

        self._traffic_totals: Dict[str, int] = {
            "messages": 0,
            "commands": 0,
            "presence_updates": 0,
            "member_updates": 0,
        }
        self._traffic_by_guild: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {
                "messages": 0,
                "commands": 0,
                "presence_updates": 0,
                "member_updates": 0,
            }
        )

        self._patch_database_layer()
        self._refresh_sqlite_snapshot()
        self.sqlite_sampler.start()

    def cog_unload(self):
        self.sqlite_sampler.cancel()
        self._unpatch_database_layer()

    # ------------------------------------------------------------------
    # Safe monkey patch for database.py
    # ------------------------------------------------------------------
    def _patch_database_layer(self):
        state = getattr(db, "_db_health_probe_state", None)
        if state is None:
            state = {"refcount": 0, "originals": {}}
            setattr(db, "_db_health_probe_state", state)

        state["refcount"] += 1
        if state["refcount"] > 1:
            return

        for func_name in READ_DB_FUNCS | WRITE_DB_FUNCS:
            original = getattr(db, func_name, None)
            if not callable(original):
                continue

            state["originals"][func_name] = original
            kind = "read" if func_name in READ_DB_FUNCS else "write"

            @wraps(original)
            def wrapper(*args, __func_name=func_name, __kind=kind, __original=original, **kwargs):
                started = time.perf_counter()
                error: Optional[Exception] = None
                try:
                    return __original(*args, **kwargs)
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    self._record_db_call(__func_name, __kind, elapsed_ms, error)

            setattr(db, func_name, wrapper)

    def _unpatch_database_layer(self):
        state = getattr(db, "_db_health_probe_state", None)
        if not state:
            return

        state["refcount"] -= 1
        if state["refcount"] > 0:
            return

        for func_name, original in state["originals"].items():
            setattr(db, func_name, original)
        state["originals"].clear()

    # ------------------------------------------------------------------
    # Runtime recording
    # ------------------------------------------------------------------
    def _record_db_call(self, func_name: str, kind: str, elapsed_ms: float, error: Optional[Exception]):
        with self._lock:
            self._db_stats["ops_total"] += 1
            if kind == "write":
                self._db_stats["writes"] += 1
            else:
                self._db_stats["reads"] += 1

            self._db_stats["total_ms"] += elapsed_ms
            self._db_stats["max_ms"] = max(self._db_stats["max_ms"], elapsed_ms)
            self._latency_samples_ms.append(elapsed_ms)

            op = self._db_stats["by_op"].get(func_name)
            if op is None:
                op = {
                    "kind": kind,
                    "count": 0,
                    "errors": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                }
                self._db_stats["by_op"][func_name] = op
            op["count"] += 1
            op["total_ms"] += elapsed_ms
            op["max_ms"] = max(op["max_ms"], elapsed_ms)

            if error is not None:
                self._db_stats["errors"] += 1
                op["errors"] += 1
                if "locked" in str(error).lower():
                    self._db_stats["locked_errors"] += 1

    def _record_traffic(self, kind: str, guild_id: Optional[int]):
        with self._lock:
            self._traffic_totals[kind] += 1
            if guild_id is not None:
                self._traffic_by_guild[guild_id][kind] += 1

    @commands.Cog.listener("on_message")
    async def on_message_probe(self, message: discord.Message):
        if message.author.bot:
            return
        self._record_traffic("messages", message.guild.id if message.guild else None)

    @commands.Cog.listener("on_command_completion")
    async def on_command_completion_probe(self, ctx: commands.Context):
        self._record_traffic("commands", ctx.guild.id if ctx.guild else None)

    @commands.Cog.listener("on_presence_update")
    async def on_presence_update_probe(self, before: discord.Member, after: discord.Member):
        self._record_traffic("presence_updates", after.guild.id if after.guild else None)

    @commands.Cog.listener("on_member_update")
    async def on_member_update_probe(self, before: discord.Member, after: discord.Member):
        self._record_traffic("member_updates", after.guild.id if after.guild else None)

    # ------------------------------------------------------------------
    # SQLite system snapshot
    # ------------------------------------------------------------------
    @tasks.loop(minutes=1)
    async def sqlite_sampler(self):
        self._refresh_sqlite_snapshot()

    @sqlite_sampler.before_loop
    async def before_sqlite_sampler(self):
        await self.bot.wait_until_ready()

    def _refresh_sqlite_snapshot(self):
        db_file = getattr(db, "DB_FILE", "bot_database.db")
        snapshot: Dict[str, Any] = {"db_file": db_file, "exists": os.path.exists(db_file)}

        if not snapshot["exists"]:
            with self._lock:
                self._last_sqlite_snapshot = snapshot
            return

        snapshot["size_bytes"] = os.path.getsize(db_file)
        conn = None
        try:
            conn = sqlite3.connect(db_file, timeout=5)
            cur = conn.cursor()
            snapshot["journal_mode"] = cur.execute("PRAGMA journal_mode").fetchone()[0]
            snapshot["synchronous"] = cur.execute("PRAGMA synchronous").fetchone()[0]
            snapshot["busy_timeout"] = cur.execute("PRAGMA busy_timeout").fetchone()[0]
            snapshot["page_size"] = cur.execute("PRAGMA page_size").fetchone()[0]
            snapshot["page_count"] = cur.execute("PRAGMA page_count").fetchone()[0]
            snapshot["freelist_count"] = cur.execute("PRAGMA freelist_count").fetchone()[0]
        except Exception as exc:
            snapshot["error"] = str(exc)
        finally:
            if conn is not None:
                conn.close()

        with self._lock:
            self._last_sqlite_snapshot = snapshot

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def _p95_latency_ms(self) -> float:
        with self._lock:
            if not self._latency_samples_ms:
                return 0.0
            values = sorted(self._latency_samples_ms)
        idx = int(0.95 * (len(values) - 1))
        return values[idx]

    def _snapshot(self) -> Dict[str, Any]:
        with self._lock:
            uptime_sec = max(time.time() - self._started_at, 0.001)
            totals = dict(self._db_stats)
            traffic = dict(self._traffic_totals)
            sqlite_info = dict(self._last_sqlite_snapshot)
            top_ops_raw = []
            for op_name, data in totals["by_op"].items():
                count = data["count"]
                top_ops_raw.append(
                    {
                        "op": op_name,
                        "kind": data["kind"],
                        "count": count,
                        "errors": data["errors"],
                        "avg_ms": (data["total_ms"] / count) if count else 0.0,
                        "max_ms": data["max_ms"],
                    }
                )
            top_ops_raw.sort(key=lambda x: x["count"], reverse=True)

            guild_rows = []
            for guild_id, gdata in self._traffic_by_guild.items():
                guild_rows.append(
                    {
                        "guild_id": guild_id,
                        "messages": gdata["messages"],
                        "commands": gdata["commands"],
                        "presence_updates": gdata["presence_updates"],
                        "member_updates": gdata["member_updates"],
                    }
                )
            guild_rows.sort(key=lambda x: x["messages"], reverse=True)

        ops = totals["ops_total"]
        avg_ms = (totals["total_ms"] / ops) if ops else 0.0

        return {
            "uptime_sec": uptime_sec,
            "db": {
                "ops_total": ops,
                "reads": totals["reads"],
                "writes": totals["writes"],
                "errors": totals["errors"],
                "locked_errors": totals["locked_errors"],
                "avg_ms": avg_ms,
                "max_ms": totals["max_ms"],
                "p95_ms": self._p95_latency_ms(),
                "ops_per_min": ops / (uptime_sec / 60.0),
                "reads_per_min": totals["reads"] / (uptime_sec / 60.0),
                "writes_per_min": totals["writes"] / (uptime_sec / 60.0),
                "top_ops": top_ops_raw[:10],
            },
            "traffic": {
                **traffic,
                "messages_per_min": traffic["messages"] / (uptime_sec / 60.0),
                "commands_per_min": traffic["commands"] / (uptime_sec / 60.0),
                "presence_per_min": traffic["presence_updates"] / (uptime_sec / 60.0),
                "member_updates_per_min": traffic["member_updates"] / (uptime_sec / 60.0),
                "top_guilds": guild_rows[:10],
            },
            "sqlite": sqlite_info,
        }

    def _recommendation(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        dbs = snapshot["db"]
        reasons = []
        level = "green"

        if dbs["locked_errors"] >= 3:
            level = "red"
            reasons.append(f"{dbs['locked_errors']} errores de lock detectados.")
        elif dbs["locked_errors"] > 0:
            level = "orange"
            reasons.append(f"{dbs['locked_errors']} errores de lock detectados.")

        if dbs["writes_per_min"] >= 180:
            level = "red"
            reasons.append(f"Escrituras muy altas ({dbs['writes_per_min']:.1f}/min).")
        elif dbs["writes_per_min"] >= 80 and level in ("green", "yellow"):
            level = "orange"
            reasons.append(f"Escrituras altas ({dbs['writes_per_min']:.1f}/min).")
        elif dbs["writes_per_min"] >= 40 and level == "green":
            level = "yellow"
            reasons.append(f"Escrituras moderadas ({dbs['writes_per_min']:.1f}/min).")

        if dbs["p95_ms"] >= 40:
            level = "red"
            reasons.append(f"P95 de latencia alto ({dbs['p95_ms']:.2f} ms).")
        elif dbs["p95_ms"] >= 20 and level in ("green", "yellow"):
            level = "orange"
            reasons.append(f"P95 de latencia elevado ({dbs['p95_ms']:.2f} ms).")
        elif dbs["avg_ms"] >= 8 and level == "green":
            level = "yellow"
            reasons.append(f"Latencia promedio moderada ({dbs['avg_ms']:.2f} ms).")

        if dbs["errors"] >= 10:
            level = "red"
            reasons.append(f"Errores de DB altos ({dbs['errors']}).")

        if not reasons:
            reasons.append("Sin señales de saturación.")

        if level == "green":
            summary = "SQLite saludable para la carga actual."
            action = "Mantener SQLite y continuar monitoreo."
            keep_sqlite = True
            color = 0x57F287
        elif level == "yellow":
            summary = "SQLite viable, pero con presión creciente."
            action = "Mantener SQLite, optimizar y vigilar tendencia."
            keep_sqlite = True
            color = 0xFEE75C
        elif level == "orange":
            summary = "SQLite en zona de riesgo."
            action = "Preparar migración a PostgreSQL/MySQL."
            keep_sqlite = False
            color = 0xFAA61A
        else:
            summary = "SQLite en condición crítica para este patrón."
            action = "Migrar cuanto antes a PostgreSQL/MySQL."
            keep_sqlite = False
            color = 0xED4245

        return {
            "level": level,
            "summary": summary,
            "action": action,
            "reasons": reasons,
            "keep_sqlite": keep_sqlite,
            "color": color,
        }

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def _can_use_commands(self, ctx: commands.Context) -> bool:
        if ctx.author.id == ctx.bot.owner_id:
            return True
        if ctx.guild is None:
            return False
        perms = ctx.author.guild_permissions
        return perms.administrator or perms.manage_guild

    @commands.group(name="dbhealth", invoke_without_command=True)
    async def dbhealth(self, ctx: commands.Context):
        """Reporte profesional de tráfico/rendimiento SQLite."""
        if not self._can_use_commands(ctx):
            await ctx.reply("No tienes permisos para usar este módulo.", mention_author=False)
            return
        await self._send_summary(ctx)

    @dbhealth.command(name="top")
    async def dbhealth_top(self, ctx: commands.Context):
        if not self._can_use_commands(ctx):
            await ctx.reply("No tienes permisos para usar este módulo.", mention_author=False)
            return

        snap = self._snapshot()
        rows = snap["db"]["top_ops"]
        if not rows:
            await ctx.reply("Aún no hay operaciones DB registradas.", mention_author=False)
            return

        lines = []
        for item in rows[:10]:
            lines.append(
                f"{item['op']} [{item['kind']}] | count={item['count']} | "
                f"avg={item['avg_ms']:.2f}ms | max={item['max_ms']:.2f}ms | err={item['errors']}"
            )
        text = "```txt\n" + "\n".join(lines) + "\n```"
        await ctx.reply(text, mention_author=False)

    @dbhealth.command(name="guilds")
    async def dbhealth_guilds(self, ctx: commands.Context):
        if not self._can_use_commands(ctx):
            await ctx.reply("No tienes permisos para usar este módulo.", mention_author=False)
            return

        snap = self._snapshot()
        rows = snap["traffic"]["top_guilds"]
        if not rows:
            await ctx.reply("Aún no hay tráfico por servidores registrado.", mention_author=False)
            return

        lines = []
        for item in rows[:10]:
            guild = self.bot.get_guild(item["guild_id"])
            gname = guild.name if guild else str(item["guild_id"])
            lines.append(
                f"{gname} | msg={item['messages']} | cmd={item['commands']} | "
                f"presence={item['presence_updates']} | member_upd={item['member_updates']}"
            )
        text = "```txt\n" + "\n".join(lines) + "\n```"
        await ctx.reply(text, mention_author=False)

    @dbhealth.command(name="raw")
    async def dbhealth_raw(self, ctx: commands.Context):
        if not self._can_use_commands(ctx):
            await ctx.reply("No tienes permisos para usar este módulo.", mention_author=False)
            return

        snap = self._snapshot()
        rec = self._recommendation(snap)
        payload = {"snapshot": snap, "recommendation": rec}
        pretty = json.dumps(payload, indent=2, ensure_ascii=False)
        if len(pretty) <= 3500:
            await ctx.reply(f"```json\n{pretty}\n```", mention_author=False)
            return

        filename = "dbhealth_report.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(pretty)
        await ctx.reply(file=discord.File(filename), mention_author=False)
        try:
            os.remove(filename)
        except OSError:
            pass

    @dbhealth.command(name="reset")
    async def dbhealth_reset(self, ctx: commands.Context):
        if ctx.author.id != ctx.bot.owner_id:
            await ctx.reply("Solo el owner puede resetear métricas.", mention_author=False)
            return

        with self._lock:
            self._started_at = time.time()
            self._latency_samples_ms.clear()
            self._db_stats = {
                "ops_total": 0,
                "reads": 0,
                "writes": 0,
                "errors": 0,
                "locked_errors": 0,
                "total_ms": 0.0,
                "max_ms": 0.0,
                "by_op": {},
            }
            self._traffic_totals = {
                "messages": 0,
                "commands": 0,
                "presence_updates": 0,
                "member_updates": 0,
            }
            self._traffic_by_guild = defaultdict(
                lambda: {
                    "messages": 0,
                    "commands": 0,
                    "presence_updates": 0,
                    "member_updates": 0,
                }
            )
        self._refresh_sqlite_snapshot()
        await ctx.reply("Métricas de DB health reiniciadas.", mention_author=False)

    async def _send_summary(self, ctx: commands.Context):
        snap = self._snapshot()
        rec = self._recommendation(snap)
        dbs = snap["db"]
        trf = snap["traffic"]
        sql = snap["sqlite"]

        embed = discord.Embed(
            title="📊 DB Health Monitor",
            description=f"**Estado:** `{rec['level'].upper()}`\n{rec['summary']}",
            color=rec["color"],
        )
        embed.add_field(
            name="DB Operaciones",
            value=(
                f"Total: **{dbs['ops_total']}**\n"
                f"Reads: **{dbs['reads']}** | Writes: **{dbs['writes']}**\n"
                f"Errores: **{dbs['errors']}** | Locks: **{dbs['locked_errors']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="DB Rendimiento",
            value=(
                f"Avg: **{dbs['avg_ms']:.2f}ms**\n"
                f"P95: **{dbs['p95_ms']:.2f}ms**\n"
                f"Max: **{dbs['max_ms']:.2f}ms**"
            ),
            inline=True,
        )
        embed.add_field(
            name="DB Rate (/min)",
            value=(
                f"Ops: **{dbs['ops_per_min']:.1f}**\n"
                f"Reads: **{dbs['reads_per_min']:.1f}**\n"
                f"Writes: **{dbs['writes_per_min']:.1f}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Tráfico Bot (/min)",
            value=(
                f"Msg: **{trf['messages_per_min']:.1f}**\n"
                f"Cmd: **{trf['commands_per_min']:.1f}**\n"
                f"Presence: **{trf['presence_per_min']:.1f}**"
            ),
            inline=True,
        )
        if sql.get("exists"):
            embed.add_field(
                name="SQLite Runtime",
                value=(
                    f"Modo: **{sql.get('journal_mode', 'n/a')}**\n"
                    f"Synchronous: **{sql.get('synchronous', 'n/a')}**\n"
                    f"Size: **{(sql.get('size_bytes', 0) / (1024*1024)):.2f} MB**"
                ),
                inline=True,
            )
        else:
            embed.add_field(name="SQLite Runtime", value="DB file no encontrado.", inline=True)

        embed.add_field(
            name="Recomendación",
            value=f"{rec['action']}\n" + "\n".join(f"• {r}" for r in rec["reasons"]),
            inline=False,
        )
        embed.set_footer(
            text=(
                "Comandos: c!dbhealth top | c!dbhealth guilds | "
                "c!dbhealth raw | c!dbhealth reset"
            )
        )
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(DBHealthCog(bot))

