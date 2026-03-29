import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from command_utils import is_interaction_context, looks_like_command, send_response


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

    @commands.hybrid_group(
        name="counting",
        invoke_without_command=True,
        fallback="panel",
        description="Gestiona el sistema de conteo",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def counting(self, ctx: commands.Context):
        await send_response(
            ctx,
            "Usa `c!counting set`, `!counting set` o `/counting set`. Tambien tienes `reset`, `status` y `panel`.",
            mention_author=False,
            ephemeral=True,
        )

    @counting.command(name="set", description="Establece el canal de conteo")
    @app_commands.describe(channel="Canal donde se va a contar")
    @commands.has_permissions(manage_channels=True)
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        db.set_counting_channel(channel.id, ctx.guild.id)
        self._set_channel_cache(
            channel.id,
            {
                "channel_id": channel.id,
                "guild_id": ctx.guild.id,
                "current_number": 0,
                "last_user_id": 0,
                "high_score": 0,
            },
        )

        await channel.send(
            "Este canal ha sido configurado para contar. Si alguien se equivoca, volvemos a empezar. El primer numero es el **1**."
        )
        await send_response(
            ctx,
            f"Canal de conteo configurado en {channel.mention}.",
            mention_author=False,
            ephemeral=True,
        )

        if not is_interaction_context(ctx) and getattr(ctx, "message", None) is not None:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    @counting.command(name="reset", description="Reinicia el conteo del canal actual")
    @commands.has_permissions(manage_channels=True)
    async def reset_channel(self, ctx: commands.Context):
        channel_data = self._get_channel_data_cached(ctx.channel.id)
        if not channel_data:
            await send_response(
                ctx,
                "Este canal no esta configurado para contar.",
                mention_author=False,
                ephemeral=True,
            )
            return

        db.reset_count(ctx.channel.id)
        channel_data["current_number"] = 0
        channel_data["last_user_id"] = 0
        self._set_channel_cache(ctx.channel.id, channel_data)
        await send_response(
            ctx,
            "El conteo ha sido reseteado. El siguiente numero es el **1**.",
            mention_author=False,
        )

    @counting.command(name="status", description="Muestra el estado del conteo en este canal")
    @commands.guild_only()
    async def counting_status(self, ctx: commands.Context):
        channel_data = self._get_channel_data_cached(ctx.channel.id)
        if not channel_data:
            await send_response(
                ctx,
                "Este canal no esta configurado para contar.",
                mention_author=False,
                ephemeral=True,
            )
            return

        next_number = channel_data["current_number"] + 1
        last_user = ctx.guild.get_member(channel_data["last_user_id"]) if channel_data["last_user_id"] else None

        embed = discord.Embed(title="Estado del conteo", color=0xF1C40F)
        embed.add_field(name="Canal", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Siguiente numero", value=str(next_number), inline=True)
        embed.add_field(name="Ultimo usuario", value=last_user.mention if last_user else "Nadie", inline=True)
        await send_response(ctx, embed=embed, mention_author=False, ephemeral=True)

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
            if not await looks_like_command(self.bot, message):
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass
            return

        current_number = channel_data["current_number"]
        last_user_id = channel_data["last_user_id"]

        if message.author.id == last_user_id:
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            await message.channel.send(
                f"{message.author.mention}, no puedes contar dos veces seguidas. El siguiente numero es **{current_number + 1}**."
            )
            return

        if sent_number != current_number + 1:
            await message.add_reaction("❌")
            db.reset_count(message.channel.id)
            channel_data["current_number"] = 0
            channel_data["last_user_id"] = 0
            self._set_channel_cache(message.channel.id, channel_data)
            await message.reply(
                "Numero incorrecto. El conteo se ha reiniciado. El siguiente numero es el **1**.",
                mention_author=False,
            )
            return

        await message.add_reaction("✅")
        db.update_count(message.channel.id, sent_number, message.author.id)
        channel_data["current_number"] = sent_number
        channel_data["last_user_id"] = message.author.id
        self._set_channel_cache(message.channel.id, channel_data)


async def setup(bot: commands.Bot):
    await bot.add_cog(CountingCog(bot))
