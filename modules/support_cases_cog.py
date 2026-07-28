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


def _render_message(record: dict[str, Any]) -> str:
    author = html.escape(record["author_display_name"])
    username = html.escape(record["author_name"])
    avatar = safe_external_url(record["author_avatar"])
    timestamp = html.escape(record["created_at"])
    edited = " · editado" if record["edited_at"] else ""
    content = html.escape(record["content"] or "").replace("\n", "<br>")
    if not content:
        content = '<span class="muted">(sin texto)</span>'

    attachment_html = ""
    if record["attachments"]:
        items = []
        for attachment in record["attachments"]:
            filename = html.escape(attachment["filename"])
            url = safe_external_url(attachment["url"])
            size = int(attachment["size"] or 0)
            items.append(
                f'<li><a href="{url}" rel="noreferrer">{filename}</a> '
                f'<span class="muted">({size:,} bytes)</span></li>'
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
        f'<footer class="muted">Message ID: {record["id"]} · User ID: {record["author_id"]}</footer>'
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
) -> tuple[bytes, str]:
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    messages = "".join(_render_message(record) for record in records)
    escaped_subject = html.escape(subject)
    escaped_reason = html.escape(close_reason)
    escaped_guild = html.escape(guild_name)
    escaped_channel = html.escape(channel_name)
    escaped_closer = html.escape(closed_by)

    document = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: http:; style-src 'unsafe-inline'">
