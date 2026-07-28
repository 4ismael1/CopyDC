from __future__ import annotations

import discord
from discord.ext import commands

from command_utils import RestrictedView, send_response
from localization import (
    get_guild_mode,
    get_language,
    resolve_discord_locale,
    set_guild_mode,
    translate_language,
)


def _mode_label(language: str, mode: str) -> str:
    return translate_language(language, f"language.mode.{mode}")


def _language_label(language: str, effective_language: str) -> str:
    key = "common.spanish" if effective_language == "es" else "common.english"
    return translate_language(language, key)


def build_language_embed(guild: discord.Guild, language: str) -> discord.Embed:
    mode = get_guild_mode(guild.id)
    detected = resolve_discord_locale(guild.preferred_locale)
    return discord.Embed(
        title=translate_language(language, "language.title"),
        description=(
            translate_language(language, "language.command_help")
            + "\n\n"
            + translate_language(
                language,
                "language.current",
                mode=_mode_label(language, mode),
                detected=_language_label(language, detected),
            )
        ),
        color=discord.Color.blurple(),
    )


class LanguageSelect(discord.ui.Select):
    def __init__(self, *, language: str, current_mode: str):
        options = [
            discord.SelectOption(
                label=_mode_label(language, mode),
                description=translate_language(language, f"language.option.{mode}"),
                value=mode,
                default=mode == current_mode,
            )
            for mode in ("auto", "es", "en")
        ]
        super().__init__(
            placeholder=translate_language(language, "language.placeholder"),
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        assert isinstance(self.view, LanguageView)
        assert interaction.guild is not None

        mode = set_guild_mode(interaction.guild.id, self.values[0])
        language = get_language(interaction)
        effective_label = _language_label(language, language)
        saved = translate_language(
            language,
            "language.saved",
            mode=_mode_label(language, mode),
            language=effective_label,
        )
        embed = build_language_embed(interaction.guild, language)
        embed.add_field(name="\u200b", value=saved, inline=False)
        new_view = LanguageView(
            author_id=self.view.author_id,
            guild=interaction.guild,
            language=language,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)
        interaction.client.dispatch("copy_language_change", interaction.guild, language)


class LanguageView(RestrictedView):
    def __init__(
        self,
        *,
        author_id: int,
        guild: discord.Guild,
        language: str,
    ):
        super().__init__(
            author_id=author_id,
            timeout=180,
            required_permissions=("manage_guild",),
        )
        self.add_item(
            LanguageSelect(
                language=language,
                current_mode=get_guild_mode(guild.id),
            )
        )


class LanguageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="language",
        description="Configure Copy's language for this server",
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def language(self, ctx: commands.Context):
        assert ctx.guild is not None
        language = get_language(ctx)
        embed = build_language_embed(ctx.guild, language)
        view = LanguageView(
            author_id=ctx.author.id,
            guild=ctx.guild,
            language=language,
        )
        await send_response(
            ctx,
            embed=embed,
            view=view,
            mention_author=False,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageCog(bot))
