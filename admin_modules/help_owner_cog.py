import os
from typing import List

import discord
from discord import ui
from discord.ext import commands

OWNER_ID = int(os.getenv("OWNER_ID", "0"))


def is_owner_check(ctx: commands.Context) -> bool:
    return ctx.author and ctx.author.id == OWNER_ID


def owner_only():
    return commands.check(is_owner_check)


def get_owner_help_embeds() -> List[discord.Embed]:
    overview = discord.Embed(
        title="Owner Help - Resumen",
        description="Comandos de admin cargados actualmente en el bot.",
        color=discord.Color.gold(),
    )
    overview.add_field(
        name="Owner Core",
        value=(
            "`c!servers`\n"
            "`c!slashsync [global|guild|all]`\n"
            "`c!presence`\n"
            "`c!ohelp`"
        ),
        inline=False,
    )
    overview.add_field(
        name="DevTools",
        value="`c!dev`, `dev load`, `dev unload`, `dev reload`, `dev reloadall`, `dev list`, `dev info`",
        inline=False,
    )
    overview.add_field(
        name="DB Health",
        value="`c!dbhealth`, `dbhealth top`, `dbhealth guilds`, `dbhealth raw`, `dbhealth reset`",
        inline=False,
    )
    overview.add_field(
        name="Perm Inspector",
        value="`c!modcheck`, `modcheckall`, `why_modview`, `roleperms`, `auditroles`, `whocan`",
        inline=False,
    )
    overview.add_field(
        name="Logging",
        value="Sin comandos. Registra `on_ready`, `on_guild_join`, `on_guild_remove` y errores.",
        inline=False,
    )
    overview.set_footer(text="Ayuda generada para los admin_modules activos")

    owner_core = discord.Embed(
        title="Owner Core",
        description="Inspeccion global del bot, sync y presencia.",
        color=discord.Color.blurple(),
    )
    owner_core.add_field(
        name="`c!servers` / `!servers`",
        value="Abre la lista interactiva de servidores.",
        inline=False,
    )
    owner_core.add_field(
        name="`servers list [pagina]`",
        value="Abre la pagina indicada de la lista.",
        inline=False,
    )
    owner_core.add_field(
        name="`servers info <id|nombre>`",
        value="Muestra la ficha del servidor con resumen, canales, roles, seguridad y permisos del bot.",
        inline=False,
    )
    owner_core.add_field(
        name="`c!slashsync [global|guild|all]` / `!slashsync ...`",
        value="Sincroniza slash commands globalmente, en el guild actual o en ambos alcances.",
        inline=False,
    )
    owner_core.add_field(
        name="`c!presence` / `!presence`",
        value=(
            "`custom <estado> <texto>` activa un status custom al instante.\n"
            "`custom <estado> <emoji unicode> | <texto>` añade emoji visible.\n"
            "`add <nombre> <tipo> <estado> <texto>` crea o actualiza presets.\n"
            "`add <nombre> custom <estado> <emoji unicode> | <texto>` guarda preset custom.\n"
            "`set <nombre>`, `list`, `remove <nombre>`, `clear` administran presets."
        ),
        inline=False,
    )
    owner_core.add_field(
        name="Tipos y estados",
        value="Tipos: `custom`, `playing`, `listening`, `watching`, `competing`. Estados: `online`, `idle`, `dnd`, `invisible`.",
        inline=False,
    )
    owner_core.add_field(
        name="Nota",
        value="Discord no muestra custom emojis de servidor en el status de bots. Usa unicode, por ejemplo `🔗`.",
        inline=False,
    )
    owner_core.set_footer(text="Modulo: owner_cog.py")

    devtools = discord.Embed(
        title="DevTools",
        description="Carga y recarga de modulos de usuario en caliente.",
        color=discord.Color.teal(),
    )
    devtools.add_field(name="`c!dev` / `!dev`", value="Muestra los subcomandos del modulo.", inline=False)
    devtools.add_field(name="`dev load <mod>`", value="Carga `modules.<mod>`.", inline=False)
    devtools.add_field(name="`dev unload <mod>`", value="Descarga `modules.<mod>`.", inline=False)
    devtools.add_field(name="`dev reload <mod>`", value="Recarga el modulo o lo carga si no estaba activo.", inline=False)
    devtools.add_field(name="`dev reloadall`", value="Recarga todas las extensiones cargadas.", inline=False)
    devtools.add_field(name="`dev list [loaded|unloaded|all]`", value="Lista modulos por estado.", inline=False)
    devtools.add_field(name="`dev info <mod>`", value="Muestra el cog cargado y sus comandos registrados.", inline=False)
    devtools.set_footer(text="Modulo: devtools_cog.py")

    db_health = discord.Embed(
        title="DB Health",
        description="Monitor de SQLite, trafico y recomendacion de escalado.",
        color=discord.Color.green(),
    )
    db_health.add_field(name="`c!dbhealth` / `!dbhealth`", value="Resumen ejecutivo del estado de DB y trafico.", inline=False)
    db_health.add_field(name="`dbhealth top`", value="Top de operaciones de DB por frecuencia y latencia.", inline=False)
    db_health.add_field(name="`dbhealth guilds`", value="Top de servidores por trafico medido por el monitor.", inline=False)
    db_health.add_field(name="`dbhealth raw`", value="Reporte JSON completo del snapshot y la recomendacion.", inline=False)
    db_health.add_field(name="`dbhealth reset`", value="Resetea metricas acumuladas del monitor.", inline=False)
    db_health.set_footer(text="Modulo: db_health_cog.py")

    perms = discord.Embed(
        title="Permission Inspector",
        description="Auditoria de permisos de moderacion y gestion.",
        color=discord.Color.orange(),
    )
    perms.add_field(name="`c!modcheck [@usuario] [#canal]`", value="Permisos efectivos en el canal actual o indicado.", inline=False)
    perms.add_field(name="`c!modcheckall [@usuario]`", value="Auditoria completa del servidor para ese usuario.", inline=False)
    perms.add_field(name="`c!why_modview [@usuario]`", value="Explica por que ese usuario ve la UI de moderacion.", inline=False)
    perms.add_field(name="`c!roleperms @rol`", value="Lista permisos de gestion/moderacion del rol.", inline=False)
    perms.add_field(name="`c!auditroles`", value="Audita roles con permisos de gestion y cuantos miembros los tienen.", inline=False)
    perms.add_field(
        name="`c!whocan <permiso> [#canal]`",
        value=(
            "Muestra quien tiene un permiso concreto.\n"
            "Permisos validos: `administrator`, `manage_guild`, `manage_channels`, "
            "`manage_roles`, `manage_webhooks`, `manage_emojis`, `manage_emojis_and_stickers`, "
            "`manage_events`, `manage_threads`, `manage_nicknames`, `view_audit_log`, "
            "`manage_messages`, `moderate_members`, `kick_members`, `ban_members`, "
            "`move_members`, `mute_members`, `deafen_members`."
        ),
        inline=False,
    )
    perms.set_footer(text="Modulo: perm_inspector_cog.py")

    logging_info = discord.Embed(
        title="Logging",
        description="Registro automatico a archivo para eventos clave del bot.",
        color=discord.Color.dark_teal(),
    )
    logging_info.add_field(
        name="Que registra",
        value="`on_ready`, `on_guild_join`, `on_guild_remove` y errores de comandos.",
        inline=False,
    )
    logging_info.add_field(
        name="Archivo",
        value="Se escribe en `logs/bot.log` cuando el cog esta cargado.",
        inline=False,
    )
    logging_info.add_field(
        name="Comandos",
        value="No expone comandos interactivos.",
        inline=False,
    )
    logging_info.set_footer(text="Modulo: logging_cog.py")

    return [overview, owner_core, devtools, db_health, perms, logging_info]


