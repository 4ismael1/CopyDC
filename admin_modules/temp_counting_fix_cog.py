from __future__ import annotations

import asyncio

from discord.ext import commands

import database as db


class TemporaryCountingFix(commands.Cog):
    """Herramienta temporal del owner para corregir un canal de conteo."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="fixcount", hidden=True)
    @commands.guild_only()
    @commands.is_owner()
    async def fix_count(self, ctx: commands.Context, number: int):
        """Establece el número actual del canal: !fixcount <número>."""
        if number < 0:
            await ctx.reply("El número no puede ser negativo.", mention_author=False)
            return

        channel_id = ctx.channel.id
        current = await asyncio.to_thread(db.get_counting_channel, channel_id)
        if current is None:
            await ctx.reply(
                "Este canal no está configurado como canal de conteo.",
                mention_author=False,
            )
            return

        await asyncio.to_thread(db.update_count, channel_id, number, 0)
        updated_row = await asyncio.to_thread(db.get_counting_channel, channel_id)
        updated = dict(updated_row)

        counting_cog = self.bot.get_cog("CountingCog")
        if counting_cog is not None:
            counting_cog._set_channel_cache(channel_id, updated)

        await ctx.reply(
            f"Conteo corregido: número actual **{number}**; el siguiente número es **{number + 1}**.",
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TemporaryCountingFix(bot))
