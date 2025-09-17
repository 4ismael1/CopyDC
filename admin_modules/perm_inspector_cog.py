# modules/perm_inspector_cog.py
import discord
from discord.ext import commands
from typing import Dict, List, Optional, Tuple

# ========== Definición de permisos de moderación/gestión ==========
# Nota: cubrimos la mayoría de flags relevantes de discord.py. Algunos
# nombres varían entre versiones (ej. manage_emojis vs manage_emojis_and_stickers).
# Por eso usamos "sinónimos" y getattr con fallback seguro.

# Nombre legible en español
NICE: Dict[str, str] = {
    "administrator": "Administrador",
    "manage_guild": "Gestionar Servidor",
    "manage_channels": "Gestionar Canales",
    "manage_roles": "Gestionar Roles",
    "manage_webhooks": "Gestionar Webhooks",
    "manage_emojis": "Gestionar Emojis",
    "manage_emojis_and_stickers": "Gestionar Emojis/Stickers",
    "manage_events": "Gestionar Eventos",
    "manage_threads": "Gestionar Hilos",
    "manage_nicknames": "Gestionar Apodos",
    "view_audit_log": "Ver Registro de Auditoría",
    "view_guild_insights": "Ver Estadísticas del Servidor",
    "manage_messages": "Gestionar Mensajes",
    "moderate_members": "Moderar Miembros (Timeout)",
    "kick_members": "Expulsar Miembros",
    "ban_members": "Banear Miembros",
    "move_members": "Mover Miembros (voz)",
    "mute_members": "Silenciar Miembros (voz)",
    "deafen_members": "Ensordecer Miembros (voz)",
}

# Sinónimos/variantes entre versiones de discord.py
SYNONYMS: Dict[str, List[str]] = {
    "manage_emojis_and_stickers": ["manage_emojis", "manage_expressions"],
    # "use_application_commands": ["use_slash_commands"],  # no lo usamos aquí
}

# Cualquier "permiso de gestión" o acción moderadora que normalmente hace aparecer
# la UI/menú de moderación al interactuar con miembros o con el servidor.
MGMT_OR_MOD_KEYS = {
    "administrator",
    "manage_guild",
    "manage_channels",
    "manage_roles",
    "manage_webhooks",
    "manage_emojis_and_stickers",
    "manage_emojis",
    "manage_events",
    "manage_threads",
    "manage_nicknames",
    "view_audit_log",
    "manage_messages",
    "moderate_members",
    "kick_members",
    "ban_members",
    "move_members",
    "mute_members",
    "deafen_members",
}

# Para marcar "¿abre vista de moderación?" consideramos cualquier permiso anterior.
MOD_VIEW_KEYS = set(MGMT_OR_MOD_KEYS)

def tick(ok: bool) -> str:
    return "✅" if ok else "❌"

def has_flag(perms: discord.Permissions, key: str) -> bool:
    """Comprueba un flag con tolerancia a nombres alternos entre versiones."""
    if hasattr(perms, key):
        return bool(getattr(perms, key))
    # Probar sinónimos si existen
    for alt in SYNONYMS.get(key, []):
        if hasattr(perms, alt):
            return bool(getattr(perms, alt))
    return False

def sort_roles(roles: List[discord.Role]) -> List[discord.Role]:
    return sorted(roles, key=lambda r: r.position, reverse=True)

def chunk(lines: List[str], size: int = 10) -> List[List[str]]:
    return [lines[i:i + size] for i in range(0, len(lines), size)]

