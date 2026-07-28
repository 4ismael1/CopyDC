import asyncio
import logging
import os
import sys
from contextlib import suppress
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import database as db
import localization
from command_utils import build_presence_activity, resolve_presence_status, send_response
from localization import get_language, translate, translate_language

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


def format_permissions(perms: list[str], language: str) -> str:
    keys = localization.catalog_keys(language)
    return ", ".join(
        translate_language(language, f"permissions.{permission}")
        if f"permissions.{permission}" in keys
        else permission.replace("_", " ")
        for permission in perms
    )


def build_welcome_embed(bot_user: discord.ClientUser, guild: discord.Guild, *, lang: str) -> discord.Embed:
    embed = discord.Embed(
        title=translate_language(lang, "welcome.title", bot=bot_user.display_name),
        description=translate_language(lang, "welcome.description"),
        color=0x5865F2,
    )
    embed.add_field(
        name=translate_language(lang, "welcome.quick.name"),
        value=translate_language(lang, "welcome.quick.value"),
        inline=False,
    )
    embed.add_field(
        name=translate_language(lang, "welcome.modules.name"),
        value=translate_language(lang, "welcome.modules.value"),
        inline=False,
    )
    embed.add_field(
        name=translate_language(lang, "welcome.before.name"),
        value=translate_language(lang, "welcome.before.value"),
        inline=False,
    )
    embed.set_footer(text=translate_language(lang, "welcome.footer", guild=guild.name))
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
            localization.initialize()
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

        async def load_cogs_from(folder: Path, package: str) -> tuple[int, list[str]]:
            if not folder.is_dir():
                log.warning(f"Carpeta no encontrada: {folder}")
                return 0, [str(folder)]

            loaded = 0
            failures: list[str] = []
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
                    failures.append(extension)
            return loaded, failures

        log.info("---------- MODULOS DE USUARIO ----------")
        user_loaded, user_failures = await load_cogs_from(USER_MODULES_DIR, "modules")

        log.info("---------- MODULOS DE ADMIN ----------")
        admin_loaded, admin_failures = await load_cogs_from(ADMIN_MODULES_DIR, "admin_modules")

        if user_loaded == 0:
            log.warning(
                "No se cargo ningun modulo de usuario. Revisa la carpeta modules o el directorio de trabajo."
            )
        if user_failures:
            raise RuntimeError(
                "No se inició el bot porque fallaron módulos de usuario requeridos: "
                + ", ".join(user_failures)
            )
        if admin_failures:
            log.warning("Módulos administrativos no disponibles: %s", ", ".join(admin_failures))

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

        self._app_commands_synced = True
        log.info("Los comandos globales quedan disponibles para todos los servidores.")

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
            lang=get_language(guild),
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
            with suppress(discord.HTTPException):
                await owner.send(embed=embed)

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
            activity=discord.Activity(type=discord.ActivityType.listening, name="c!help | !help | /help"),
        )


bot = MyBot()


@bot.event
async def on_ready():
    await asyncio.to_thread(db.sync_guilds, bot.guilds)
    await bot.sync_application_commands_once()
    log.info(f"Bot listo | Conectado como {bot.user}")
    log.info(f"Presente en {len(bot.guilds)} servidores.")
    log.info(f"Usuarios totales (suma de servidores): {total_users_all_guilds(bot)}")
    await bot.apply_configured_presence()


@bot.event
async def on_guild_join(guild: discord.Guild):
    await asyncio.to_thread(db.add_guild, guild)
    await bot.send_guild_welcome(guild)
    total = total_users_all_guilds(bot)
    log.info(f"Se unio a {guild.name} ({guild.id}) | Total: {len(bot.guilds)} servidores, {total} usuarios")


@bot.event
async def on_guild_remove(guild: discord.Guild):
    await asyncio.to_thread(db.remove_guild, guild)
    localization.remove_guild_mode(guild.id)
    total = total_users_all_guilds(bot)
    log.info(
        f"Salio de {guild.name or 'servidor desconocido'} ({guild.id}) | "
        f"Total: {len(bot.guilds)} servidores, {total} usuarios"
    )


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
            translate(ctx, "error.missing_argument", argument=error.param.name),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.ChannelNotFound):
        await send_response(
            ctx,
            translate(ctx, "error.channel_not_found"),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.RoleNotFound):
        await send_response(
            ctx,
            translate(ctx, "error.role_not_found"),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.MemberNotFound):
        await send_response(
            ctx,
            translate(ctx, "error.member_not_found"),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.BadArgument):
        await send_response(
            ctx,
            translate(ctx, "error.bad_argument"),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.MissingPermissions):
        language = get_language(ctx)
        await send_response(
            ctx,
            translate(
                ctx,
                "error.missing_permissions",
                permissions=format_permissions(error.missing_permissions, language),
            ),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.BotMissingPermissions):
        language = get_language(ctx)
        await send_response(
            ctx,
            translate(
                ctx,
                "error.bot_missing_permissions",
                permissions=format_permissions(error.missing_permissions, language),
            ),
            mention_author=False,
            ephemeral=True,
        )
        return

    if isinstance(error, commands.NoPrivateMessage):
        return

    original = getattr(error, "original", error)
    if isinstance(original, discord.Forbidden):
        await send_response(
            ctx,
            translate(ctx, "error.discord_forbidden"),
            mention_author=False,
            ephemeral=True,
        )
        return

    log.exception(
        "Error en comando '%s'",
        getattr(ctx.command, "qualified_name", "desconocido"),
        exc_info=(type(original), original, original.__traceback__),
    )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)

    async def respond(message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    if isinstance(original, commands.MissingPermissions):
        language = get_language(interaction)
        await respond(
            translate(
                interaction,
                "error.missing_permissions",
                permissions=format_permissions(original.missing_permissions, language),
            )
        )
        return

    if isinstance(original, commands.BotMissingPermissions):
        language = get_language(interaction)
        await respond(
            translate(
                interaction,
                "error.bot_missing_permissions",
                permissions=format_permissions(original.missing_permissions, language),
            )
        )
        return

    if isinstance(original, discord.Forbidden):
        await respond(translate(interaction, "error.discord_forbidden"))
        return

    if isinstance(error, app_commands.CheckFailure):
        await respond(translate(interaction, "error.slash_check_failed"))
        return

    if isinstance(error, app_commands.TransformerError):
        await respond(translate(interaction, "error.transformer"))
        return

    log.error(
        "Error en slash command '%s'",
        getattr(interaction.command, "qualified_name", "desconocido"),
        exc_info=(type(original), original, original.__traceback__),
    )
    await respond(translate(interaction, "error.unexpected"))


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN no encontrado en el archivo .env")
    if OWNER_ID <= 0:
        raise RuntimeError("OWNER_ID debe contener el ID numérico del propietario en el archivo .env")

    async with bot:
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
