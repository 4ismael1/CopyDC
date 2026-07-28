from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import logging
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands, tasks

import database as db
from command_utils import maybe_defer, send_response
from localization import get_language, translate, translate_language

log = logging.getLogger("bot")
MAX_SUBJECT_LENGTH = 100
MAX_TRANSCRIPT_MESSAGES = 25_000


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def safe_channel_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.casefold()).strip("-")
    return normalized[:45] or "soporte"


def safe_external_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "#"
    if parsed.scheme.casefold() not in {"https", "http"} or not parsed.netloc:
        return "#"
    return html.escape(value, quote=True)


def _message_record(message: Any) -> dict[str, Any]:
    attachments = [
        {
            "filename": attachment.filename,
            "url": attachment.url,
            "size": attachment.size,
            "content_type": attachment.content_type,
        }
        for attachment in message.attachments
    ]
    embeds = []
    for embed in message.embeds:
        data = embed.to_dict()
        embeds.append(
            {
                "title": data.get("title"),
                "description": data.get("description"),
                "url": data.get("url"),
                "type": data.get("type"),
            }
        )
    return {
        "id": message.id,
        "author_id": message.author.id,
        "author_name": str(message.author),
        "author_display_name": getattr(message.author, "display_name", str(message.author)),
        "author_avatar": str(message.author.display_avatar.url),
        "content": message.content,
        "created_at": message.created_at.astimezone(UTC).isoformat(timespec="seconds"),
        "edited_at": (
            message.edited_at.astimezone(UTC).isoformat(timespec="seconds") if message.edited_at else None
        ),
        "attachments": attachments,
        "embeds": embeds,
    }


def _render_message(record: dict[str, Any], language: str) -> str:
    author = html.escape(record["author_display_name"])
    username = html.escape(record["author_name"])
    avatar = safe_external_url(record["author_avatar"])
    timestamp = html.escape(record["created_at"])
    edited = (
        " · " + html.escape(translate_language(language, "support.transcript.edited"))
        if record["edited_at"]
        else ""
    )
    content = html.escape(record["content"] or "").replace("\n", "<br>")
    if not content:
        empty = html.escape(translate_language(language, "support.transcript.empty"))
        content = f'<span class="muted">{empty}</span>'

    attachment_html = ""
    if record["attachments"]:
        items = []
        for attachment in record["attachments"]:
            filename = html.escape(attachment["filename"])
            url = safe_external_url(attachment["url"])
            size = int(attachment["size"] or 0)
            items.append(
                f'<li><a href="{url}" rel="noreferrer">{filename}</a> '
                f'<span class="muted">('
                f"{html.escape(translate_language(language, 'support.transcript.attachment_bytes', size=f'{size:,}'))}"
                f")</span></li>"
            )
        attachment_html = f'<ul class="attachments">{"".join(items)}</ul>'

    embed_html = ""
    if record["embeds"]:
        cards = []
        for embed in record["embeds"]:
            title = html.escape(embed.get("title") or "Embed")
            description = html.escape(embed.get("description") or "").replace("\n", "<br>")
            raw_url = embed.get("url") or ""
            url = safe_external_url(raw_url)
            linked_title = (
                f'<a href="{url}" rel="noreferrer">{title}</a>' if raw_url and url != "#" else title
            )
            cards.append(f'<div class="embed"><strong>{linked_title}</strong><br>{description}</div>')
        embed_html = "".join(cards)

    return (
        '<article class="message">'
        f'<img class="avatar" src="{avatar}" alt="">'
        '<div class="message-body">'
        f'<header><strong>{author}</strong> <span class="muted">{username} · {timestamp}{edited}</span></header>'
        f'<div class="content">{content}</div>{attachment_html}{embed_html}'
        f'<footer class="muted">'
        f"{html.escape(translate_language(language, 'support.transcript.message_id'))}: {record['id']} · "
        f"{html.escape(translate_language(language, 'support.transcript.user_id'))}: {record['author_id']}"
        f"</footer>"
        "</div></article>"
    )


