"""Bounded recovery for idempotent role writes after Discord transport failures."""

import asyncio
import json
import logging
import math
from contextlib import suppress
from contextvars import ContextVar
from functools import wraps

import discord

log = logging.getLogger("bot")
_current = ContextVar("role_event_current", default=lambda: True)


class SupersededRoleEvent(Exception):
    pass


def latest_role_event(handler):
    """Invalidate sleeping retries when a newer member event arrives; keep no history."""
    active = {}

    @wraps(handler)
    async def wrapped(self, before, after):
        key = (id(self), after.guild.id, after.id)
        primary = getattr(after, "primary_guild", None)
        signature = (
            getattr(primary, "id", None),
            getattr(primary, "tag", None),
            getattr(primary, "identity_enabled", None),
            str(getattr(after, "status", None)),
            tuple(
                (str(a.type), getattr(a, "name", None), getattr(a, "state", None))
                for a in getattr(after, "activities", ())
            ),
        )
        if key in active and active[key][1] == signature:
            return None
        marker = object()
        entry = (marker, signature)
        active[key] = entry
        token = _current.set(lambda: active.get(key) is entry)
        try:
            return await handler(self, before, after)
        except SupersededRoleEvent:
            return None
        finally:
            _current.reset(token)
            if active.get(key) is entry:
                active.pop(key, None)

    return wrapped


def http_error_summary(exc):
    return f"HTTP {exc.status}, Discord code {exc.code}"


def retry_delay(exc, attempt):
    delay = (30, 60)[attempt]
    if exc.status == 429:
        candidates = [getattr(exc.response, "headers", {}).get("Retry-After")]
        with suppress(ValueError, TypeError, AttributeError):
            candidates.append(json.loads(exc.text).get("retry_after"))
        for value in candidates:
            try:
                seconds = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(seconds) and seconds >= 0:
                delay = max(delay, seconds)
    return delay


async def change_roles(member, *roles, add, reason):
    """Only retry role PUT/DELETE, never notification sends or permission failures."""
    operation = member.add_roles if add else member.remove_roles
    for attempt in range(3):
        if not _current.get()():
            raise SupersededRoleEvent
        try:
            await operation(*roles, reason=reason)
            return
        except discord.HTTPException as exc:
            if exc.status != 429 and not 500 <= exc.status < 600:
                raise
            if attempt == 2:
                raise
            delay = retry_delay(exc, attempt)
            # Do not retry early when Discord requests an unusually long cooldown.
            if delay > 300:
                raise
            log.warning(
                "Cambio de rol temporalmente pendiente guild=%s member=%s: %s; reintento %s/2 en %.1fs",
                member.guild.id,
                member.id,
                http_error_summary(exc),
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)
