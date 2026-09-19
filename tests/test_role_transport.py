import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import pytest

from role_transport import change_roles, http_error_summary, latest_role_event


def failure(status, headers=None):
    return discord.HTTPException(
        SimpleNamespace(status=status, reason="failure", headers=headers or {}),
        "<html>upstream failed</html>",
    )


def member(status="online"):
    return SimpleNamespace(
        id=1, guild=SimpleNamespace(id=2), status=status, add_roles=AsyncMock(), remove_roles=AsyncMock()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 522, 429])
async def test_transient_role_failure_recovers(status):
    user = member()
    user.add_roles.side_effect = [failure(status, {"Retry-After": "75"}), None]
    with patch("role_transport.asyncio.sleep", new_callable=AsyncMock) as sleep:
        await change_roles(user, "role", add=True, reason="test")
    assert user.add_roles.await_count == 2
    sleep.assert_awaited_once_with(75 if status == 429 else 30)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,attempts", [(403, 1), (404, 1), (522, 3)])
async def test_permanent_failures_and_retry_limit(status, attempts):
    user = member()
    user.remove_roles.side_effect = failure(status)
    with (
        patch("role_transport.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(discord.HTTPException),
    ):
        await change_roles(user, "role", add=False, reason="test")
    assert user.remove_roles.await_count == attempts


@pytest.mark.asyncio
async def test_duplicate_events_coalesce_and_new_state_cancels_retry():
    entered, release = asyncio.Event(), asyncio.Event()
    user = member()
    user.add_roles.side_effect = failure(522)

    async def wait(_):
        entered.set()
        await release.wait()

    @latest_role_event
    async def handler(self, before, after):
        if after.status == "online":
            await change_roles(after, "role", add=True, reason="test")

    owner = object()
    with patch("role_transport.asyncio.sleep", side_effect=wait):
        task = asyncio.create_task(handler(owner, None, user))
        await entered.wait()
        await handler(owner, None, user)
        await handler(owner, None, member("offline"))
        release.set()
        await task
    assert user.add_roles.await_count == 1


def test_summary_does_not_print_response_html():
    assert http_error_summary(failure(522)) == "HTTP 522, Discord code 0"
