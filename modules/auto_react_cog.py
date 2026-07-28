import asyncio
import json
import logging
import re
import time
from contextlib import suppress

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from command_utils import RestrictedView, parse_emoji_tokens, send_response
from localization import get_language, translate, translate_language

log = logging.getLogger("bot")
CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):(\d+)>")


class ConfirmClearView(RestrictedView):
    def __init__(self, author_id: int, language: str):
        super().__init__(
            author_id=author_id,
            timeout=30,
            required_permissions=("manage_guild",),
        )
        self.confirmed = False
        self.confirm.label = translate_language(language, "common.confirm")
        self.cancel.label = translate_language(language, "common.cancel")

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.confirmed = True
        self.disable_all_items()
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.disable_all_items()
        await interaction.response.edit_message(view=self)
        self.stop()


class AutoReactCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._config_cache = {}
        self._cache_ttl_sec = 30.0

    def _invalidate_guild_cache(self, guild_id: int):
        self._config_cache.pop(guild_id, None)

    def _get_guild_configs_cached(self, guild_id: int):
        now = time.monotonic()
        cached = self._config_cache.get(guild_id)
        if cached and now < cached["expires_at"]:
            return cached["configs"]

        rows = db.get_all_auto_reactions(guild_id)
        configs = [dict(row) for row in rows]
        self._config_cache[guild_id] = {
            "expires_at": now + self._cache_ttl_sec,
            "configs": configs,
        }
        return configs

    async def _validate_emojis(
        self, ctx: commands.Context, emoji_tokens: list[str]
    ) -> tuple[list[str], list[str]]:
        validated = []
        rejected = []
        message = getattr(ctx, "message", None)
        probe_message = None

        if message is None:
            try:
                probe_message = await ctx.channel.send(translate(ctx, "react.probe"))
                message = probe_message
            except discord.HTTPException:
                message = None

        for emoji in emoji_tokens:
            custom_match = CUSTOM_EMOJI_RE.fullmatch(emoji)
            if custom_match:
                emoji_obj = discord.utils.get(ctx.guild.emojis, id=int(custom_match.group(2)))
                if emoji_obj:
                    validated.append(emoji)
                else:
                    rejected.append(emoji)
                continue

            if message is not None:
                try:
                    await message.add_reaction(emoji)
                    await message.remove_reaction(emoji, ctx.guild.me)
                    validated.append(emoji)
                    continue
                except (discord.HTTPException, discord.NotFound):
                    pass

            rejected.append(emoji)

        if probe_message is not None:
            with suppress(discord.HTTPException):
                await probe_message.delete()

        return validated, rejected

    @commands.hybrid_group(
        name="react",
        invoke_without_command=True,
        fallback="panel",
        description="Gestiona reacciones automaticas",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def react(self, ctx: commands.Context):
        await send_response(
            ctx,
            translate(ctx, "react.help"),
            mention_author=False,
            ephemeral=True,
        )

    @react.command(name="add", description="Configura reacciones automaticas para una palabra o frase")
    @app_commands.describe(
        trigger_phrase="Palabra o frase que activara las reacciones",
        emojis="Emojis separados por espacios, por ejemplo: 👋 💖 ✨",
    )
    @commands.has_permissions(manage_guild=True)
    async def react_add(self, ctx: commands.Context, trigger_phrase: str, *, emojis: str):
        trigger_phrase = trigger_phrase.strip().lower()
        if not trigger_phrase:
            await send_response(
                ctx,
                translate(ctx, "react.empty_trigger"),
                mention_author=False,
                ephemeral=True,
            )
            return
        if len(trigger_phrase) > 100:
            await send_response(
                ctx,
                translate(ctx, "react.max_trigger"),
                mention_author=False,
                ephemeral=True,
            )
            return

        emoji_tokens = parse_emoji_tokens(emojis)
        if not emoji_tokens:
            await send_response(
                ctx,
                translate(ctx, "react.no_emojis"),
                mention_author=False,
                ephemeral=True,
            )
            return

        if len(emoji_tokens) > 20:
            await send_response(
                ctx,
                translate(ctx, "react.max_emojis"),
                mention_author=False,
                ephemeral=True,
            )
            return

        validated_emojis, rejected_emojis = await self._validate_emojis(ctx, emoji_tokens)
        if not validated_emojis:
            await send_response(
                ctx,
                translate(ctx, "react.no_valid_emojis"),
                mention_author=False,
                ephemeral=True,
            )
            return

        db.add_auto_reaction(ctx.guild.id, trigger_phrase, validated_emojis)
        self._invalidate_guild_cache(ctx.guild.id)

        message = translate(
            ctx,
            "react.added",
            trigger=trigger_phrase,
            emojis=" ".join(validated_emojis),
        )
        if rejected_emojis:
            message += "\n" + translate(ctx, "react.omitted", emojis=" ".join(rejected_emojis))

        await send_response(ctx, message, mention_author=False)

    @react.command(name="remove", description="Elimina una configuracion de reacciones")
    @app_commands.describe(trigger_phrase="Palabra o frase que quieres eliminar")
    @commands.has_permissions(manage_guild=True)
    async def react_remove(self, ctx: commands.Context, trigger_phrase: str):
        trigger_phrase = trigger_phrase.lower()
        config = db.get_auto_reaction(ctx.guild.id, trigger_phrase)
        if not config:
            await send_response(
                ctx,
                translate(ctx, "react.not_found", trigger=trigger_phrase),
                mention_author=False,
                ephemeral=True,
            )
            return

        db.remove_auto_reaction(ctx.guild.id, trigger_phrase)
        self._invalidate_guild_cache(ctx.guild.id)
        await send_response(
            ctx,
            translate(ctx, "react.removed", trigger=trigger_phrase),
            mention_author=False,
        )

    @react.command(name="list", description="Muestra las reacciones automaticas configuradas")
    @commands.guild_only()
    async def react_list(self, ctx: commands.Context):
        configs = self._get_guild_configs_cached(ctx.guild.id)
        if not configs:
            await send_response(
                ctx,
                translate(ctx, "react.none"),
                mention_author=False,
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=translate(ctx, "react.list_title"),
            description=translate(ctx, "react.list_description", count=len(configs)),
            color=0xE74C3C,
        )

        for index, config in enumerate(configs[:25], start=1):
            try:
                emojis_list = json.loads(config["emojis"])
                emoji_preview = " ".join(emojis_list)
            except json.JSONDecodeError:
                emoji_preview = translate(ctx, "react.decode_error")

            embed.add_field(
                name=f'{index}. "{config["trigger_word"]}"',
                value=emoji_preview,
                inline=False,
            )

        footer = (
            translate(ctx, "react.footer_limited", count=len(configs))
            if len(configs) > 25
            else translate(ctx, "react.footer_all", count=len(configs))
        )
        embed.set_footer(text=footer)
        await send_response(ctx, embed=embed, mention_author=False, ephemeral=True)

    @react.command(name="clear", description="Elimina todas las reacciones automaticas del servidor")
    @commands.has_permissions(manage_guild=True)
    async def react_clear(self, ctx: commands.Context):
        configs = self._get_guild_configs_cached(ctx.guild.id)
        if not configs:
            await send_response(
                ctx,
                translate(ctx, "react.none"),
                mention_author=False,
                ephemeral=True,
            )
            return

        view = ConfirmClearView(ctx.author.id, get_language(ctx))
        await send_response(
            ctx,
            translate(ctx, "react.confirm_clear", count=len(configs)),
            mention_author=False,
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            await send_response(
                ctx,
                translate(ctx, "common.cancelled"),
                mention_author=False,
                ephemeral=True,
            )
            return

        db.clear_auto_reactions(ctx.guild.id)
        self._invalidate_guild_cache(ctx.guild.id)
        await send_response(
            ctx,
            translate(ctx, "react.cleared", count=len(configs)),
            mention_author=False,
            ephemeral=True,
        )

    @commands.Cog.listener("on_message")
    async def auto_react_listener(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.content:
            return

        configs = await asyncio.to_thread(self._get_guild_configs_cached, message.guild.id)
        if not configs:
            return

        content_lower = message.content.lower()
        for config in configs:
            trigger = config["trigger_word"]
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if not re.search(pattern, content_lower):
                continue

            try:
                emojis_list = json.loads(config["emojis"])
            except json.JSONDecodeError:
                log.error(f"Error al decodificar emojis para trigger '{trigger}' en guild {message.guild.id}")
                continue

            for emoji in emojis_list:
                try:
                    await message.add_reaction(emoji)
                    if len(emojis_list) > 2:
                        await asyncio.sleep(0.3)
                except discord.HTTPException as exc:
                    log.warning(f"No se pudo agregar reaccion '{emoji}' en {message.guild.name}: {exc}")
                except Exception as exc:
                    log.error(f"Error inesperado al reaccionar en {message.guild.name}: {exc}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReactCog(bot))
