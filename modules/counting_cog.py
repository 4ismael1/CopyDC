import asyncio
import time
from collections import defaultdict
from contextlib import suppress

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from command_utils import is_interaction_context, looks_like_command, send_response
from localization import translate


class CountingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._channel_cache = {}
        self._cache_ttl_sec = 60.0
        self._channel_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

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
            translate(ctx, "counting.help"),
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

        await channel.send(translate(ctx, "counting.setup_message"))
        await send_response(
            ctx,
            translate(ctx, "counting.configured", channel=channel.mention),
            mention_author=False,
            ephemeral=True,
        )

        if not is_interaction_context(ctx) and getattr(ctx, "message", None) is not None:
            with suppress(discord.Forbidden, discord.NotFound, discord.HTTPException):
                await ctx.message.delete()

    @counting.command(name="remove", description="Desactiva el conteo del canal actual")
    @commands.has_permissions(manage_channels=True)
    async def remove_channel(self, ctx: commands.Context):
        channel_data = self._get_channel_data_cached(ctx.channel.id)
        if not channel_data:
            await send_response(
                ctx,
                translate(ctx, "counting.not_configured"),
                mention_author=False,
                ephemeral=True,
            )
            return

        db.remove_counting_channel(ctx.channel.id)
        self._set_channel_cache(ctx.channel.id, None)
        await send_response(
            ctx,
            translate(ctx, "counting.disabled"),
            mention_author=False,
            ephemeral=True,
        )

    @counting.command(name="reset", description="Reinicia el conteo del canal actual")
    @commands.has_permissions(manage_channels=True)
    async def reset_channel(self, ctx: commands.Context):
        channel_data = self._get_channel_data_cached(ctx.channel.id)
        if not channel_data:
            await send_response(
                ctx,
                translate(ctx, "counting.not_configured"),
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
            translate(ctx, "counting.reset"),
            mention_author=False,
        )

    @counting.command(name="status", description="Muestra el estado del conteo en este canal")
    @commands.guild_only()
    async def counting_status(self, ctx: commands.Context):
        channel_data = self._get_channel_data_cached(ctx.channel.id)
        if not channel_data:
            await send_response(
                ctx,
                translate(ctx, "counting.not_configured"),
                mention_author=False,
                ephemeral=True,
            )
            return

        next_number = channel_data["current_number"] + 1
        last_user = (
            ctx.guild.get_member(channel_data["last_user_id"]) if channel_data["last_user_id"] else None
        )

        embed = discord.Embed(title=translate(ctx, "counting.status_title"), color=0xF1C40F)
        embed.add_field(name=translate(ctx, "counting.channel_field"), value=ctx.channel.mention, inline=True)
        embed.add_field(name=translate(ctx, "counting.next_field"), value=str(next_number), inline=True)
        embed.add_field(
            name=translate(ctx, "counting.last_user_field"),
            value=last_user.mention if last_user else translate(ctx, "counting.never"),
            inline=True,
        )
        embed.add_field(
            name=translate(ctx, "counting.record_field"),
            value=str(channel_data["high_score"]),
            inline=True,
        )
        await send_response(ctx, embed=embed, mention_author=False, ephemeral=True)

    @commands.Cog.listener("on_message")
    async def on_counting_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        raw_content = message.content.strip()
        if not raw_content:
            return

        async with self._channel_locks[message.channel.id]:
            channel_data = self._get_channel_data_cached(message.channel.id)
            if not channel_data:
                return

            try:
                sent_number = int(raw_content)
            except ValueError:
                if await looks_like_command(self.bot, message):
                    return
                with suppress(discord.Forbidden, discord.NotFound, discord.HTTPException):
                    await message.delete()
                return

            current_number = channel_data["current_number"]
            last_user_id = channel_data["last_user_id"]

            if message.author.id == last_user_id:
                with suppress(discord.Forbidden, discord.NotFound, discord.HTTPException):
                    await message.delete()

                await message.channel.send(
                    translate(
                        message,
                        "counting.same_user",
                        user=message.author.mention,
                        next_number=current_number + 1,
                    )
                )
                return

            if sent_number != current_number + 1:
                with suppress(discord.HTTPException):
                    await message.add_reaction("❌")
                await asyncio.to_thread(db.reset_count, message.channel.id)
                channel_data["current_number"] = 0
                channel_data["last_user_id"] = 0
                self._set_channel_cache(message.channel.id, channel_data)
                await message.reply(
                    translate(message, "counting.wrong_number"),
                    mention_author=False,
                )
                return

            with suppress(discord.HTTPException):
                await message.add_reaction("✅")
            await asyncio.to_thread(
                db.update_count,
                message.channel.id,
                sent_number,
                message.author.id,
            )
            channel_data["current_number"] = sent_number
            channel_data["last_user_id"] = message.author.id
            channel_data["high_score"] = max(channel_data["high_score"], sent_number)
            self._set_channel_cache(message.channel.id, channel_data)


async def setup(bot: commands.Bot):
    await bot.add_cog(CountingCog(bot))
