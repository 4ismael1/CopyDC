from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin_modules.owner_cog import GuildInfoView, ServerListView, ServerSearchModal, search_guilds


def guild(gid, name):
    return SimpleNamespace(id=gid, name=name, member_count=42, owner=None, created_at=datetime.now(UTC))


def test_search_exact_id_partial_name_and_stable_duplicates():
    bot = SimpleNamespace(
        guilds=[guild(2, "Alpha Test"), guild(3, "ALPHA"), guild(1, "Alpha"), guild(4, "Beta")]
    )
    assert [g.id for g in search_guilds(bot, " ALPHA ")] == [1, 3, 2]
    assert [g.id for g in search_guilds(bot, "2")] == [2]
    assert search_guilds(bot, "999") == []
    assert search_guilds(bot, "not found") == []


@pytest.mark.asyncio
async def test_empty_list_valid_select_and_disabled_navigation():
    view = ServerListView(SimpleNamespace(guilds=[]), 1, page_index=100)
    assert view.page_index == 0
    assert view.select.disabled
    assert len(view.select.options) == 1
    assert view.prev_page.disabled and view.next_page.disabled
    assert "No hay servidores" in view.build_list_embed().description


@pytest.mark.asyncio
async def test_page_clamps_and_refresh_after_guild_removal():
    bot = SimpleNamespace(guilds=[guild(i, "A" * 100) for i in range(31)])
    view = ServerListView(bot, 1, page_index=99)
    assert view.page_index == 3
    assert len(view.build_list_embed()) < 6000
    bot.guilds = bot.guilds[:2]
    view.refresh()
    assert view.page_index == 0
    assert len(view.select.options) == 2


@pytest.mark.asyncio
async def test_back_preserves_query_and_page():
    bot = SimpleNamespace(guilds=[guild(i, "Test") for i in range(20)])
    view = GuildInfoView(bot, 1, 10, back_to_list=(1, 10, "Test"))
    interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
    await view.btn_back.callback(interaction)
    rebuilt = interaction.response.edit_message.call_args.kwargs["view"]
    assert rebuilt.query == "Test" and rebuilt.page_index == 1


@pytest.mark.asyncio
async def test_owner_controls_and_modal_reject_other_user():
    bot = SimpleNamespace(guilds=[])
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=20), response=SimpleNamespace(send_message=AsyncMock())
    )
    for view in (ServerListView(bot, 10), GuildInfoView(bot, 1, 10)):
        assert not await view.interaction_check(interaction)
    await ServerSearchModal(bot, 10).on_submit(interaction)
    assert interaction.response.send_message.await_count == 3
