from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

import database as db
from admin_modules.mirror_cog import (
    MirrorCog,
    MirrorConfirmation,
    MirrorSetupView,
    MirrorStore,
    message_parts,
    permitted_message,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path / "mirror.db"))
    store = MirrorStore()
    store.init()
    return store


def pair(state="active"):
    return dict(source=1, destination=2, owner=10, state=state)


def message(author=10, bot=False, webhook=None):
    channel = Mock(spec=discord.TextChannel)
    channel.id = 101
    return SimpleNamespace(
        id=1001,
        guild=SimpleNamespace(id=1),
        channel=channel,
        author=SimpleNamespace(
            id=author,
            bot=bot,
            display_name="Owner",
            display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
        ),
        webhook_id=webhook,
        content="Hello",
        stickers=[],
        attachments=[],
        embeds=[],
        reference=None,
        created_at=datetime.now(UTC),
    )


def seed(store):
    store.begin(1, 2, 10)
    store.write("INSERT INTO mirror_channels VALUES (101, 1, 201, 301)")
    store.state(1, "active")


def test_persistence_and_interrupted_setup(store):
    seed(store)
    store.write("INSERT INTO mirror_messages VALUES (1001, 0, 101, 2001)")
    store.begin(3, 4, 10)
    store.init()
    assert store.messages(1001)[0]["destination_message"] == 2001
    assert {p["source"]: p["state"] for p in store.pairs()} == {1: "active", 3: "error"}


def test_stop_then_reconfigure_removes_old_mappings_only(store):
    seed(store)
    store.write("INSERT INTO mirror_messages VALUES (1001, 0, 101, 2001)")
    store.state(1, "stopped")
    store.begin(1, 3, 10)
    assert store.messages(1001) == []
    assert store.channel(101) is None
    assert store.pairs()[0]["destination"] == 3


@pytest.mark.parametrize(
    "author,bot,webhook,expected",
    [(10, False, None, True), (11, False, None, False), (10, True, None, False), (10, False, 9, False)],
)
def test_ignore_other_people_bots_webhooks(author, bot, webhook, expected):
    assert permitted_message(message(author, bot, webhook), pair()) == expected


def test_long_text_not_truncated():
    msg = message()
    msg.content = "abc" * 1400
    parts = message_parts(msg)
    assert "".join(parts) == msg.content
    assert all(len(p) <= 2000 for p in parts)


@pytest.mark.asyncio
async def test_create_idempotent_edit_and_delete_keeps_content(store):
    seed(store)
    bot = SimpleNamespace(get_guild=lambda _: SimpleNamespace(filesize_limit=10_000_000))
    cog = MirrorCog(bot)
    cog.store = store
    cog.pairs = {1: pair()}
    webhook = SimpleNamespace(
        send=AsyncMock(return_value=SimpleNamespace(id=2001)),
        edit_message=AsyncMock(),
        fetch_message=AsyncMock(return_value=SimpleNamespace(embeds=[])),
    )
    cog.webhook = AsyncMock(return_value=webhook)
    msg = message()
    await cog.replicate(msg, pair(), edited=False)
    await cog.replicate(msg, pair(), edited=False)
    assert webhook.send.await_count == 1
    assert webhook.send.call_args.kwargs["allowed_mentions"].everyone is False
    msg.content = "Updated"
    await cog.replicate(msg, pair(), edited=True)
    assert webhook.edit_message.call_args.kwargs["content"] == "Updated"
    await cog.mark_deleted(msg.id)
    kwargs = webhook.edit_message.call_args.kwargs
    assert "content" not in kwargs and "attachments" not in kwargs
    assert "eliminado" in kwargs["embed"].footer.text
    assert store.messages(msg.id)


@pytest.mark.asyncio
async def test_deleted_copy_does_not_break_delete_event(store):
    seed(store)
    store.write("INSERT INTO mirror_messages VALUES (1001, 0, 101, 2001)")
    cog = MirrorCog(SimpleNamespace())
    cog.store = store
    cog.webhook = AsyncMock(
        return_value=SimpleNamespace(
            fetch_message=AsyncMock(
                side_effect=discord.NotFound(SimpleNamespace(status=404, reason="missing"), "missing")
            )
        )
    )
    await cog.mark_deleted(1001)


