from __future__ import annotations

import re
from typing import Any

import discord
from discord.ext import commands


def is_interaction_context(ctx: commands.Context) -> bool:
    return getattr(ctx, "interaction", None) is not None


async def send_response(
    ctx: commands.Context,
    content: str | None = None,
    *,
    mention_author: bool = False,
    ephemeral: bool = False,
    **kwargs: Any,
):
    if is_interaction_context(ctx):
        await ctx.send(content=content, ephemeral=ephemeral, **kwargs)
        return

    await ctx.reply(content=content, mention_author=mention_author, **kwargs)


async def maybe_defer(ctx: commands.Context, *, ephemeral: bool = False):
    interaction = getattr(ctx, "interaction", None)
    if interaction and not interaction.response.is_done():
        await ctx.defer(ephemeral=ephemeral)


async def get_string_prefixes(bot: commands.Bot, message: discord.Message) -> list[str]:
    prefixes = await bot.get_prefix(message)
    if isinstance(prefixes, str):
        return [prefixes]
    return [prefix for prefix in prefixes if isinstance(prefix, str)]


async def looks_like_command(bot: commands.Bot, message: discord.Message) -> bool:
    return any(message.content.startswith(prefix) for prefix in await get_string_prefixes(bot, message))


def parse_emoji_tokens(raw: str) -> list[str]:
    return [token for token in raw.split() if token.strip()]


CUSTOM_EMOJI_RE = re.compile(r"^<(a?):([A-Za-z0-9_]+):(\d+)>$")
CUSTOM_EMOJI_ALIAS_RE = re.compile(r"^:([A-Za-z0-9_]+)(?:~\d+)?:$")
CUSTOM_EMOJI_ID_RE = re.compile(r"^\d{15,22}$")
PLAIN_CUSTOM_EMOJI_NAME_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")


def split_custom_status_input(raw: str) -> tuple[str | None, str]:
    normalized = (raw or "").strip()
    if "|" not in normalized:
        return None, normalized

    emoji_part, text_part = normalized.split("|", 1)
    emoji_candidate = emoji_part.strip()
    if not emoji_candidate or any(ch.isspace() for ch in emoji_candidate):
        return None, normalized

    return emoji_candidate, text_part.strip()


def looks_like_custom_emoji_reference(emoji_text: str | None) -> bool:
    token = (emoji_text or "").strip()
    if not token:
        return False

    return bool(
        CUSTOM_EMOJI_RE.fullmatch(token)
        or CUSTOM_EMOJI_ALIAS_RE.fullmatch(token)
        or CUSTOM_EMOJI_ID_RE.fullmatch(token)
    )


def _iter_custom_emoji_pool(bot: commands.Bot, guild: discord.Guild | None):
    seen_ids: set[int] = set()

    if guild is not None:
        for emoji in guild.emojis:
            if emoji.id not in seen_ids:
                seen_ids.add(emoji.id)
                yield emoji

    for emoji in bot.emojis:
        if emoji.id not in seen_ids:
            seen_ids.add(emoji.id)
            yield emoji


def normalize_presence_emoji_input(
    bot: commands.Bot,
    guild: discord.Guild | None,
    emoji_text: str | None,
) -> str | None:
    token = (emoji_text or "").strip()
    if not token:
        return None

    custom_match = CUSTOM_EMOJI_RE.fullmatch(token)
    if custom_match:
        animated = "a" if custom_match.group(1) else ""
        return f"<{animated}:{custom_match.group(2)}:{int(custom_match.group(3))}>"

    if CUSTOM_EMOJI_ID_RE.fullmatch(token):
        emoji = bot.get_emoji(int(token))
        return str(emoji) if emoji is not None else None

    alias_match = CUSTOM_EMOJI_ALIAS_RE.fullmatch(token)
    if alias_match:
        normalized_name = alias_match.group(1)
        for emoji in _iter_custom_emoji_pool(bot, guild):
            if emoji.name == normalized_name:
                return str(emoji)
        return None

    if PLAIN_CUSTOM_EMOJI_NAME_RE.fullmatch(token):
        for emoji in _iter_custom_emoji_pool(bot, guild):
            if emoji.name == token:
                return str(emoji)
        return None

    return token


def build_presence_emoji(emoji_text: str | None) -> discord.PartialEmoji | str | None:
    if not emoji_text:
        return None

    match = CUSTOM_EMOJI_RE.fullmatch(emoji_text)
    if match:
        return discord.PartialEmoji(
            name=match.group(2),
            id=int(match.group(3)),
            animated=bool(match.group(1)),
        )

    return emoji_text


def resolve_presence_status(status_name: str) -> discord.Status:
    normalized = (status_name or "online").lower()
    mapping = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "do_not_disturb": discord.Status.dnd,
        "invisible": discord.Status.invisible,
        "offline": discord.Status.invisible,
    }
    return mapping.get(normalized, discord.Status.online)


def build_presence_activity(
    activity_type: str,
    activity_text: str,
    activity_emoji: str | None = None,
) -> discord.BaseActivity | None:
    normalized = (activity_type or "listening").lower()
    if not activity_text:
        return None

    if normalized == "custom":
        display_text = activity_text
        if activity_emoji and not looks_like_custom_emoji_reference(activity_emoji):
            display_text = f"{activity_emoji} {activity_text}".strip()
        return discord.CustomActivity(
            name="Custom Status",
            state=display_text,
        )
    if normalized == "playing":
        return discord.Game(name=activity_text)

    type_map = {
        "listening": discord.ActivityType.listening,
        "watching": discord.ActivityType.watching,
        "competing": discord.ActivityType.competing,
    }
    return discord.Activity(type=type_map.get(normalized, discord.ActivityType.listening), name=activity_text)
