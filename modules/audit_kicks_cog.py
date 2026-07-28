# modules/audit_kicks_cog.py

import discord
from discord.ext import commands

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
                    "❌ Este comando por DM sólo está permitido para el **owner del bot**.",
                    mention_author=False,
                )

            # Necesita guild_id explícito
            if arg1 is None:
                return await ctx.reply("ℹ️ En DM usa: `c!kicks <guild_id> [limite]`", mention_author=False)

            guild_id = parse_int(arg1)
            if guild_id is None:
                return await ctx.reply(
                    "❌ `guild_id` inválido. Ej: `c!kicks 123456789012345678 10`", mention_author=False
                )

            # Límite
            limit = 5
            if arg2 is not None:
                lim = parse_int(arg2)
                if lim is None or lim <= 0:
                    return await ctx.reply(
                        "❌ Límite inválido. Usa un número entero positivo.", mention_author=False
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
                    "❌ No puedo acceder a ese servidor (¿el bot está dentro?).", mention_author=False
                )

        else:
            # En servidor: arg1 opcional = límite
            guild = ctx.guild
            if not isinstance(ctx.author, discord.Member):
                return await ctx.reply(
                    "❌ No pude verificar tus permisos en este servidor.",
                    mention_author=False,
                )
            requester_permissions = ctx.author.guild_permissions
            if not (
                requester_permissions.administrator
                or requester_permissions.manage_guild
                or requester_permissions.view_audit_log
            ):
                return await ctx.reply(
                    "❌ Necesitas **Ver registro de auditoría** o **Gestionar servidor** para usar este comando.",
                    mention_author=False,
                )

            limit = 5
            if arg1 is not None:
                lim = parse_int(arg1)
                if lim is None or lim <= 0:
                    return await ctx.reply(
                        "❌ Límite inválido. Usa un número entero positivo.", mention_author=False
                    )
                limit = min(lim, MAX_LIMIT)

        # --- Verificar permisos del BOT en ese guild ---
        me = guild.me or guild.get_member(self.bot.user.id)
        if not me:
            return await ctx.reply("❌ No pude verificar mis permisos en ese servidor.", mention_author=False)

        if not me.guild_permissions.view_audit_log:
            return await ctx.reply(
                "❌ No tengo permiso **Ver registro de auditoría** en ese servidor.", mention_author=False
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
                    f"{getattr(target, 'name', 'Desconocido')}#{getattr(target, 'discriminator', '0000')}"
                    if hasattr(target, "discriminator")
                    else f"{getattr(target, 'name', 'Desconocido')}"
                )
                mod_name = (
                    f"{getattr(moderator, 'name', 'Desconocido')}#{getattr(moderator, 'discriminator', '0000')}"
                    if hasattr(moderator, "discriminator")
                    else f"{getattr(moderator, 'name', 'Desconocido')}"
                )
                when = entry.created_at  # UTC datetime
                ts = int(when.timestamp()) if when else None

                line = (
                    f"👢 **Expulsado:** {target_name} (ID: {getattr(target, 'id', '¿?')})\n"
                    f"🔨 **Moderador:** {mod_name} (ID: {getattr(moderator, 'id', '¿?')})"
                )
                if ts:
                    line += f"\n🕒 **Fecha:** <t:{ts}:F> • <t:{ts}:R>"
                if entry.reason:
                    line += f"\n📝 **Razón:** {entry.reason}"
                items.append(line)
        except discord.Forbidden:
            return await ctx.reply("❌ Acceso denegado al registro de auditoría.", mention_author=False)
        except discord.HTTPException:
            return await ctx.reply(
                "⚠️ Error al leer el registro de auditoría. Intenta de nuevo.", mention_author=False
            )

        if not items:
            return await ctx.reply("ℹ️ No hay expulsiones registradas (o no recientes).", mention_author=False)

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
                title=f"Registro de expulsiones (kick) — {guild.name}", description=chunk, color=0x5865F2
            )
            embed.set_footer(text=f"Página {i}/{len(chunks)} • Límite solicitado: {limit}")
            await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditKicksCog(bot))
