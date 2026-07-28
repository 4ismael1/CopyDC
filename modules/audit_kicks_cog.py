# modules/audit_kicks_cog.py

import discord
from discord.ext import commands

from localization import translate

MAX_LIMIT = 25


def parse_int(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


class AuditKicksCog(commands.Cog):
    """
    Consulta expulsiones (kicks) desde los registros de auditoría.
    - En un servidor: c!kicks [limite]
    - Por DM (MD):    c!kicks <guild_id> [limite]
    Requisitos: Permiso 'View Audit Log' para el bot en ese servidor.
    Seguridad: En DM sólo permite al OWNER_ID (owner del bot).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="kicks")
    async def kicks(self, ctx: commands.Context, arg1: str | None = None, arg2: str | None = None):
        """
        Lista expulsiones recientes (AuditLogAction.kick) con usuario e ID.
        Uso:
          - En servidor: c!kicks            -> últimos 5
                          c!kicks 10        -> últimos 10 (máx 25)
          - Por DM:      c!kicks <guild_id> [limite]
                          ej: c!kicks 1192645155040272414 15
        """
        # --- Resolver contexto (DM vs Servidor) ---
        if ctx.guild is None:
            # En DM sólo el owner del bot puede usarlo (auditoría es sensible)
            if ctx.author.id != (self.bot.owner_id or 0):
                return await ctx.reply(
                    translate(ctx, "audit.dm_owner_only"),
                    mention_author=False,
                )

            # Necesita guild_id explícito
            if arg1 is None:
                return await ctx.reply(translate(ctx, "audit.dm_usage"), mention_author=False)

            guild_id = parse_int(arg1)
            if guild_id is None:
                return await ctx.reply(
                    translate(ctx, "audit.guild_id_invalid"),
                    mention_author=False,
                )

            # Límite
            limit = 5
            if arg2 is not None:
                lim = parse_int(arg2)
                if lim is None or lim <= 0:
                    return await ctx.reply(
                        translate(ctx, "audit.limit_invalid"),
                        mention_author=False,
                    )
                limit = min(lim, MAX_LIMIT)

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                # Intento de fetch si no está en caché
                try:
                    guild = await self.bot.fetch_guild(guild_id)
                except discord.HTTPException:
                    guild = None

            if guild is None:
                return await ctx.reply(
                    translate(ctx, "audit.guild_unavailable"),
                    mention_author=False,
                )

        else:
            # En servidor: arg1 opcional = límite
            guild = ctx.guild
            if not isinstance(ctx.author, discord.Member):
                return await ctx.reply(
                    translate(ctx, "audit.permissions_unresolved"),
                    mention_author=False,
                )
            requester_permissions = ctx.author.guild_permissions
            if not (
                requester_permissions.administrator
                or requester_permissions.manage_guild
                or requester_permissions.view_audit_log
            ):
                return await ctx.reply(
                    translate(ctx, "audit.permission_required"),
                    mention_author=False,
                )

            limit = 5
            if arg1 is not None:
                lim = parse_int(arg1)
                if lim is None or lim <= 0:
                    return await ctx.reply(
                        translate(ctx, "audit.limit_invalid"),
                        mention_author=False,
                    )
                limit = min(lim, MAX_LIMIT)

        # --- Verificar permisos del BOT en ese guild ---
        me = guild.me or guild.get_member(self.bot.user.id)
        if not me:
            return await ctx.reply(
                translate(ctx, "audit.bot_permissions_unresolved"),
                mention_author=False,
            )

        if not me.guild_permissions.view_audit_log:
            return await ctx.reply(
                translate(ctx, "audit.bot_permission_missing"),
                mention_author=False,
            )

        # --- Leer auditoría ---
        items = []
        try:
            async for entry in guild.audit_logs(limit=limit, action=discord.AuditLogAction.kick):
                # entry.target: usuario expulsado (discord.User/Member)
                # entry.user: moderador que hizo la acción
                target = entry.target
                moderator = entry.user
                target_name = (
                    f"{getattr(target, 'name', translate(ctx, 'audit.unknown'))}#{getattr(target, 'discriminator', '0000')}"
                    if hasattr(target, "discriminator")
                    else f"{getattr(target, 'name', translate(ctx, 'audit.unknown'))}"
                )
                mod_name = (
                    f"{getattr(moderator, 'name', translate(ctx, 'audit.unknown'))}#{getattr(moderator, 'discriminator', '0000')}"
                    if hasattr(moderator, "discriminator")
                    else f"{getattr(moderator, 'name', translate(ctx, 'audit.unknown'))}"
                )
                when = entry.created_at  # UTC datetime
                ts = int(when.timestamp()) if when else None

                line = (
                    f"👢 **{translate(ctx, 'audit.target')}:** {target_name} "
                    f"(ID: {getattr(target, 'id', '?')})\n"
                    f"🔨 **{translate(ctx, 'audit.moderator')}:** {mod_name} "
                    f"(ID: {getattr(moderator, 'id', '?')})"
                )
                if ts:
                    line += f"\n🕒 **{translate(ctx, 'audit.date')}:** <t:{ts}:F> • <t:{ts}:R>"
                if entry.reason:
                    line += f"\n📝 **{translate(ctx, 'audit.reason')}:** {entry.reason}"
                items.append(line)
        except discord.Forbidden:
            return await ctx.reply(translate(ctx, "audit.access_denied"), mention_author=False)
        except discord.HTTPException:
            return await ctx.reply(
                translate(ctx, "audit.fetch_error"),
                mention_author=False,
            )

        if not items:
            return await ctx.reply(translate(ctx, "audit.none"), mention_author=False)

        # --- Construir Embed paginado sencillo (si es muy largo, lo dividimos en bloques) ---
        # Discord limita ~4096 chars en descripción. Partimos si hace falta.
        full_text = "\n\n".join(items)
        chunks = []
        while full_text:
            chunk = full_text[:3800]
            # Cortar en el último doble salto para no partir una entrada
            last_split = chunk.rfind("\n\n")
            if 1200 < last_split < len(chunk):
                chunk = chunk[:last_split]
            chunks.append(chunk)
            full_text = full_text[len(chunk) :].lstrip()

        for i, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=translate(ctx, "audit.title", guild=guild.name),
                description=chunk,
                color=0x5865F2,
            )
            embed.set_footer(
                text=translate(
                    ctx,
                    "audit.footer",
                    page=i,
                    pages=len(chunks),
                    limit=limit,
                )
            )
            await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditKicksCog(bot))
