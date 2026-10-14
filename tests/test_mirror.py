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
    marker,
    message_parts,
    safe_username,
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
    [(10, False, None, True), (11, False, None, True), (10, True, None, False), (10, False, 9, False)],
)
def test_copies_everyone_but_ignores_bots_webhooks(author, bot, webhook, expected):
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
    assert webhook.send.call_args.kwargs["embed"] is None
    msg.content = "Updated"
    await cog.replicate(msg, pair(), edited=True)
    assert webhook.edit_message.call_args.kwargs["content"] == "Updated"
    await cog.mark_deleted(msg.id)
    kwargs = webhook.edit_message.call_args.kwargs
    assert "content" not in kwargs and "attachments" not in kwargs
    assert "eliminado" in kwargs["embed"].footer.text
    assert "ID original" not in kwargs["embed"].footer.text
    assert kwargs["embed"].timestamp is None
    assert store.messages(msg.id)


def test_marker_has_no_normal_footer_or_timestamp():
    assert marker(1001) is None
    for kwargs in ({"edited": True}, {"deleted": True}, {"notes": "Archivo no disponible"}):
        embed = marker(1001, **kwargs)
        assert embed.timestamp is None
        assert "1001" not in str(embed.to_dict())
        assert "Copia experimental" not in str(embed.to_dict())


@pytest.mark.asyncio
async def test_empty_unsupported_message_remains_sendable(store):
    seed(store)
    cog = MirrorCog(SimpleNamespace(get_guild=lambda _: SimpleNamespace(filesize_limit=10_000_000)))
    cog.store = store
    cog.pairs = {1: pair()}
    webhook = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=2001)))
    cog.webhook = AsyncMock(return_value=webhook)
    msg = message()
    msg.content = ""
    assert await cog.replicate(msg, pair(), edited=False)
    assert webhook.send.call_args.kwargs["content"] == "[Mensaje sin contenido compatible]"


async def history_stream(messages):
    for msg in messages:
        yield msg


@pytest.mark.asyncio
async def test_history_counts_all_users_and_reverses_selected_messages():
    cog = MirrorCog(SimpleNamespace())
    messages = [message(author=11), message(bot=True), message(webhook=3), message(), message(), message()]
    for i, msg in enumerate(messages):
        msg.id = 1100 - i
    channel = SimpleNamespace(history=Mock(return_value=history_stream(messages)))
    cutoff = datetime.now(UTC)
    ids = await cog.collect_history_ids(channel, pair(), 2, cutoff, lambda: None)
    assert ids == [1097, 1100]
    channel.history.assert_called_once_with(limit=None, before=cutoff, oldest_first=False)


@pytest.mark.asyncio
async def test_history_skips_existing_and_fetches_before_copy(store):
    seed(store)
    store.write("INSERT INTO mirror_channels VALUES (102, 1, 202, 302)")
    store.write("INSERT INTO mirror_messages VALUES (1001, 0, 101, 2001)")
    old, new = message(), message()
    new.id = 1002
    channel = old.channel
    channel.history = Mock(return_value=history_stream([new, old]))
    channel.fetch_message = AsyncMock(return_value=new)
    bot = SimpleNamespace(
        get_channel=Mock(side_effect=lambda channel_id: channel if channel_id == 101 else None),
        get_guild=lambda _: SimpleNamespace(owner_id=10, filesize_limit=10_000_000),
    )
    cog = MirrorCog(bot)
    cog.store = store
    cog.pairs = {1: pair()}
    webhook = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=2002)))
    cog.webhook = AsyncMock(return_value=webhook)
    ctx = SimpleNamespace(send=AsyncMock(), channel=SimpleNamespace(id=201))
    await cog.import_history(ctx, 1, 2, 2)
    channel.fetch_message.assert_awaited_once_with(1002)
    bot.get_channel.assert_called_once_with(101)
    webhook.send.assert_awaited_once()
    assert store.messages(1002)[0]["destination_message"] == 2002
    assert "1 mensajes copiados; 1 omitidos" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
async def test_history_in_unlinked_destination_channel_reads_no_history(store):
    seed(store)
    bot = SimpleNamespace(
        get_channel=Mock(),
        get_guild=lambda _: SimpleNamespace(owner_id=10),
    )
    cog = MirrorCog(bot)
    cog.store = store
    cog.pairs = {1: pair()}
    ctx = SimpleNamespace(send=AsyncMock(), channel=SimpleNamespace(id=999))
    await cog.import_history(ctx, 1, 2, 10)
    bot.get_channel.assert_not_called()
    assert "no está enlazado" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
