# modules/logging_cog.py
import os
import logging
from discord.ext import commands

class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Asegurar carpeta logs
        os.makedirs("logs", exist_ok=True)

        # Configuración del logger con archivo
        log_file = os.path.join("logs", "bot.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)

        # Añadir handler al logger principal del bot (solo una vez)
        self.logger = logging.getLogger("bot")
        if not any(isinstance(h, logging.FileHandler) for h in self.logger.handlers):
            self.logger.addHandler(file_handler)

    # Opcional: solo errores globales
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        self.logger.error(f"Error en comando '{ctx.command}': {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
