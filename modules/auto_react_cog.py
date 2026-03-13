import asyncio
import json
import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from command_utils import parse_emoji_tokens, send_response

log = logging.getLogger("bot")
CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):(\d+)>")


class ConfirmClearView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        for child in self.children:
            child.disabled = True
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

    async def _validate_emojis(self, ctx: commands.Context, emoji_tokens: list[str]) -> tuple[list[str], list[str]]:
        validated = []
        rejected = []
        message = getattr(ctx, "message", None)
        probe_message = None

        if message is None:
            try:
                probe_message = await ctx.channel.send("Validando emojis...")
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
            try:
                await probe_message.delete()
            except discord.HTTPException:
                pass

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
            "Usa `c!react add`, `!react add` o `/react add`. Tambien tienes `remove`, `list`, `clear` y `panel`.",
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
        emoji_tokens = parse_emoji_tokens(emojis)
        if not emoji_tokens:
            await send_response(
                ctx,
                "Debes proporcionar al menos un emoji.",
                mention_author=False,
                ephemeral=True,
            )
            return

        if len(emoji_tokens) > 20:
            await send_response(
                ctx,
                "Puedes agregar maximo 20 reacciones por palabra.",
                mention_author=False,
                ephemeral=True,
            )
            return

        validated_emojis, rejected_emojis = await self._validate_emojis(ctx, emoji_tokens)
        if not validated_emojis:
            await send_response(
                ctx,
                "Ninguno de los emojis proporcionados es valido.",
                mention_author=False,
                ephemeral=True,
            )
            return

        db.add_auto_reaction(ctx.guild.id, trigger_phrase.lower(), validated_emojis)
        self._invalidate_guild_cache(ctx.guild.id)

        message = (
            f'Reacciones automaticas configuradas para **"{trigger_phrase.lower()}"**\n'
            f'Reacciones: {" ".join(validated_emojis)}'
        )
        if rejected_emojis:
            message += f"\nOmitidos: {' '.join(rejected_emojis)}"

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
                f'No hay reacciones configuradas para **"{trigger_phrase}"**.',
                mention_author=False,
                ephemeral=True,
            )
            return

        db.remove_auto_reaction(ctx.guild.id, trigger_phrase)
        self._invalidate_guild_cache(ctx.guild.id)
        await send_response(
            ctx,
            f'Reacciones automaticas eliminadas para **"{trigger_phrase}"**.',
            mention_author=False,
        )

    @react.command(name="list", description="Muestra las reacciones automaticas configuradas")
    @commands.guild_only()
    async def react_list(self, ctx: commands.Context):
        configs = self._get_guild_configs_cached(ctx.guild.id)
        if not configs:
            await send_response(
                ctx,
                "No hay reacciones automaticas configuradas en este servidor.",
                mention_author=False,
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Reacciones automaticas configuradas",
            description=f'Total: **{len(configs)}** palabra(s) configurada(s)',
            color=0xE74C3C,
        )

        for index, config in enumerate(configs[:25], start=1):
            try:
                emojis_list = json.loads(config["emojis"])
                emoji_preview = " ".join(emojis_list)
            except json.JSONDecodeError:
                emoji_preview = "Error al cargar emojis"

            embed.add_field(
                name=f'{index}. "{config["trigger_word"]}"',
                value=emoji_preview,
                inline=False,
            )

        footer = f"Mostrando primeras 25 de {len(configs)} configuraciones" if len(configs) > 25 else f"{len(configs)} configuracion(es) en total"
        embed.set_footer(text=footer)
        await send_response(ctx, embed=embed, mention_author=False, ephemeral=True)

    @react.command(name="clear", description="Elimina todas las reacciones automaticas del servidor")
    @commands.has_permissions(manage_guild=True)
    async def react_clear(self, ctx: commands.Context):
        configs = self._get_guild_configs_cached(ctx.guild.id)
        if not configs:
            await send_response(
                ctx,
                "No hay reacciones automaticas configuradas en este servidor.",
                mention_author=False,
                ephemeral=True,
            )
            return

        view = ConfirmClearView()
        await send_response(
            ctx,
            f"Vas a eliminar **{len(configs)}** configuracion(es) de reacciones automaticas. Confirma con el boton.",
            mention_author=False,
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            await send_response(ctx, "Operacion cancelada.", mention_author=False, ephemeral=True)
            return

        db.clear_auto_reactions(ctx.guild.id)
        self._invalidate_guild_cache(ctx.guild.id)
        await send_response(
            ctx,
            f"Se eliminaron **{len(configs)}** configuracion(es) de reacciones automaticas.",
            mention_author=False,
            ephemeral=True,
        )

    @commands.Cog.listener("on_message")
    async def auto_react_listener(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.content:
            return

        configs = self._get_guild_configs_cached(message.guild.id)
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
