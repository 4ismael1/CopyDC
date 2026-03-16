import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import database as db
from command_utils import build_presence_activity, resolve_presence_status, send_response
from modules.help_cog import resolve_help_language

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
BASE_DIR = Path(__file__).resolve().parent
USER_MODULES_DIR = BASE_DIR / "modules"
ADMIN_MODULES_DIR = BASE_DIR / "admin_modules"
TEXT_PREFIXES = ("c!", "!")


class BotConsoleFormatter(logging.Formatter):
    RESET = "\033[0m"
    DIM = "\033[2m"
    COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[95m",
    }
    ICONS = {
        logging.DEBUG: "[.]",
        logging.INFO: "[OK]",
        logging.WARNING: "[!]",
        logging.ERROR: "[X]",
        logging.CRITICAL: "[X]",
    }

    def __init__(self, use_color: bool):
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        timestamp = self.formatTime(record, "%H:%M:%S")
        icon = self.ICONS.get(record.levelno, "•")
        level = record.levelname
        if self.use_color:
            color = self.COLORS.get(record.levelno, "")
            return f"{self.DIM}{timestamp}{self.RESET} {color}{icon} {level}{self.RESET} | {message}"
        return f"{timestamp} {icon} {level} | {message}"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(getattr(handler, "_copy_console_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler._copy_console_handler = True
        handler.setLevel(logging.INFO)
        handler.setFormatter(BotConsoleFormatter(use_color=os.getenv("NO_COLOR") is None))
        logger.addHandler(handler)

    return logger


log = configure_logging()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guild_messages = True
intents.presences = True


def total_users_all_guilds(bot: commands.Bot) -> int:
    return sum((guild.member_count or 0) for guild in bot.guilds)


def format_permissions(perms: list[str]) -> str:
    readable_names = {
        "administrator": "Administrador",
        "manage_guild": "Gestionar servidor",
        "manage_channels": "Gestionar canales",
        "manage_roles": "Gestionar roles",
        "manage_messages": "Gestionar mensajes",
        "manage_expressions": "Gestionar expresiones",
        "view_audit_log": "Ver registro de auditoria",
        "add_reactions": "Anadir reacciones",
        "send_messages": "Enviar mensajes",
        "embed_links": "Insertar enlaces",
    }
    return ", ".join(readable_names.get(perm, perm.replace("_", " ")) for perm in perms)


def build_welcome_embed(bot_user: discord.ClientUser, guild: discord.Guild, *, lang: str) -> discord.Embed:
    if lang == "en":
        embed = discord.Embed(
            title=f"Thanks for inviting {bot_user.display_name}",
            description=(
                "Start with `c!help`, `!help`, or `/help`.\n"
                "The bot supports text commands and slash commands for faster setup."
            ),
            color=0x5865F2,
        )
        embed.add_field(
            name="Quick start",
            value=(
                "`/help` or `c!help`\n"
                "`/thread add` for auto threads\n"
                "`/counting set` for counting\n"
                "`/react add` for automatic reactions"
            ),
            inline=False,
        )
        embed.add_field(
            name="Setup modules",
            value=(
                "`/thread`, `/counting`, `/react`\n"
                "`/vanity`, `/clantag`, `/boostrole`\n"
                "They also work with `c!` and `!`."
            ),
            inline=False,
        )
        embed.add_field(
            name="Before you start",
            value=(
                "Place the bot role above the roles it will assign.\n"
                "Give it permissions to send messages, embed links, manage roles, and manage channels depending on the module."
            ),
            inline=False,
        )
        embed.set_footer(
            text=f"Server: {guild.name} | If slash commands do not appear immediately, wait a few seconds and try again."
        )
        return embed

    embed = discord.Embed(
        title=f"Gracias por invitar a {bot_user.display_name}",
        description=(
            "Empieza con `c!help`, `!help` o `/help`.\n"
            "El bot mantiene comandos de texto y ahora tambien slash commands para configurarlo mas rapido."
        ),
        color=0x5865F2,
    )
    embed.add_field(
        name="Inicio rapido",
        value=(
            "`/help` o `c!help`\n"
            "`/thread add` para hilos automaticos\n"
            "`/counting set` para conteo\n"
            "`/react add` para reacciones automaticas"
        ),
        inline=False,
    )
    embed.add_field(
        name="Modulos de configuracion",
        value=(
            "`/thread`, `/counting`, `/react`\n"
            "`/vanity`, `/clantag`, `/boostrole`\n"
            "Tambien funcionan con `c!` y `!`."
        ),
        inline=False,
    )
    embed.add_field(
        name="Antes de empezar",
        value=(
            "Pon el rol del bot por encima de los roles que va a dar.\n"
            "Dale permisos de enviar mensajes, insertar enlaces, gestionar roles y gestionar canales segun el modulo que uses."
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"Servidor: {guild.name} | Si no ves / al instante, espera unos segundos y vuelve a probar."
    )
    return embed


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(*TEXT_PREFIXES),
            intents=intents,
            owner_id=OWNER_ID,
        )
        self._app_commands_synced = False

    async def setup_hook(self):
        try:
            db.setup_database()
            log.info("Base de datos conectada y lista.")
        except Exception as exc:
            log.error("ERROR CRITICO: no se pudo inicializar la base de datos.")
            log.error(exc)
            raise

        @self.check
        async def _admin_only_gate(ctx: commands.Context) -> bool:
            cmd = ctx.command
            if cmd is None:
                return True

            module_name = ""
            if cmd.cog is not None and hasattr(cmd.cog, "__module__"):
                module_name = cmd.cog.__module__ or ""
            elif hasattr(cmd, "__module__"):
                module_name = getattr(cmd, "__module__", "") or ""

            if module_name.startswith("admin_modules"):
                return ctx.author.id == ctx.bot.owner_id
            return True

        async def load_cogs_from(folder: Path, package: str) -> int:
            if not folder.is_dir():
                log.warning(f"Carpeta no encontrada: {folder}")
                return 0

            loaded = 0
            for file_path in sorted(folder.glob("*.py")):
                if file_path.name.startswith("__"):
                    continue

                extension = f"{package}.{file_path.stem}"
                try:
                    await self.load_extension(extension)
                    loaded += 1
                    log.info(f"Modulo cargado: {extension}")
                except Exception as exc:
                    log.error(f"Fallo al cargar {extension}: {exc}")
            return loaded

        log.info("---------- MODULOS DE USUARIO ----------")
        user_loaded = await load_cogs_from(USER_MODULES_DIR, "modules")

        log.info("---------- MODULOS DE ADMIN ----------")
        admin_loaded = await load_cogs_from(ADMIN_MODULES_DIR, "admin_modules")

        if user_loaded == 0:
            log.warning("No se cargo ningun modulo de usuario. Revisa la carpeta modules o el directorio de trabajo.")

        log.info(f"Modulos listos | usuario={user_loaded} admin={admin_loaded}")
        log.info("Todos los modulos han sido procesados.")

    async def sync_application_commands_once(self):
        if self._app_commands_synced:
            return

        try:
            global_synced = await self.tree.sync()
            log.info(f"Slash commands globales sincronizados: {len(global_synced)}")
        except discord.HTTPException as exc:
            log.error(f"No se pudieron sincronizar los slash commands globales: {exc}")
            return

        guild_sync_count = 0
        for guild in self.guilds:
            try:
                await self.sync_guild_application_commands(guild, log_result=False)
                guild_sync_count += 1
            except discord.HTTPException as exc:
                log.warning(f"No se pudieron sincronizar slash commands en {guild.name} ({guild.id}): {exc}")

        self._app_commands_synced = True
        log.info(f"Slash commands sincronizados para {guild_sync_count} servidores actuales.")

    async def sync_guild_application_commands(
        self,
        guild: discord.Guild,
        *,
        log_result: bool = True,
    ) -> list[app_commands.AppCommand]:
        try:
            # Refleja los slash globales en scope de guild para que aparezcan al instante
            # en servidores nuevos, sin esperar a la propagacion global.
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            if log_result:
                log.info(f"Slash commands sincronizados en {guild.name} ({guild.id}): {len(synced)}")
            return synced
        except discord.HTTPException as exc:
            log.warning(f"No se pudieron sincronizar slash commands en {guild.name} ({guild.id}): {exc}")
            raise

    async def send_guild_welcome(self, guild: discord.Guild):
        if self.user is None:
            return

        embed = build_welcome_embed(
            self.user,
            guild,
            lang=resolve_help_language(getattr(guild, "preferred_locale", None)),
        )
        me = guild.me or guild.get_member(self.user.id)

        candidate_channels: list[discord.TextChannel] = []
        for channel in (guild.system_channel, guild.public_updates_channel):
            if isinstance(channel, discord.TextChannel) and channel not in candidate_channels:
                candidate_channels.append(channel)

        for channel in sorted(guild.text_channels, key=lambda item: item.position):
            if channel not in candidate_channels:
                candidate_channels.append(channel)

        if me is not None:
            for channel in candidate_channels:
                perms = channel.permissions_for(me)
                if perms.view_channel and perms.send_messages and perms.embed_links:
                    try:
                        await channel.send(embed=embed)
                        return
                    except discord.HTTPException:
                        continue

        owner = guild.owner
        if owner is None:
            try:
                owner = await self.fetch_user(guild.owner_id)
            except discord.HTTPException:
                owner = None

        if owner is not None:
            try:
                await owner.send(embed=embed)
            except discord.HTTPException:
                pass

    async def apply_configured_presence(self):
        preset = db.get_active_bot_presence_preset()
        if preset:
            await self.change_presence(
                status=resolve_presence_status(preset["status"]),
                activity=build_presence_activity(
                    preset["activity_type"],
                    preset["activity_text"],
                    preset["activity_emoji"],
                ),
            )
            return

        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="c!help | !help | /help")
        )