@pytest.mark.asyncio
async def test_invalid_confirmation_never_calls_setup():
    cog = SimpleNamespace(run_setup=AsyncMock())
    source = SimpleNamespace(id=1, channels=[])
    dest = SimpleNamespace(id=2, channels=[])
    view = MirrorSetupView(cog, source, dest, 10)
    modal = MirrorConfirmation(view)
    modal.destination_id._value = "1"
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=10), response=SimpleNamespace(send_message=AsyncMock())
    )
    await modal.on_submit(interaction)
    cog.run_setup.assert_not_called()


@pytest.mark.asyncio
async def test_changed_inventory_aborts_before_deleting(store):
    cog = MirrorCog(SimpleNamespace(get_guild=lambda _: None))
    cog.store = store
    channel = SimpleNamespace(id=201, delete=AsyncMock())
    source = SimpleNamespace(id=1, channels=[])
    destination = SimpleNamespace(id=2, channels=[channel])
    cog.validate = Mock(return_value=(source, destination))
    cog.report = AsyncMock()
    plan = SimpleNamespace(source=1, destination=2, owner=10, source_ids=set(), destination_ids=set())
    await cog.run_setup(SimpleNamespace(), plan)
    channel.delete.assert_not_called()
    assert store.pairs() == []


def test_validate_rejects_same_server_or_other_owner():
    guild = SimpleNamespace(owner_id=10)
    cog = MirrorCog(SimpleNamespace(owner_id=10, get_guild=lambda _: guild))
    with pytest.raises(ValueError, match="distintos"):
        cog.validate(1, 1, 10)
    with pytest.raises(ValueError, match="propietario"):
        cog.validate(1, 2, 99)


@pytest.mark.asyncio
async def test_paused_pair_does_not_enqueue():
    cog = MirrorCog(SimpleNamespace())
    cog.pairs = {1: pair("paused")}
    await cog.on_message(message())
    assert cog.queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_setup_writes_only_to_destination_and_stops_on_failure(store, fail):
    original = Mock(spec=discord.TextChannel)
    original.id, original.position, original.category_id = 101, 0, None
    original.name, original.topic, original.nsfw, original.slowmode_delay = "general", "Test", False, 0
    original.delete = AsyncMock()
    source = SimpleNamespace(id=1, channels=[original], categories=[])
    old_channel = SimpleNamespace(id=201, delete=AsyncMock())
    if fail:
        old_channel.delete.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="test"), "test")
    hook = SimpleNamespace(id=301)
    clone = SimpleNamespace(id=202, create_webhook=AsyncMock(return_value=hook))
    destination = SimpleNamespace(
        id=2, channels=[old_channel], create_text_channel=AsyncMock(return_value=clone)
    )
    cog = MirrorCog(SimpleNamespace(get_guild=lambda _: destination))
    cog.store = store
    cog.validate = Mock(return_value=(source, destination))
    cog.report = AsyncMock()
    plan = SimpleNamespace(source=1, destination=2, owner=10, source_ids={101}, destination_ids={201})
    await cog.run_setup(SimpleNamespace(channel_id=201), plan)
    original.delete.assert_not_called()
    old_channel.delete.assert_awaited_once()
    assert store.pairs()[0]["state"] == ("error" if fail else "active")
    if fail:
        destination.create_text_channel.assert_not_called()
    else:
        assert store.channel(101)["destination_channel"] == 202
        assert destination.create_text_channel.call_args.kwargs["overwrites"] == {}


@pytest.mark.asyncio
async def test_setup_controls_reject_non_owner():
    view = MirrorSetupView(
        SimpleNamespace(), SimpleNamespace(id=1, channels=[]), SimpleNamespace(id=2, channels=[]), 10
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=11), response=SimpleNamespace(send_message=AsyncMock())
    )
    assert not await view.interaction_check(interaction)
