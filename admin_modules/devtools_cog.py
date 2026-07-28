# modules/devtools_cog.py
from __future__ import annotations

import os
import traceback
from pathlib import Path

import discord
from discord.ext import commands

# ╭────────────────────────── CONFIG ──────────────────────────╮
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))  # Debe existir en .env
MODULES_DIR: Path = Path(__file__).parent  # /modules

# Colores corporativos
CLR_SUCCESS = discord.Color.green()
CLR_FAIL = discord.Color.red()
CLR_INFO = discord.Color.blurple()


# ╭────────────────────────── UTILS ──────────────────────────╮
def owner_only():
    """Decorator que limita la ejecución al owner."""
    return commands.check(lambda ctx: ctx.author.id == OWNER_ID)


def qname(mod: str) -> str:
    """Devuelve el nombre cualificado ('modules.foo')."""
    return mod if mod.startswith("modules.") else f"modules.{mod}"


def build_embed(title: str, desc: str, color: discord.Color, **fields) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color)
    for k, v in fields.items():
        e.add_field(name=k, value=v, inline=False)
    return e


def list_py_modules() -> list[str]:
    """Lista .py en /modules excluyendo __init__ y archivos dunder."""
    return sorted(p.stem for p in MODULES_DIR.glob("*.py") if not p.stem.startswith("_"))


# ╭────────────────────────── COG ──────────────────────────╮
class DevTools(commands.Cog):
    """Herramientas de mantenimiento para el owner."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ───────── Silenciar intentos de no-owner ─────────
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, err: commands.CommandError):
        if (
            isinstance(err, commands.CheckFailure)
            and ctx.command
            and ctx.command.qualified_name.startswith("dev")
        ):
            return  # ignora en silencio

    # ╭────────── Grupo base: dev ──────────╮
    @commands.group(name="dev", invoke_without_command=True)
    @owner_only()
    async def dev(self, ctx: commands.Context):
        cmds = "`load | unload | reload | reloadall | list | info`"
        await ctx.reply(embed=build_embed("DevTools", f"Subcomandos: {cmds}", CLR_INFO), mention_author=False)

    # ───────── load ─────────
    @dev.command(name="load")
    @owner_only()
    async def load(self, ctx, module: str):
        module = qname(module)
        try:
            await self.bot.load_extension(module)
            await ctx.reply(
                embed=build_embed("✅ Cargado", f"`{module}` se cargó con éxito.", CLR_SUCCESS),
                mention_author=False,
            )
        except Exception as e:
            await ctx.reply(
                embed=build_embed("❌ Error al cargar", f"```py\n{e}```", CLR_FAIL),
                mention_author=False,
            )
            traceback.print_exc()

    # ───────── unload ─────────
    @dev.command(name="unload")
    @owner_only()
    async def unload(self, ctx, module: str):
        module = qname(module)
        try:
            await self.bot.unload_extension(module)
            await ctx.reply(
                embed=build_embed("⏹️ Descargado", f"`{module}` se descargó.", CLR_SUCCESS),
                mention_author=False,
            )
        except Exception as e:
            await ctx.reply(
                embed=build_embed("❌ Error al descargar", f"```py\n{e}```", CLR_FAIL),
                mention_author=False,
            )
            traceback.print_exc()

    # ───────── reload ─────────
    @dev.command(name="reload", aliases=["r"])
    @owner_only()
    async def reload(self, ctx, module: str):
        module = qname(module)
        try:
            await self.bot.reload_extension(module)
            await ctx.reply(
                embed=build_embed("🔄 Recargado", f"`{module}` se recargó.", CLR_SUCCESS),
                mention_author=False,
            )
        except commands.ExtensionNotLoaded:
            # Si no estaba cargado lo carga
            try:
                await self.bot.load_extension(module)
                await ctx.reply(
                    embed=build_embed("ℹ️ No estaba cargado", f"`{module}` se cargó ahora.", CLR_SUCCESS),
                    mention_author=False,
                )
            except Exception as e:
                await ctx.reply(
                    embed=build_embed("❌ Error", f"```py\n{e}```", CLR_FAIL), mention_author=False
                )
                traceback.print_exc()
        except Exception as e:
            await ctx.reply(embed=build_embed("❌ Error", f"```py\n{e}```", CLR_FAIL), mention_author=False)
            traceback.print_exc()

    # ───────── reload all ─────────
    @dev.command(name="reloadall", aliases=["ra"])
    @owner_only()
    async def reload_all(self, ctx):
        successes, fails = [], []
        for mod in list(self.bot.extensions):
            try:
                await self.bot.reload_extension(mod)
                successes.append(mod)
            except Exception as e:
                fails.append((mod, e))
                traceback.print_exc()

        msg = f"**Recargados:** {len(successes)}\n**Errores:** {len(fails)}"
        embed = build_embed("🔄 Recarga global completa", msg, CLR_INFO)
        if successes:
            embed.add_field(name="✔️ Éxitos", value="\n".join(successes)[:1024], inline=False)
        if fails:
            txt = "\n".join(f"{m} → {e}" for m, e in fails)[:1024]
            embed.add_field(name="❌ Fallos", value=txt, inline=False)
        await ctx.reply(embed=embed, mention_author=False)

    # ───────── list ─────────
    @dev.command(name="list")
    @owner_only()
    async def list_mods(self, ctx, scope: str = "loaded"):
        """scope: loaded | unloaded | all"""
        loaded = set(self.bot.extensions)
        all_files = list_py_modules()

        if scope == "loaded":
            items = sorted(loaded)
        elif scope == "unloaded":
            items = sorted(qname(m) for m in all_files if qname(m) not in loaded)
        else:
            items = [f"✅ {m}" if m in loaded else f"— {m}" for m in (qname(f) for f in all_files)]

        desc = "\n".join(items) or "—"
        await ctx.reply(
            embed=build_embed("📄 Lista de módulos", desc[:4000], CLR_INFO),
            mention_author=False,
        )

    # ───────── info ─────────
    @dev.command(name="info")
    @owner_only()
    async def info(self, ctx, module: str):
        """Muestra comandos registrados por un Cog."""
        module = qname(module)
        cog = next((c for c in self.bot.cogs.values() if c.__module__ == module), None)
        if not cog:
            await ctx.reply(embed=build_embed("🚫 No cargado", f"`{module}` no está activo.", CLR_FAIL))
            return

        # Reúne comandos del Cog
        cmds = [c for c in self.bot.walk_commands() if c.cog_name == cog.qualified_name]
        lines = [f"• **{c.qualified_name}** → {c.help or '_sin descripción_'}" for c in cmds][:50]
        embed = build_embed(
            f"ℹ️ Información de {module}",
            f"Comandos: **{len(cmds)}**",
            CLR_INFO,
            Ejemplos="\n".join(lines) or "—",
        )
        await ctx.reply(embed=embed, mention_author=False)


# ╭────────────────────────── SETUP ──────────────────────────╮
async def setup(bot: commands.Bot):
    await bot.add_cog(DevTools(bot))