class OwnerHelpSelect(ui.Select):
    def __init__(self, embeds: List[discord.Embed]):
        options = [
            discord.SelectOption(label="Resumen", description="Todos los comandos admin activos", value="0"),
            discord.SelectOption(label="Owner Core", description="Servers, slashsync y presence", value="1"),
            discord.SelectOption(label="DevTools", description="Carga y recarga de modulos", value="2"),
            discord.SelectOption(label="DB Health", description="Monitor SQLite y trafico", value="3"),
            discord.SelectOption(label="Perm Inspector", description="Auditoria de permisos", value="4"),
            discord.SelectOption(label="Logging", description="Registro en archivo", value="5"),
        ]
        super().__init__(placeholder="Elige una seccion owner...", min_values=1, max_values=1, options=options)
        self.embeds = embeds

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.embeds[int(self.values[0])], view=self.view)


class OwnerHelpView(ui.View):
    def __init__(self, embeds: List[discord.Embed]):
        super().__init__(timeout=180)
        self.add_item(OwnerHelpSelect(embeds))


class OwnerHelpCog(commands.Cog):
    """Menu de ayuda para modulos del owner."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, err: commands.CommandError):
        if isinstance(err, commands.CheckFailure) and ctx.command and ctx.command.qualified_name.startswith("ohelp"):
            return

    @commands.command(name="ohelp")
    @owner_only()
    async def owner_help(self, ctx: commands.Context):
        """Muestra el menu de ayuda de modulos exclusivos del owner."""
        embeds = get_owner_help_embeds()
        view = OwnerHelpView(embeds)
        await ctx.reply(embed=embeds[0], view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerHelpCog(bot))
