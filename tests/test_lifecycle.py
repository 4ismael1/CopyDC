from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

import main


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,purge", [("cached", False), ("accessible", False), ("unavailable", False), ("missing", True)]
)
async def test_startup_removal_requires_confirmation(outcome, purge):
    guild = SimpleNamespace(id=123, name=None)
    client = SimpleNamespace(
        is_ready=Mock(return_value=False),
        wait_until_ready=AsyncMock(),
        get_guild=Mock(return_value=guild if outcome == "cached" else None),
        fetch_guild=AsyncMock(return_value=guild),
    )
    if outcome in {"unavailable", "missing"}:
        status = 404 if outcome == "missing" else 503
        error = discord.NotFound if status == 404 else discord.HTTPException
        client.fetch_guild.side_effect = error(SimpleNamespace(status=status, reason="test"), "test")
    with (
        patch.object(main, "bot", client),
        patch.object(main.db, "remove_guild") as remove,
        patch.object(main.localization, "remove_guild_mode") as language,
        patch.object(main.log, "info") as info,
    ):
        await main.on_guild_remove(guild)
        assert remove.call_count == int(purge)
        assert language.call_count == int(purge)
        info.assert_not_called()


@pytest.mark.asyncio
async def test_real_removal_still_cleans_up():
    guild = SimpleNamespace(id=123, name="Example")
    client = SimpleNamespace(is_ready=Mock(return_value=True), guilds=[])
    with (
        patch.object(main, "bot", client),
        patch.object(main.db, "remove_guild") as remove,
        patch.object(main.localization, "remove_guild_mode"),
    ):
        await main.on_guild_remove(guild)
        remove.assert_called_once_with(guild)
