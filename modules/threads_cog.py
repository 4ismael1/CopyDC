import logging
import time
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from command_utils import send_response

log = logging.getLogger("bot")
ThreadMode = Literal["all", "media", "text"]


class ThreadsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._channel_cache = {}
        self._cache_ttl_sec = 60.0

    def _set_channel_cache(self, channel_id: int, config):
        self._channel_cache[channel_id] = {
            "expires_at": time.monotonic() + self._cache_ttl_sec,
            "config": config,
        }

    def _get_channel_config_cached(self, channel_id: int):
        now = time.monotonic()
        cached = self._channel_cache.get(channel_id)
        if cached and now < cached["expires_at"]:
            return cached["config"]

        row = db.get_thread_config_for_channel(channel_id)
        config = dict(row) if row else None
        self._set_channel_cache(channel_id, config)
        return config

    @commands.hybrid_group(
        name="thread",
        invoke_without_command=True,
        fallback="panel",
        description="Gestiona hilos automaticos",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def thread(self, ctx: commands.Context):
        await send_response(
            ctx,
            "Usa `c!thread add`, `!thread add` o `/thread add`. Tambien tienes `remove`, `list` y `panel`.",
            mention_author=False,
            ephemeral=True,
        )

    @thread.command(name="add", description="Activa hilos automaticos en un canal")
    @app_commands.describe(channel="Canal que tendra hilos automaticos", mode="Modo de activacion del hilo")
    @commands.has_permissions(manage_channels=True)
    async def thread_add(self, ctx: commands.Context, channel: discord.TextChannel, mode: ThreadMode):
        db.add_thread_config(ctx.guild.id, channel.id, mode)
        self._set_channel_cache(
            channel.id,
            {"guild_id": ctx.guild.id, "channel_id": channel.id, "mode": mode},
        )
        await send_response(
            ctx,
            f"Hilos automaticos activados en {channel.mention} con modo **{mode}**.",
            mention_author=False,
        )

    @thread.command(name="remove", description="Desactiva hilos automaticos en un canal")
    @app_commands.describe(channel="Canal que dejara de crear hilos automaticamente")
    @commands.has_permissions(manage_channels=True)
    async def thread_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        db.remove_thread_config(channel.id)
        self._set_channel_cache(channel.id, None)
        await send_response(
            ctx,
            f"Hilos automaticos desactivados en {channel.mention}.",
            mention_author=False,
        )

    @thread.command(name="list", description="Muestra la configuracion actual de hilos")
    @commands.guild_only()
    async def thread_list(self, ctx: commands.Context):
        configs = db.get_all_thread_configs_for_guild(ctx.guild.id)
        if not configs:
            await send_response(
                ctx,
                "No hay canales configurados para hilos automaticos en este servidor.",
                mention_author=False,
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="Configuracion de hilos automaticos", color=0x3498DB)
        lines = []
        for config in configs:
            channel = self.bot.get_channel(config["channel_id"])
            channel_text = channel.mention if channel else f"`{config['channel_id']}`"
            lines.append(f"{channel_text} -> modo **{config['mode']}**")

        embed.description = "\n".join(lines)
        await send_response(ctx, embed=embed, mention_author=False, ephemeral=True)

    @commands.Cog.listener("on_message")
    async def auto_threads_listener(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        config = self._get_channel_config_cached(msg.channel.id)
        if not config:
            return

        config_mode = config["mode"]
        has_media = any(
            attachment.content_type
            and (
                attachment.content_type.startswith("image/")
                or attachment.content_type.startswith("video/")
            )
            for attachment in msg.attachments
        )
        has_text = bool(msg.content.strip())

        should_create_thread = False
        if config_mode == "all" and (has_text or has_media):
            should_create_thread = True
        elif config_mode == "media" and has_media:
            should_create_thread = True
        elif config_mode == "text" and has_text and not has_media:
            should_create_thread = True

        if should_create_thread:
            try:
                await msg.add_reaction("💗")
            except discord.NotFound:
                # El mensaje fue eliminado antes de poder reaccionar.
                return
            except discord.HTTPException:
                pass

            try:
                await msg.create_thread(name="comentarios (auto)", auto_archive_duration=1440)
            except discord.NotFound:
                # Carrera normal: alguien borro el mensaje antes del thread.
                return
            except discord.Forbidden as exc:
                log.warning(
                    f"Sin permisos para crear hilo automatico en {msg.guild.name} ({msg.channel.name}): {exc}"
                )
            except discord.HTTPException as exc:
                log.error(f"Error al crear hilo automatico en {msg.guild.name} ({msg.channel.name}): {exc}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ThreadsCog(bot))