async def test_history_checks_state_and_guilds():
    cog = MirrorCog(SimpleNamespace(get_guild=lambda _: None))
    cog.pairs = {1: pair()}
    with pytest.raises(ValueError):
        cog.history_pair(1, 2)
    cog.bot.get_guild = lambda _: SimpleNamespace(owner_id=10)
    cog.pairs[1]["state"] = "paused"
    with pytest.raises(ValueError):
        cog.history_pair(1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, -1, 1001])
async def test_history_rejects_invalid_amount(amount):
    cog = MirrorCog(SimpleNamespace())
    ctx = SimpleNamespace(reply=AsyncMock())
    await cog.history.callback(cog, ctx, amount)
    assert not cog.history_tasks
    ctx.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_cancel_is_cooperative():
    task = SimpleNamespace(cancel=Mock())
    cog = MirrorCog(SimpleNamespace())
    cog.history_tasks[2] = task
    ctx = SimpleNamespace(guild=SimpleNamespace(id=2), reply=AsyncMock())
    await cog.history_cancel.callback(cog, ctx)
    assert task.cancel_requested
    task.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_history_rejects_second_concurrent_job():
    cog = MirrorCog(SimpleNamespace())
    cog.pairs = {1: pair()}
    task = SimpleNamespace()
    cog.history_tasks[2] = task
    ctx = SimpleNamespace(guild=SimpleNamespace(id=2), reply=AsyncMock())
    await cog.history.callback(cog, ctx, 50)
    assert cog.history_tasks[2] is task
    assert "en curso" in ctx.reply.call_args.args[0]


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
    with pytest.raises(ValueError, match="dueño de Copy"):
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
async def test_setup_controls_silently_reject_non_owner():
    view = MirrorSetupView(
        SimpleNamespace(), SimpleNamespace(id=1, channels=[]), SimpleNamespace(id=2, channels=[]), 10
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=11),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
    )
    assert not await view.interaction_check(interaction)
    interaction.response.send_message.assert_not_called()
    interaction.response.defer.assert_awaited_once()


def test_mirror_commands_hidden_and_owner_only():
    cog = MirrorCog(SimpleNamespace())
    assert cog.mirror.hidden
    for command in cog.mirror.walk_commands():
        assert command.checks, command.name


def test_validate_does_not_require_owning_servers():
    guild = SimpleNamespace(
        owner_id=999, unavailable=False, features=[], text_channels=[], channels=[],
        me=SimpleNamespace(guild_permissions=SimpleNamespace(administrator=True)),
    )
    cog = MirrorCog(SimpleNamespace(owner_id=10, get_guild=lambda _: guild, intents=SimpleNamespace(message_content=True)))
    # Pasa la comprobación de dueño y llega a la siguiente validación (origen sin canales).
    with pytest.raises(ValueError, match="al menos un canal"):
        cog.validate(1, 2, 10)


@pytest.mark.asyncio
async def test_reply_links_to_destination_copy(store):
    seed(store)
    store.write("INSERT INTO mirror_messages VALUES (1000, 0, 101, 2000)")
    cog = MirrorCog(SimpleNamespace(get_guild=lambda _: SimpleNamespace(filesize_limit=10_000_000)))
    cog.store = store
    cog.pairs = {1: pair()}
    webhook = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=2001)))
    cog.webhook = AsyncMock(return_value=webhook)
    original = Mock(spec=discord.Message)
    original.content, original.attachments = "probando login", []
    original.author = SimpleNamespace(display_name="Ana")
    msg = message(author=11)
    msg.content = "ya funciona"
    msg.reference = SimpleNamespace(message_id=1000, resolved=original, type=None)
    await cog.replicate(msg, pair(), edited=False)
    content = webhook.send.call_args.kwargs["content"]
    assert content.startswith("> ↪️ **Ana**: probando login")
    assert "https://discord.com/channels/2/201/2000" in content
    assert content.endswith("\nya funciona")
    assert webhook.send.call_args.kwargs["embed"] is None


@pytest.mark.asyncio
async def test_reply_to_unknown_message_has_no_link(store):
    cog = MirrorCog(SimpleNamespace())
    cog.store = store
    msg = message()
    msg.reference = SimpleNamespace(message_id=5, resolved=None, type=None)
    header = await cog.reply_header(msg, pair())
    assert "no disponible" in header and "discord.com" not in header


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ana", "Ana"),
        ("discordia", "d​iscordia"),
        ("Clyde", "C​lyde"),
        ("everyone", "Usuario del espejo"),
        ("   ", "Usuario del espejo"),
        ("x" * 100, "x" * 80),
    ],
)
def test_safe_username_blocks_webhook_rejections(raw, expected):
    result = safe_username(raw)
    assert result == expected
    assert 1 <= len(result) <= 80
    assert "discord" not in result.lower() and "clyde" not in result.lower()
