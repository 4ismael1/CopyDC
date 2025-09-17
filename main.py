# main.py
import os
import logging
import asyncio
import sys
import traceback
import discord
from discord.ext import commands
from dotenv import load_dotenv
import database as db

# ────────────── ENV & LOG ──────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("bot")

# ────────────── BOT SETUP ──────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guild_messages = True  # permite leer mensajes-sistema (boost add)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="c!", intents=intents, owner_id=OWNER_ID)

    async def setup_hook(self):
        """Prepara la DB, registra el gate admin y carga los Cogs (usuarios → admin)."""
        # 1) DB
        try:
            db.setup_database()
            log.info("✔️ Base de datos conectada y lista.")
        except Exception as e:
            log.error("❌ ERROR CRÍTICO: No se pudo inicializar la base de datos.")
            log.error(e)
            raise e

        # 2) Gate global: comandos de admin_modules.* solo para el OWNER
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

        # 3) Loader utilitario
        async def load_cogs_from(folder: str, package: str):
            """Carga todos los .py (no __init__) de una carpeta como extensiones."""
            if not os.path.isdir(folder):
                log.warning(f"⚠️ Carpeta no encontrada: {folder}")
                return

            for filename in sorted(os.listdir(folder)):
                if filename.endswith(".py") and not filename.startswith("__"):
                    ext = f"{package}.{filename[:-3]}"
                    try:
                        await self.load_extension(ext)
                        log.info(f"✅ Módulo cargado: {ext}")
                    except Exception as e:
                        log.error(f"❌ Falló al cargar {ext}: {e}")

        # 4) Carga por secciones
        log.info("────────── MÓDULOS DE USUARIO (./modules) ──────────")
        await load_cogs_from("./modules", "modules")

        log.info("────────── MÓDULOS DE ADMIN (./admin_modules) ──────────")
        await load_cogs_from("./admin_modules", "admin_modules")

        log.info("Todos los módulos han sido procesados.")


bot = MyBot()

# ────────────── EVENTOS ──────────────
@bot.event
async def on_ready():
    """Se ejecuta cuando el bot está listo y sincroniza los servidores con la DB."""
    db.sync_guilds(bot.guilds)
    log.info(f"Bot listo | Conectado como {bot.user}")
    log.info(f"Presente en {len(bot.guilds)} servidores.")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="c!help")
    )

@bot.event
async def on_guild_join(guild):
    """Añade el nuevo servidor a la base de datos."""
    db.add_guild(guild)
    log.info(f"➕ Se unió a {guild.name} ({guild.id})")

@bot.event
async def on_guild_remove(guild):
    """Elimina el servidor de la base de datos."""
    db.remove_guild(guild)
    log.info(f"➖ Salió de {guild.name} ({guild.id})")


# ────────────── MANEJADOR DE ERRORES GLOBAL ──────────────
@bot.event
async def on_command_error(ctx: commands.Context, error):
    """Manejador de errores global para todos los comandos."""
    # Silencio total: intentos de no-owner sobre admin_modules.* (sin mensaje y sin log)
    if isinstance(error, commands.CheckFailure):
        module_name = ""
        if ctx.command and ctx.command.cog and hasattr(ctx.command.cog, "__module__"):
            module_name = ctx.command.cog.__module__ or ""
        elif ctx.command:
            module_name = getattr(ctx.command, "__module__", "") or ""
        if module_name.startswith("admin_modules"):
            return  # no responder ni loguear
        # Para otros CheckFailure que no sean de admin_modules, sigue con el manejo estándar abajo

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"Ups, te faltó un argumento: `{error.param.name}`.", mention_author=False)
        return

    if isinstance(error, commands.BadArgument):
        await ctx.reply("El tipo de argumento que usaste no es válido para este comando.", mention_author=False)
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("No tienes los permisos necesarios para usar este comando.", mention_author=False)
        return

    if isinstance(error, commands.NoPrivateMessage):
        return

    # Para cualquier otro tipo de error, lo mostramos en la consola para depuración.
    print(f'Ignorando excepción en comando {getattr(ctx.command, "qualified_name", "¿desconocido?")}:', file=sys.stderr)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


# ────────────── RUN ──────────────
async def main():
    """Función principal para iniciar el bot."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN no encontrado en el archivo .env")
    async with bot:
        await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())