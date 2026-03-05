# modules/counting_cog.py
import discord
from discord.ext import commands
import time
import database as db

class CountingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._channel_cache = {}
        self._cache_ttl_sec = 60.0

    def _set_channel_cache(self, channel_id: int, channel_data):
        self._channel_cache[channel_id] = {
            "expires_at": time.monotonic() + self._cache_ttl_sec,
            "data": channel_data,
        }

    def _get_channel_data_cached(self, channel_id: int):
        now = time.monotonic()
        cached = self._channel_cache.get(channel_id)
        if cached and now < cached["expires_at"]:
            return cached["data"]

        row = db.get_counting_channel(channel_id)
        data = dict(row) if row else None
        self._set_channel_cache(channel_id, data)
        return data

    @commands.group(name="counting", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def counting(self, ctx: commands.Context):
        """Muestra los subcomandos para el sistema de conteo."""
        await ctx.reply("Comando inválido. Usa `c!counting set` o `c!counting reset`.", mention_author=False)

    @counting.command(name="set")
    @commands.has_permissions(manage_channels=True)
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Establece un canal para empezar a contar."""
        db.set_counting_channel(channel.id, ctx.guild.id)
        self._set_channel_cache(
            channel.id,
            {
                "channel_id": channel.id,
                "guild_id": ctx.guild.id,
                "current_number": 0,
                "last_user_id": 0,
            },
        )
        await channel.send(f"✅ ¡Este canal ha sido configurado para contar! Si alguien se equivoca, volvemos a empezar. El primer número es el **1**.")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @counting.command(name="reset")
    @commands.has_permissions(manage_channels=True)
    async def reset_channel(self, ctx: commands.Context):
        """Resetea el conteo en este canal a 0."""
        channel_data = self._get_channel_data_cached(ctx.channel.id)
        if not channel_data:
            await ctx.reply("Este canal no está configurado para contar.", mention_author=False)
            return
        
        db.reset_count(ctx.channel.id)
        channel_data["current_number"] = 0
        channel_data["last_user_id"] = 0
        self._set_channel_cache(ctx.channel.id, channel_data)
        await ctx.reply("🔄 ¡El conteo ha sido reseteado! El siguiente número es el **1**.", mention_author=False)

    @commands.Cog.listener("on_message")
    async def on_counting_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        channel_data = self._get_channel_data_cached(message.channel.id)
        if not channel_data:
            return

        try:
            sent_number = int(message.content)
        except ValueError:
            if not message.content.startswith(self.bot.command_prefix):
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
            return

        current_number = channel_data['current_number']
        last_user_id = channel_data['last_user_id']
        
        # --- LÓGICA DE ERRORES CORREGIDA ---

        # Caso 1: Usuario repetido (Advertencia, sin reinicio, borra mensaje del user)
        if message.author.id == last_user_id:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            
            await message.channel.send(f"⚠️ {message.author.mention}, ¡no puedes contar dos veces seguidas! El siguiente número es **{current_number + 1}**.")
            return

        # Caso 2: Número incorrecto (Reinicio)
        if sent_number != current_number + 1:
            await message.add_reaction("❌")
            db.reset_count(message.channel.id)
            channel_data["current_number"] = 0
            channel_data["last_user_id"] = 0
            self._set_channel_cache(message.channel.id, channel_data)
            await message.reply(f"❌ ¡Número incorrecto! **El conteo se ha reiniciado**. El siguiente número es el **1**.", mention_author=False)
            return
            
        # Si todo es correcto
        await message.add_reaction("✅")
        db.update_count(message.channel.id, sent_number, message.author.id)
        channel_data["current_number"] = sent_number
        channel_data["last_user_id"] = message.author.id
        self._set_channel_cache(message.channel.id, channel_data)

async def setup(bot: commands.Bot):
    await bot.add_cog(CountingCog(bot))