def build_transcript_html(
    *,
    guild_name: str,
    channel_name: str,
    case_id: int,
    subject: str,
    opener_id: int,
    closed_by: str,
    close_reason: str,
    records: list[dict[str, Any]],
    language: str = "en",
) -> tuple[bytes, str]:
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    messages = "".join(_render_message(record, language) for record in records)
    escaped_reason = html.escape(close_reason)
    escaped_guild = html.escape(guild_name)
    escaped_channel = html.escape(channel_name)
    escaped_closer = html.escape(closed_by)

    document = f"""<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: http:; style-src 'unsafe-inline'">
<title>{html.escape(translate_language(language, "support.transcript.title", case_id=case_id, subject=subject))}</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
body {{ background:#111214; color:#dbdee1; margin:0; padding:24px; }}
main {{ max-width:980px; margin:auto; }}
.summary,.message {{ background:#1e1f22; border:1px solid #2b2d31; border-radius:10px; }}
.summary {{ padding:20px; margin-bottom:18px; }}
.message {{ display:flex; gap:12px; padding:14px; margin:10px 0; }}
.avatar {{ width:42px; height:42px; border-radius:50%; object-fit:cover; }}
.message-body {{ min-width:0; flex:1; }}
.content {{ margin:5px 0 8px; overflow-wrap:anywhere; }}
.muted {{ color:#949ba4; font-size:.85rem; }}
.attachments {{ margin:8px 0; }}
.embed {{ border-left:4px solid #5865f2; background:#2b2d31; padding:10px; margin:8px 0; }}
a {{ color:#00a8fc; }}
footer {{ margin-top:7px; }}
</style>
</head>
<body><main>
<section class="summary">
<h1>{html.escape(translate_language(language, "support.intro.title", case_id=case_id, subject=subject))}</h1>
<p><strong>{html.escape(translate_language(language, "support.transcript.server"))}:</strong> {escaped_guild}<br>
<strong>{html.escape(translate_language(language, "support.transcript.channel"))}:</strong> #{escaped_channel}<br>
<strong>{html.escape(translate_language(language, "support.transcript.opener"))}:</strong> {opener_id}<br>
<strong>{html.escape(translate_language(language, "support.transcript.closed_by"))}:</strong> {escaped_closer}<br>
<strong>{html.escape(translate_language(language, "support.transcript.reason"))}:</strong> {escaped_reason}<br>
<strong>{html.escape(translate_language(language, "support.transcript.messages"))}:</strong> {len(records)}<br>
<strong>SHA-256:</strong> <code>{digest}</code></p>
</section>
{messages}
</main></body></html>"""
    return document.encode("utf-8"), digest


def package_transcript(
    transcript: bytes,
    *,
    html_filename: str,
    max_bytes: int,
) -> tuple[bytes, str] | None:
    if len(transcript) <= max_bytes:
        return transcript, html_filename

    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zip_file:
        zip_file.writestr(html_filename, transcript)
    payload = archive.getvalue()
    if len(payload) > max_bytes:
        return None
    return payload, html_filename.removesuffix(".html") + ".zip"