bot = MyBot()


@bot.event
async def on_ready():
    db.sync_guilds(bot.guilds)
    await bot.sync_application_commands_once()
    log.info(f"Bot listo | Conectado como {bot.user}")
    log.info(f"Presente en {len(bot.guilds)} servidores.")
    log.info(f"Usuarios totales (suma de servidores): {total_users_all_guilds(bot)}")
    await bot.apply_configured_presence()


@bot.event
async def on_guild_join(guild: discord.Guild):
    db.add_guild(guild)
    await bot.sync_guild_application_commands(guild)
    await bot.send_guild_welcome(guild)
    total = total_users_all_guilds(bot)
    log.info(f"Se unio a {guild.name} ({guild.id}) | Total: {len(bot.guilds)} servidores, {total} usuarios")


@bot.event
async def on_guild_remove(guild: discord.Guild):
    if not guild.name:
        return
    db.remove_guild(guild)
    total = total_users_all_guilds(bot)
    log.info(f"Salio de {guild.name} ({guild.id}) | Total: {len(bot.guilds)} servidores, {total} usuarios")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        module_name = ""
        if ctx.command and ctx.command.cog and hasattr(ctx.command.cog, "__module__"):
            module_name = ctx.command.cog.__module__ or ""
        elif ctx.command:
            module_name = getattr(ctx.command, "__module__", "") or ""
        if module_name.startswith("admin_modules"):
            return

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await send_response(
            ctx,
            f"Ups, te falto un argumento: `{error.param.name}`. Usa `c!help`, `!help` o `/help` si necesitas un ejemplo.",
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.ChannelNotFound):
        await send_response(
            ctx,
            "No encontre ese canal. Menciona un canal real como `#general` o usa su ID. No escribas el placeholder literal `#canal`.",
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.RoleNotFound):
        await send_response(
            ctx,
            "No encontre ese rol. Menciona el rol real con `@rol` o usa su ID.",
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.MemberNotFound):
        await send_response(
            ctx,
            "No encontre a ese usuario en este servidor. Usa una mencion, su nombre exacto o el ID.",
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.BadArgument):
        await send_response(
            ctx,
            "Uno de los argumentos no es valido para este comando. Si era un canal o rol, usa la mencion real del selector de Discord.",
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.MissingPermissions):
        await send_response(
            ctx,
            f"No tienes los permisos necesarios para usar este comando. Te faltan: {format_permissions(error.missing_permissions)}.",
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.NoPrivateMessage):
        return

    print(
        f"Ignorando excepcion en comando {getattr(ctx.command, 'qualified_name', 'desconocido')}:",
        file=sys.stderr,
    )
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)

    async def respond(message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    if isinstance(original, commands.MissingPermissions):
        await respond(
            f"No tienes los permisos necesarios para usar este comando. Te faltan: {format_permissions(original.missing_permissions)}."
        )
        return

    if isinstance(error, app_commands.CheckFailure):
        await respond("No tienes permisos suficientes para usar este slash command.")
        return

    if isinstance(error, app_commands.TransformerError):
        await respond("No pude interpretar uno de los argumentos. Si era un canal o rol, usa la opcion real del selector de Discord.")
        return

    log.error(
        f"Error en slash command '{getattr(interaction.command, 'qualified_name', 'desconocido')}': {original}"
    )
    await respond("Ocurrio un error inesperado al ejecutar este comando.")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN no encontrado en el archivo .env")

    async with bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
