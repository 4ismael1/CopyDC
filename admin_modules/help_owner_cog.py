# modules/help_owner_cog.py
import os
from typing import List

import discord
from discord.ext import commands
from discord import ui

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# ─────────────────────────────────────────────────────────────────────────────
# Utils (owner-only + silencio para no-owner)
# ─────────────────────────────────────────────────────────────────────────────

def is_owner_check(ctx: commands.Context) -> bool:
    return ctx.author and ctx.author.id == OWNER_ID

def owner_only():
    return commands.check(is_owner_check)

# ─────────────────────────────────────────────────────────────────────────────
# Embeds por módulo de owner
# ─────────────────────────────────────────────────────────────────────────────

def get_owner_help_embeds() -> List[discord.Embed]:
    # 1) Owner (servers)
    e1 = discord.Embed(
        title="👑 Owner — Servidores",
        description="Herramientas para **listar** e **inspeccionar** servidores desde Discord.",
        color=discord.Color.gold()
    )
    e1.add_field(
        name="`c!servers`",
        value="Abre la **lista interactiva** de servidores (página 1). Usa el menú para elegir un servidor.",
        inline=False
    )
    e1.add_field(
        name="`c!servers list [página]`",
        value="Abre la lista en la página indicada (1-indexed).",
        inline=False
    )
    e1.add_field(
        name="`c!servers info <ID|nombre>`",
        value=(
            "Abre la **ficha del servidor** con pestañas:\n"
            "• Resumen\n• Miembros/Canales\n• Roles/Emojis\n• Seguridad/Nitro\n• Permisos del bot"
        ),
        inline=False
    )
    e1.set_footer(text="Módulo: owner_cog.py")

    # 2) DevTools
    e2 = discord.Embed(
        title="🛠️ DevTools — Gestión de módulos",
        description="Cargar/descargar/recargar cogs en caliente. Solo owner.",
        color=discord.Color.blurple()
    )
    e2.add_field(name="`c!dev`", value="Muestra los subcomandos disponibles.", inline=False)
    e2.add_field(name="`c!dev load <mod>`", value="Carga `modules.<mod>`.", inline=False)
    e2.add_field(name="`c!dev unload <mod>`", value="Descarga el módulo.", inline=False)
    e2.add_field(name="`c!dev reload <mod>`", value="Recarga el módulo (o lo carga si no estaba).", inline=False)
    e2.add_field(name="`c!dev reloadall`", value="Recarga **todos** los módulos cargados.", inline=False)
    e2.add_field(name="`c!dev list [loaded|unloaded|all]`", value="Lista módulos por estado.", inline=False)
    e2.add_field(name="`c!dev info <mod>`", value="Comandos registrados por el Cog.", inline=False)
    e2.set_footer(text="Módulo: devtools_cog.py")

    # 3) Exec (shell)
    e3 = discord.Embed(
        title="💻 Exec — Comandos de shell",
        description="Ejecuta comandos en la shell del servidor (⚠️ uso bajo tu responsabilidad).",
        color=discord.Color.red()
    )
    e3.add_field(
        name="`c!exec <comando>`",
        value=(
            "Ejecuta el comando y devuelve stdout/stderr (truncados si son muy largos).\n"
            "Puedes enviar el comando envuelto en bloque ``` para mayor claridad."
        ),
        inline=False
    )
    e3.add_field(
        name="Timeout",
        value="Corta a los **5 minutos** si el proceso no termina.",
        inline=False
    )
    e3.set_footer(text="Módulo: exec_cog.py")

    # 4) Logging (informativo)
    e4 = discord.Embed(
        title="📜 Logging — Registros a archivo",
        description="Registra eventos y errores en `logs/bot.log` de forma automática.",
        color=discord.Color.teal()
    )
    e4.add_field(
        name="Qué hace",
        value=(
            "• Crea carpeta `logs/` si no existe.\n"
            "• Añade un `FileHandler` al logger `bot`.\n"
            "• Registra `on_ready`, `on_guild_join`, `on_guild_remove` y errores de comandos."
        ),
        inline=False
    )
    e4.add_field(
        name="Comandos",
        value="No expone comandos. Funciona al cargar el Cog.",
        inline=False
    )
    e4.set_footer(text="Módulo: logging_cog.py")

    return [e1, e2, e3, e4]

# ─────────────────────────────────────────────────────────────────────────────
# UI: Menú desplegable (Select) para secciones owner
# ─────────────────────────────────────────────────────────────────────────────

class OwnerHelpSelect(ui.Select):
    def __init__(self, embeds: List[discord.Embed]):
        options = [
            discord.SelectOption(label="Servidores", description="Lista y ficha con pestañas", value="0", emoji="👑"),
            discord.SelectOption(label="DevTools", description="Cargar/recargar módulos", value="1", emoji="🛠️"),
            discord.SelectOption(label="Exec", description="Ejecutar comandos de shell", value="2", emoji="💻"),
            discord.SelectOption(label="Logging", description="Registro en archivo", value="3", emoji="📜"),
        ]
        super().__init__(placeholder="Elige una sección (owner)…", min_values=1, max_values=1, options=options)
        self.embeds = embeds

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.embeds[int(self.values[0])], view=self.view)

class OwnerHelpView(ui.View):
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=180)
        self.add_item(OwnerHelpSelect(embeds))

# ─────────────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────────────

class OwnerHelpCog(commands.Cog):
    """Menú de ayuda para módulos del owner (solo visible para el owner)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Silenciar intentos de no-owner: no responde y no loggea
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, err: commands.CommandError):
        if isinstance(err, commands.CheckFailure) and ctx.command and ctx.command.qualified_name.startswith("ohelp"):
            return  # silencio total

    @commands.command(name="ohelp")
    @owner_only()
    async def owner_help(self, ctx: commands.Context):
        """Muestra el menú de ayuda de módulos exclusivos del owner."""
        embeds = get_owner_help_embeds()
        view = OwnerHelpView(embeds)
        await ctx.reply(embed=embeds[0], view=view, mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerHelpCog(bot))