class SupportCasesCog(commands.Cog):
    """Casos privados de soporte con expediente íntegro al cierre."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._closing_channels: set[int] = set()
        self.cleanup_expired_archives.start()

    def cog_unload(self):
        self.cleanup_expired_archives.cancel()

    @staticmethod
    def _is_support(member: discord.Member, settings: Any) -> bool:
        return member.guild_permissions.manage_channels or any(
            role.id == settings["support_role_id"] for role in member.roles
        )

    async def _settings(self, guild_id: int):
        return await asyncio.to_thread(db.get_support_settings, guild_id)

    @commands.hybrid_group(
        name="case",
        invoke_without_command=True,
        fallback="panel",
        description="Gestiona casos privados de soporte",
    )
    @commands.guild_only()
    async def case(self, ctx: commands.Context):
        await send_response(
            ctx,
            translate(ctx, "support.help"),
            ephemeral=True,
        )

    @case.command(name="setup", description="Configura los casos y su archivo privado")
    @app_commands.describe(
        archive_channel="Canal privado donde se publicarán los expedientes",
        category="Categoría donde se crearán los casos",
        support_role="Rol del equipo que podrá ver y cerrar casos",
        retention_days="Días que se conservará cada expediente (1-90)",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def case_setup(
        self,
        ctx: commands.Context,
        archive_channel: discord.TextChannel,
        category: discord.CategoryChannel,
        support_role: discord.Role,
        retention_days: int = 30,
    ):
        if not 1 <= retention_days <= 90:
            await send_response(ctx, translate(ctx, "support.config_retention"), ephemeral=True)
            return
        if support_role.is_default():
            await send_response(
                ctx,
                translate(ctx, "support.config_role_everyone"),
                ephemeral=True,
            )
            return
        if archive_channel.permissions_for(ctx.guild.default_role).view_channel:
            await send_response(
                ctx,
                translate(ctx, "support.config_archive_public"),
                ephemeral=True,
            )
            return
        me = ctx.guild.me
        if me is None or not archive_channel.permissions_for(me).send_messages:
            await send_response(
                ctx,
                translate(ctx, "support.config_archive_permissions"),
                ephemeral=True,
            )
            return
        await asyncio.to_thread(
            db.set_support_settings,
            ctx.guild.id,
            archive_channel.id,
            category.id,
            support_role.id,
            retention_days,
        )
        await send_response(
            ctx,
            translate(
                ctx,
                "support.config_success",
                category=category.name,
                archive=archive_channel.mention,
                role=support_role.mention,
                days=retention_days,
            ),
        )

    @case.command(name="open", description="Abre un caso privado con el equipo de soporte")
    @app_commands.describe(subject="Resumen breve del motivo del caso")
    @commands.bot_has_permissions(manage_channels=True)
    async def case_open(self, ctx: commands.Context, *, subject: str):
        settings = await self._settings(ctx.guild.id)
        if settings is None:
            await send_response(ctx, translate(ctx, "support.not_configured"), ephemeral=True)
            return
        subject = subject.strip()
        if not subject or len(subject) > MAX_SUBJECT_LENGTH:
            await send_response(
                ctx,
                translate(ctx, "support.subject_invalid", limit=MAX_SUBJECT_LENGTH),
                ephemeral=True,
            )
            return
        existing = await asyncio.to_thread(
            db.get_open_support_case_for_user,
            ctx.guild.id,
            ctx.author.id,
        )
        if existing is not None:
            channel = ctx.guild.get_channel(existing["channel_id"])
            if channel is not None:
                await send_response(
                    ctx,
                    translate(
                        ctx,
                        "support.already_open",
                        case_id=existing["case_id"],
                        channel=channel.mention,
                    ),
                    ephemeral=True,
                )
                return
            await asyncio.to_thread(db.delete_support_case_record, existing["case_id"])
        category = ctx.guild.get_channel(settings["category_id"])
        support_role = ctx.guild.get_role(settings["support_role_id"])
        me = ctx.guild.me
        if not isinstance(category, discord.CategoryChannel) or support_role is None or me is None:
            await send_response(
                ctx,
                translate(ctx, "support.category_missing"),
                ephemeral=True,
            )
            return

        await maybe_defer(ctx, ephemeral=True)
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.author: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }
        channel = await ctx.guild.create_text_channel(
            name=f"case-{safe_channel_slug(ctx.author.display_name)}",
            category=category,
            overwrites=overwrites,
            topic=f"Support case | opener={ctx.author.id} | {subject}",
            reason=f"Support case opened by {ctx.author} ({ctx.author.id})",
        )
        try:
            case_id = await asyncio.to_thread(
                db.create_support_case,
                ctx.guild.id,
                channel.id,
                ctx.author.id,
                subject,
                utc_now_iso(),
            )
        except sqlite3.IntegrityError:
            await channel.delete(reason="Rollback: duplicate support case")
            await send_response(
                ctx,
                translate(ctx, "support.duplicate"),
                ephemeral=True,
            )
            return
        except Exception:
            await channel.delete(reason="Rollback: support case could not be persisted")
            raise

        await channel.edit(name=f"case-{case_id}-{safe_channel_slug(ctx.author.display_name)}")
        embed = discord.Embed(
            title=translate(ctx, "support.intro.title", case_id=case_id, subject=subject),
            description=translate(
                ctx,
                "support.intro.description",
                user=ctx.author.mention,
                role=support_role.mention,
            ),
            color=0x5865F2,
        )
        embed.set_footer(text=translate(ctx, "support.intro.footer"))
        await channel.send(
            content=f"{ctx.author.mention} {support_role.mention}",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False),
        )
        await send_response(
            ctx,
            translate(ctx, "support.created", case_id=case_id, channel=channel.mention),
            ephemeral=True,
        )

    @case.command(name="close", description="Cierra el caso actual y genera su expediente completo")
    @app_commands.describe(reason="Motivo o resolución del cierre")
    @commands.bot_has_permissions(manage_channels=True)
    async def case_close(self, ctx: commands.Context, *, reason: str = ""):
        case = await asyncio.to_thread(db.get_support_case_by_channel, ctx.channel.id)
        if case is None or case["guild_id"] != ctx.guild.id:
            await send_response(ctx, translate(ctx, "support.not_case"), ephemeral=True)
            return
        if case["status"] != "open":
            await send_response(ctx, translate(ctx, "support.already_closed"), ephemeral=True)
            return
        settings = await self._settings(ctx.guild.id)
        if settings is None:
            await send_response(ctx, translate(ctx, "support.settings_deleted"), ephemeral=True)
            return
        member = ctx.author
        if member.id != case["opener_id"] and not self._is_support(member, settings):
            await send_response(
                ctx,
                translate(ctx, "support.close_permission"),
                ephemeral=True,
            )
            return
        reason = reason.strip()[:300] or translate(ctx, "support.default_reason")
        if ctx.channel.id in self._closing_channels:
            await send_response(ctx, translate(ctx, "support.close_in_progress"), ephemeral=True)
            return

        archive_channel = ctx.guild.get_channel(settings["archive_channel_id"])
        if not isinstance(archive_channel, discord.TextChannel):
            await send_response(
                ctx,
                translate(ctx, "support.channel_archive_missing"),
                ephemeral=True,
            )
            return

        self._closing_channels.add(ctx.channel.id)
        try:
            await maybe_defer(ctx, ephemeral=True)
            messages = [
                message
                async for message in ctx.channel.history(
                    limit=MAX_TRANSCRIPT_MESSAGES + 1,
                    oldest_first=True,
                )
            ]
            records = [_message_record(message) for message in messages]
            transcript, digest = await asyncio.to_thread(
                build_transcript_html,
                guild_name=ctx.guild.name,
                channel_name=ctx.channel.name,
                case_id=case["case_id"],
                subject=case["subject"],
                opener_id=case["opener_id"],
                closed_by=f"{ctx.author} ({ctx.author.id})",
                close_reason=reason,
                records=records,
                language=get_language(ctx),
            )
            if len(messages) > MAX_TRANSCRIPT_MESSAGES:
                await send_response(
                    ctx,
                    translate(
                        ctx,
                        "support.close_limit",
                        limit=f"{MAX_TRANSCRIPT_MESSAGES:,}",
                    ),
                    ephemeral=True,
                )
                return
            packaged = await asyncio.to_thread(
                package_transcript,
                transcript,
                html_filename=f"case-{case['case_id']}-transcript.html",
                max_bytes=ctx.guild.filesize_limit,
            )
            if packaged is None:
                await send_response(
                    ctx,
                    translate(ctx, "support.upload_too_large"),
                    ephemeral=True,
                )
                return
            transcript_payload, transcript_filename = packaged

            archive_embed = discord.Embed(
                title=translate(ctx, "support.archive.title", case_id=case["case_id"]),
                description=(
                    f"**{case['subject']}**\n" + translate(ctx, "support.archive.close_reason", reason=reason)
                ),
                color=0x57F287,
                timestamp=datetime.now(UTC),
            )
            archive_embed.add_field(
                name=translate(ctx, "support.archive.channel"),
                value=f"`{ctx.channel.name}` · `{ctx.channel.id}`",
            )
            archive_embed.add_field(
                name=translate(ctx, "support.archive.messages"),
                value=str(len(records)),
            )
            archive_embed.add_field(name="SHA-256", value=f"`{digest}`", inline=False)
            archive_embed.set_footer(
                text=translate(
                    ctx,
                    "support.archive.footer",
                    days=settings["retention_days"],
                )
            )
            archive_message = await archive_channel.send(
                embed=archive_embed,
                file=discord.File(
                    io.BytesIO(transcript_payload),
                    filename=transcript_filename,
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            changed = await asyncio.to_thread(
                db.close_support_case,
                case["case_id"],
                archive_channel.id,
                archive_message.id,
                utc_now_iso(),
            )
            if not changed:
                await archive_message.delete()
                await send_response(
                    ctx,
                    translate(ctx, "support.close_concurrent"),
                    ephemeral=True,
                )
                return

            opener = ctx.guild.get_member(case["opener_id"])
            if opener is not None:
                await ctx.channel.set_permissions(
                    opener,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                    reason=f"Support case #{case['case_id']} closed",
                )
            await ctx.channel.edit(
                name=f"closed-{case['case_id']}",
                topic=f"Closed support case #{case['case_id']} | Archive message {archive_message.id}",
                reason=f"Support case #{case['case_id']} closed",
            )
            await send_response(
                ctx,
                translate(
                    ctx,
                    "support.close_success",
                    case_id=case["case_id"],
                    count=len(records),
                ),
                ephemeral=True,
            )
        finally:
            self._closing_channels.discard(ctx.channel.id)

    @case.command(name="list", description="Lista casos abiertos o cerrados")
    @app_commands.describe(status="Estado: open o closed")
    @commands.has_permissions(manage_channels=True)
    async def case_list(self, ctx: commands.Context, status: str = "open"):
        status = status.casefold().strip()
        if status not in {"open", "closed"}:
            await send_response(ctx, translate(ctx, "support.status_invalid"), ephemeral=True)
            return
        rows = await asyncio.to_thread(db.get_support_cases_for_guild, ctx.guild.id, status)
        if not rows:
            await send_response(
                ctx,
                translate(ctx, "support.list.empty", status=status),
                ephemeral=True,
            )
            return
        lines = []
        for row in rows[:20]:
            channel = ctx.guild.get_channel(row["channel_id"])
            target = channel.mention if channel else f"`{row['channel_id']}`"
            lines.append(
                f"**#{row['case_id']}** · {target} · {discord.utils.escape_markdown(row['subject'])}"
            )
        embed = discord.Embed(
            title=translate(ctx, "support.list.title", status=status),
            description="\n".join(lines),
            color=0x5865F2,
        )
        if len(rows) > 20:
            embed.set_footer(text=translate(ctx, "support.list.footer", count=len(rows)))
        await send_response(ctx, embed=embed, ephemeral=True)

    @case.command(name="delete_archive", description="Elimina el expediente archivado de un caso")
    @app_commands.describe(case_id="Número del caso")
    @commands.has_permissions(manage_guild=True)
    async def case_delete_archive(self, ctx: commands.Context, case_id: int):
        case = await asyncio.to_thread(db.get_support_case, ctx.guild.id, case_id)
        if case is None or case["archive_channel_id"] is None or case["archive_message_id"] is None:
            await send_response(ctx, translate(ctx, "support.archive.missing"), ephemeral=True)
            return
        channel = ctx.guild.get_channel(case["archive_channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(case["archive_message_id"])
                await message.delete()
            except discord.NotFound:
                pass
        await asyncio.to_thread(db.clear_support_archive, case_id)
        await send_response(
            ctx,
            translate(ctx, "support.archive.deleted", case_id=case_id),
            ephemeral=True,
        )

    @case.command(name="privacy", description="Explica qué datos conserva el sistema de casos")
    async def case_privacy(self, ctx: commands.Context):
        await send_response(
            ctx,
            translate(ctx, "support.privacy"),
            ephemeral=True,
        )

    @tasks.loop(hours=1)
    async def cleanup_expired_archives(self):
        rows = await asyncio.to_thread(db.get_expired_support_archives, utc_now_iso())
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            channel = guild.get_channel(row["archive_channel_id"]) if guild else None
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(row["archive_message_id"])
                    await message.delete()
                except discord.NotFound:
                    pass
                except discord.HTTPException as exc:
                    log.warning("No se pudo purgar el expediente #%s: %s", row["case_id"], exc)
                    continue
            await asyncio.to_thread(db.clear_support_archive, row["case_id"])

    @cleanup_expired_archives.before_loop
    async def before_cleanup_expired_archives(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SupportCasesCog(bot))
