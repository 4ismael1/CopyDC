# modules/threads_cog.py
import logging
import discord
from discord.ext import commands
import database as db # <--- Importamos nuestro gestor de DB

log = logging.getLogger("bot")

class ThreadsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="thread", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def thread(self, ctx: commands.Context):
        await ctx.reply("Comando inválido. Usa `c!thread add`, `c!thread remove` o `c!thread list`.", mention_author=False)

    @thread.command(name="add")
    @commands.has_permissions(manage_channels=True)
    async def thread_add(self, ctx: commands.Context, channel: discord.TextChannel, mode: str):
        """Activa hilos automáticos. Modos: 'all', 'media', 'text'."""
        mode = mode.lower()
        if mode not in ["media", "all", "text"]:
            await ctx.reply("❌ Modo inválido. Usa 'all', 'media' o 'text'.", mention_author=False)
            return

        # Guardamos la configuración en la base de datos
        db.add_thread_config(ctx.guild.id, channel.id, mode)
        await ctx.reply(f"✅ Hilos automáticos activados en {channel.mention} con modo **{mode}**.", mention_author=False)

    @thread.command(name="remove")
    @commands.has_permissions(manage_channels=True)
    async def thread_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        """Desactiva los hilos automáticos para un canal."""
        # Eliminamos la configuración de la base de datos
        db.remove_thread_config(channel.id)
        await ctx.reply(f"✅ Hilos automáticos desactivados en {channel.mention}.", mention_author=False)

    @thread.command(name="list")
    async def thread_list(self, ctx: commands.Context):
        """Muestra la configuración de hilos automáticos para este servidor."""
        # Obtenemos las configuraciones desde la base de datos
        configs = db.get_all_thread_configs_for_guild(ctx.guild.id)
        if not configs:
            await ctx.reply("ℹ️ No hay canales configurados para hilos automáticos en este servidor.", mention_author=False)
            return

        embed = discord.Embed(title="⚙️ Configuración de Hilos Automáticos", color=0x3498db)
        description = ""
        for config in configs:
            ch = self.bot.get_channel(config['channel_id'])
            description += f"{ch.mention if ch else f'`{config['channel_id']}`'} → Modo: **{config['mode']}**\n"
        
        embed.description = description
        await ctx.reply(embed=embed, mention_author=False)

    @commands.Cog.listener("on_message")
    async def auto_threads_listener(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        # Consultamos la configuración en vivo desde la base de datos
        config = db.get_thread_config_for_channel(msg.channel.id)
        if not config:
            return

        config_mode = config['mode']
        
        has_media = any(a.content_type and (a.content_type.startswith("image/") or a.content_type.startswith("video/")) for a in msg.attachments)
        has_text = bool(msg.content.strip())
        
        should_create_thread = False
        if config_mode == 'all' and (has_text or has_media): should_create_thread = True
        elif config_mode == 'media' and has_media: should_create_thread = True
        elif config_mode == 'text' and has_text and not has_media: should_create_thread = True

        if should_create_thread:
            try:
                # El emoji fue cambiado en el código que me pasaste, lo mantengo.
                await msg.add_reaction("💗") 
                await msg.create_thread(name="comentarios ₍^. .^₎⟆", auto_archive_duration=1440)
            except Exception as e:
                log.error(f"Error al crear hilo automático en {msg.guild.name} ({msg.channel.name}): {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ThreadsCog(bot))