<title>Caso #{case_id} - {escaped_subject}</title>
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
<h1>Caso #{case_id}: {escaped_subject}</h1>
<p><strong>Servidor:</strong> {escaped_guild}<br>
<strong>Canal:</strong> #{escaped_channel}<br>
<strong>Usuario inicial:</strong> {opener_id}<br>
<strong>Cerrado por:</strong> {escaped_closer}<br>
<strong>Motivo:</strong> {escaped_reason}<br>
<strong>Mensajes:</strong> {len(records)}<br>
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
            "Usa `/case open`, `/case close`, `/case list` o `/case privacy`. "
            "La configuración administrativa está en `/case setup`.",
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
            await send_response(ctx, "La retención debe estar entre 1 y 90 días.", ephemeral=True)
            return
        if support_role.is_default():
            await send_response(
                ctx,
                "El rol de soporte no puede ser `@everyone`; selecciona un rol privado del equipo.",
                ephemeral=True,
            )
            return
        if archive_channel.permissions_for(ctx.guild.default_role).view_channel:
            await send_response(
                ctx,
                "El canal de archivo debe ser privado para `@everyone`. Ocúltalo antes de activar el módulo.",
                ephemeral=True,
            )
            return
        me = ctx.guild.me
        if me is None or not archive_channel.permissions_for(me).send_messages:
            await send_response(
                ctx,
                "No puedo enviar archivos en el canal de archivo seleccionado.",
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
            f"Casos configurados en **{category.name}**. Expedientes: {archive_channel.mention}; "
            f"equipo: {support_role.mention}; retención: **{retention_days} días**.",
        )

    @case.command(name="open", description="Abre un caso privado con el equipo de soporte")
    @app_commands.describe(subject="Resumen breve del motivo del caso")
    @commands.bot_has_permissions(manage_channels=True)
    async def case_open(self, ctx: commands.Context, *, subject: str):
        settings = await self._settings(ctx.guild.id)
        if settings is None:
            await send_response(
                ctx, "Este servidor todavía no configuró el sistema de casos.", ephemeral=True
            )
            return
        subject = subject.strip()
        if not subject or len(subject) > MAX_SUBJECT_LENGTH:
            await send_response(
                ctx,
                f"El asunto debe tener entre 1 y {MAX_SUBJECT_LENGTH} caracteres.",
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
                    f"Ya tienes abierto el caso #{existing['case_id']}: {channel.mention}",
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
                "La categoría o el rol configurado ya no existe. Un administrador debe ejecutar `/case setup`.",
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
                "Ya existe otro caso abierto para tu usuario. Usa `/case list` o contacta al equipo.",
                ephemeral=True,
            )
            return
        except Exception:
            await channel.delete(reason="Rollback: support case could not be persisted")
            raise

        await channel.edit(name=f"case-{case_id}-{safe_channel_slug(ctx.author.display_name)}")
        embed = discord.Embed(
            title=f"Caso #{case_id}: {subject}",
            description=(
                f"{ctx.author.mention}, describe aquí lo ocurrido. El equipo {support_role.mention} "
                "puede responder directamente en este canal.\n\n"
                "Al cerrar el caso, Copy generará un expediente completo del historial y lo enviará "
                "al archivo privado configurado."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Usa /case close dentro de este canal para cerrarlo.")
        await channel.send(
            content=f"{ctx.author.mention} {support_role.mention}",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False),
        )
        await send_response(ctx, f"Caso #{case_id} creado: {channel.mention}", ephemeral=True)

    @case.command(name="close", description="Cierra el caso actual y genera su expediente completo")
    @app_commands.describe(reason="Motivo o resolución del cierre")
    @commands.bot_has_permissions(manage_channels=True)
    async def case_close(self, ctx: commands.Context, *, reason: str = "Caso resuelto"):
        case = await asyncio.to_thread(db.get_support_case_by_channel, ctx.channel.id)
        if case is None or case["guild_id"] != ctx.guild.id:
            await send_response(ctx, "Este canal no es un caso administrado por Copy.", ephemeral=True)
            return
        if case["status"] != "open":
            await send_response(ctx, "Este caso ya está cerrado.", ephemeral=True)
            return
        settings = await self._settings(ctx.guild.id)
        if settings is None:
            await send_response(ctx, "La configuración del módulo fue eliminada.", ephemeral=True)
            return
        member = ctx.author
        if member.id != case["opener_id"] and not self._is_support(member, settings):
            await send_response(
                ctx, "Solo quien abrió el caso o el equipo de soporte puede cerrarlo.", ephemeral=True
            )
            return
        reason = reason.strip()[:300] or "Caso resuelto"
        if ctx.channel.id in self._closing_channels:
            await send_response(ctx, "El cierre de este caso ya está en proceso.", ephemeral=True)
            return

        archive_channel = ctx.guild.get_channel(settings["archive_channel_id"])
        if not isinstance(archive_channel, discord.TextChannel):
            await send_response(
                ctx,
                "El canal de archivo ya no existe. Un administrador debe ejecutar `/case setup`.",
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
            )
            if len(messages) > MAX_TRANSCRIPT_MESSAGES:
                await send_response(
                    ctx,
                    f"El caso supera el límite operativo de {MAX_TRANSCRIPT_MESSAGES:,} mensajes. "
                    "Contacta al propietario del bot antes de cerrarlo.",
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
                    "El expediente comprimido supera el límite de archivos de este servidor. "
                    "Contacta al propietario del bot antes de cerrar este caso.",
                    ephemeral=True,
                )
                return
            transcript_payload, transcript_filename = packaged

            archive_embed = discord.Embed(
                title=f"Expediente de soporte #{case['case_id']}",
                description=f"**{case['subject']}**\nMotivo de cierre: {reason}",
                color=0x57F287,
                timestamp=datetime.now(UTC),
            )
            archive_embed.add_field(name="Canal", value=f"`{ctx.channel.name}` · `{ctx.channel.id}`")
            archive_embed.add_field(name="Mensajes", value=str(len(records)))
            archive_embed.add_field(name="SHA-256", value=f"`{digest}`", inline=False)
            archive_embed.set_footer(
                text=f"Retención configurada: {settings['retention_days']} días · No contiene adjuntos binarios"
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
                    ctx, "El caso fue cerrado simultáneamente por otra persona.", ephemeral=True
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
                f"Caso #{case['case_id']} cerrado. Se archivaron **{len(records)} mensajes** "
                "y el canal quedó en modo de solo lectura.",
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
            await send_response(ctx, "El estado debe ser `open` o `closed`.", ephemeral=True)
            return
        rows = await asyncio.to_thread(db.get_support_cases_for_guild, ctx.guild.id, status)
        if not rows:
            await send_response(ctx, f"No hay casos con estado `{status}`.", ephemeral=True)
            return
        lines = []
        for row in rows[:20]:
            channel = ctx.guild.get_channel(row["channel_id"])
            target = channel.mention if channel else f"`{row['channel_id']}`"
            lines.append(
                f"**#{row['case_id']}** · {target} · {discord.utils.escape_markdown(row['subject'])}"
            )
        embed = discord.Embed(
            title=f"Casos {status}",
            description="\n".join(lines),
            color=0x5865F2,
        )
        if len(rows) > 20:
            embed.set_footer(text=f"Mostrando 20 de {len(rows)} casos.")
        await send_response(ctx, embed=embed, ephemeral=True)

    @case.command(name="delete_archive", description="Elimina el expediente archivado de un caso")
    @app_commands.describe(case_id="Número del caso")
    @commands.has_permissions(manage_guild=True)
    async def case_delete_archive(self, ctx: commands.Context, case_id: int):
        case = await asyncio.to_thread(db.get_support_case, ctx.guild.id, case_id)
        if case is None or case["archive_channel_id"] is None or case["archive_message_id"] is None:
            await send_response(ctx, "Ese caso no tiene un expediente archivado.", ephemeral=True)
            return
        channel = ctx.guild.get_channel(case["archive_channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(case["archive_message_id"])
                await message.delete()
            except discord.NotFound:
                pass
        await asyncio.to_thread(db.clear_support_archive, case_id)
        await send_response(ctx, f"Expediente del caso #{case_id} eliminado.", ephemeral=True)

    @case.command(name="privacy", description="Explica qué datos conserva el sistema de casos")
    async def case_privacy(self, ctx: commands.Context):
        await send_response(
            ctx,
            "Copy procesa el historial del canal únicamente al cerrar el caso. "
            "No guarda mensajes ni adjuntos en su base de datos: conserva IDs y metadatos del caso. "
            "El HTML se publica en el canal privado configurado y se elimina según la retención del servidor. "
            "Los adjuntos se registran como nombre, tamaño y enlace; no se copian sus archivos.",
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