class PermissionsInspectorCog(commands.Cog):
    """
    Auditor de permisos de moderación/gestión.
    Comandos:
      - c!modcheck @usuario [#canal]        -> Efectivo en canal o actual
      - c!modcheckall @usuario              -> Auditoría general (servidor completo)
      - c!why_modview @usuario              -> Por qué abre la vista de moderador
      - c!roleperms @rol                    -> Qué permisos de gestión tiene un rol
      - c!auditroles                        -> Roles con permisos de gestión y miembros
      - c!whocan <permiso> [#canal]         -> Quién tiene un permiso en canal/servidor
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========== Utilidades ==========

    def _guild_base_flags(self, member: discord.Member) -> Dict[str, bool]:
        gp = member.guild_permissions
        return {k: has_flag(gp, k) for k in MGMT_OR_MOD_KEYS}

    def _roles_granting(self, member: discord.Member) -> Dict[str, List[discord.Role]]:
        out: Dict[str, List[discord.Role]] = {k: [] for k in MGMT_OR_MOD_KEYS}
        for role in member.roles:
            rp = role.permissions or discord.Permissions.none()
            for k in MGMT_OR_MOD_KEYS:
                if has_flag(rp, k):
                    out[k].append(role)
        return out

    def _iter_visible_channels(self, guild: discord.Guild, member: discord.Member) -> List[discord.abc.GuildChannel]:
        chans: List[discord.abc.GuildChannel] = []
        chans.extend(guild.text_channels)
        chans.extend(guild.voice_channels)
        chans.extend(guild.stage_channels)
        forum_chs = getattr(guild, "forum_channels", [])
        if forum_chs:
            chans.extend(forum_chs)
        chans.extend(guild.categories)
        # Solo los que el miembro puede ver
        visible = []
        for ch in chans:
            try:
                if getattr(ch.permissions_for(member), "view_channel", False):
                    visible.append(ch)
            except Exception:
                pass
        return visible

    def _scan_member_serverwide(
        self, member: discord.Member
    ) -> Tuple[Dict[str, bool], Dict[str, Tuple[int, int]], List[discord.abc.GuildChannel], List[str]]:
        """
        Escanea todo el servidor para el miembro:
          - base_flags: flags base a nivel servidor (por roles)
          - per_perm_counts: {perm: (canales donde True, total_canales_visibles)}
          - modview_channels: lista de canales donde se cumpliría "vista de moderación"
          - reasons: lista de permisos que por sí solos ya justifican vista de moderación
        """
        base_flags = self._guild_base_flags(member)
        visible = self._iter_visible_channels(member.guild, member)
        total = len(visible)
        counts = {k: (0, total) for k in MGMT_OR_MOD_KEYS}
        modview_channels: List[discord.abc.GuildChannel] = []

        for ch in visible:
            perms = ch.permissions_for(member)
            show = False
            for k in MGMT_OR_MOD_KEYS:
                if has_flag(perms, k):
                    y, t = counts[k]
                    counts[k] = (y + 1, t)
                    if k in MOD_VIEW_KEYS:
                        show = True
            if show:
                modview_channels.append(ch)

        # Razones (a nivel base del servidor) que suelen exponer paneles concretos
        # según documentación oficial (ej. Moderation/Overview requieren Manage Server;
        # Audit Log requiere View Audit Log; Integrations requiere Manage Webhooks).
        reasons = []
        for k in ["administrator", "manage_guild", "view_audit_log", "manage_webhooks",
                  "manage_roles", "manage_channels", "manage_messages",
                  "moderate_members", "kick_members", "ban_members", "manage_nicknames"]:
            if base_flags.get(k):
                reasons.append(k)

        return base_flags, counts, modview_channels, reasons

    # ========== Comandos ==========

    @commands.command(name="modcheck")
    @commands.guild_only()
    async def modcheck(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        channel: Optional[discord.abc.GuildChannel] = None
    ):
        """c!modcheck @usuario [#canal] — Permisos efectivos en canal/actual."""
        member = member or ctx.author
        if channel is None and isinstance(
            ctx.channel,
            (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel, discord.CategoryChannel),
        ):
            channel = ctx.channel

        perms = channel.permissions_for(member) if channel else member.guild_permissions
        effective = {k: has_flag(perms, k) for k in MGMT_OR_MOD_KEYS}
        can_open = any(effective[k] for k in MOD_VIEW_KEYS)

        ordered = sorted(NICE.keys(), key=lambda k: (0 if effective.get(k, False) else 1, NICE[k]))
        resumen = [f"{tick(effective.get(k, False))} **{NICE[k]}**" for k in ordered if k in MGMT_OR_MOD_KEYS]

        emb = discord.Embed(
            title=f"Permisos de Moderación (canal) — {member.display_name}",
            color=discord.Color.green() if can_open else discord.Color.red(),
            description="\n".join(resumen) or "—",
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        if channel:
            emb.add_field(name="Canal", value=channel.mention, inline=True)
        emb.add_field(name="Usuario", value=member.mention, inline=True)
        emb.add_field(name="¿Vista de moderación aquí?", value="**Sí**" if can_open else "**No**", inline=False)
        emb.set_footer(text="Incluye permisos de gestión (manage_*) y moderación de miembros.")
        await ctx.reply(member.mention, embed=emb, mention_author=False)

    @commands.command(name="modcheckall")
    @commands.guild_only()
    async def modcheckall(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """c!modcheckall @usuario — Auditoría general en TODO el servidor."""
        member = member or ctx.author

        base_flags, counts, modview_channels, reasons = self._scan_member_serverwide(member)
        total_visible = next(iter(counts.values()))[1] if counts else 0
        can_open_somewhere = len(modview_channels) > 0

        base_lines = []
        for k in sorted(MGMT_OR_MOD_KEYS):
            base_lines.append(f"{tick(base_flags.get(k, False))} **{NICE.get(k, k)}**")

        cov_lines = []
        for k in sorted(MGMT_OR_MOD_KEYS):
            y, t = counts[k]
            cov_lines.append(f"**{NICE.get(k, k)}:** {y}/{t}")

        sample = ", ".join(ch.mention for ch in modview_channels[:15]) if modview_channels else "(Ninguno)"
        more = f"\n…y otros {max(0, len(modview_channels)-15)} canales." if len(modview_channels) > 15 else ""

        # Razones legibles
        why_lines = [f"• {NICE.get(k, k)}" for k in reasons] or ["(Ninguna)"]

        emb = discord.Embed(
            title=f"Auditoría de Moderación — {member.display_name}",
            color=discord.Color.green() if can_open_somewhere else discord.Color.red()
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.add_field(
            name="¿Abre vista de moderación en el servidor?",
            value=("**Sí**" if can_open_somewhere else "**No**") + f" — ({len(modview_channels)}/{total_visible} canales visibles)",
            inline=False
        )
        emb.add_field(name="Permisos base (roles)", value="\n".join(base_lines), inline=False)
        emb.add_field(name="Cobertura por canal", value="\n".join(cov_lines), inline=False)
        emb.add_field(name="Motivos (permisos que lo habilitan)", value="\n".join(why_lines), inline=False)
        emb.add_field(name="Canales donde aparece (muestra)", value=sample + more, inline=False)
        emb.add_field(name="Usuario", value=member.mention, inline=True)
        emb.add_field(name="Servidor", value=ctx.guild.name, inline=True)
        emb.set_footer(text="Solo se cuentan canales visibles para el usuario.")
        await ctx.reply(member.mention, embed=emb, mention_author=False)

    @commands.command(name="why_modview")
    @commands.guild_only()
    async def why_modview(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """c!why_modview @usuario — Explica exactamente qué permisos/roles abren la vista de moderación."""
        member = member or ctx.author
        base_flags = self._guild_base_flags(member)
        roles_map = self._roles_granting(member)

        reasons = [k for k in MOD_VIEW_KEYS if base_flags.get(k)]
        if not reasons:
            # Puede que no tenga flags base pero sí en ciertos canales; referir al modcheckall
            emb = discord.Embed(
                title=f"¿Por qué vería la vista de moderación? — {member.display_name}",
                description="No se hallaron permisos base que la habiliten globalmente. Prueba `c!modcheckall @usuario` para ver cobertura por canal.",
                color=discord.Color.orange()
            )
            return await ctx.reply(member.mention, embed=emb, mention_author=False)

        lines = []
        for k in reasons:
            role_mentions = [r.mention for r in sort_roles(roles_map.get(k, []))]
            roles_text = ", ".join(role_mentions) if role_mentions else "(concedido indirectamente)"
            lines.append(f"**{NICE.get(k, k)}** → {roles_text}")

        emb = discord.Embed(
            title=f"Motivos — {member.display_name}",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )
        emb.set_thumbnail(url=member.display_avatar.url)
        emb.set_footer(text="Incluye permisos de gestión como Gestionar Apodos, Roles, Canales, Mensajes, etc.")
        await ctx.reply(member.mention, embed=emb, mention_author=False)

    @commands.command(name="roleperms")
    @commands.guild_only()
    async def roleperms(self, ctx: commands.Context, role: discord.Role):
        """c!roleperms @rol — Qué permisos de gestión/moderación tiene un rol (global)."""
        rp = role.permissions or discord.Permissions.none()
        lines = []
        for k in sorted(MGMT_OR_MOD_KEYS):
            lines.append(f"{tick(has_flag(rp, k))} **{NICE.get(k, k)}**")
        emb = discord.Embed(
            title=f"Permisos de rol — {role.name}",
            description="\n".join(lines) or "—",
            color=discord.Color.teal()
        )
        emb.add_field(name="Rol", value=role.mention, inline=True)
        await ctx.reply(embed=emb, mention_author=False)

    @commands.command(name="auditroles")
    @commands.guild_only()
    async def auditroles(self, ctx: commands.Context):
        """c!auditroles — Lista roles con permisos de gestión y cuántos miembros los tienen."""
        rows: List[str] = []
        for role in sort_roles(ctx.guild.roles):
            if role.is_default():
                continue
            rp = role.permissions or discord.Permissions.none()
            grants = [NICE.get(k, k) for k in MGMT_OR_MOD_KEYS if has_flag(rp, k)]
            if grants:
                count = sum(1 for m in ctx.guild.members if role in m.roles)
                rows.append(f"{role.mention} — {count} miembros\n• " + ", ".join(grants))
        if not rows:
            rows = ["(Ningún rol con permisos de gestión)"]

        emb = discord.Embed(
            title="Auditoría de roles con permisos de gestión",
            description="\n\n".join(rows)[:3900],  # margen de seguridad
            color=discord.Color.dark_gold()
        )
        await ctx.reply(embed=emb, mention_author=False)

    @commands.command(name="whocan")
    @commands.guild_only()
    async def whocan(
        self,
        ctx: commands.Context,
        perm_key: str,
        channel: Optional[discord.abc.GuildChannel] = None
    ):
        """c!whocan <permiso> [#canal] — Quién tiene ese permiso en canal/servidor."""
        perm_key = perm_key.strip().lower()
        valid = sorted(MGMT_OR_MOD_KEYS)
        if perm_key not in valid:
            return await ctx.reply(
                f"Permiso no válido. Usa uno de: `{', '.join(valid)}`.",
                mention_author=False
            )
        if channel is None and isinstance(
            ctx.channel,
            (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel, discord.CategoryChannel),
        ):
            channel = ctx.channel

        holders: List[str] = []
        for m in ctx.guild.members:
            perms = channel.permissions_for(m) if channel else m.guild_permissions
            if has_flag(perms, perm_key):
                holders.append(m.mention)

        desc = (
            f"Miembros con **{NICE.get(perm_key, perm_key)}** "
            f"en {channel.mention if channel else 'el servidor'}:\n"
            + (", ".join(holders[:900]) if holders else "Nadie.")
        )
        emb = discord.Embed(
            title=f"Quién puede — {NICE.get(perm_key, perm_key)}",
            description=desc,
            color=discord.Color.orange()
        )
        await ctx.reply(embed=emb, mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(PermissionsInspectorCog(bot))
