# modules/info_cog.py
import discord
from discord.ext import commands
import datetime
from collections import defaultdict, Counter
from typing import Union, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Emojis para insignias (public_flags)
# ─────────────────────────────────────────────────────────────────────────────
BADGE_EMOJIS = {
    "staff": "<:discord_staff:1148813386634579998>",
    "partner": "<:partner:1148813426720444527>",
    "hypesquad": "<:hypesquad_events:1148813410522042459>",
    "bug_hunter": "<:bug_hunter:1148813394413158480>",
    "hypesquad_bravery": "<:bravery:1148813401769152602>",
    "hypesquad_brilliance": "<:brilliance:1148813404550000670>",
    "hypesquad_balance": "<:balance:1148813400192086036>",
    "early_supporter": "<:early_supporter:1148813406324101180>",
    "bug_hunter_level_2": "<:bug_hunter_level_2:1148813396862627911>",
    "verified_bot": "<:verified_bot:1148813390080454746>",
    "verified_developer": "<:verified_developer:1148813391745638511>",
    "certified_moderator": "<:certified_moderator:1148813398343045140>",
    "bot_http_interactions": "🌐",
    "active_developer": "<:active_developer:1148813428452671559>",
}

# Permisos clave “sensibles” para mostrar en roleinfo
KEY_PERMS = {
    "Administrador": "administrator",
    "Gestionar Servidor": "manage_guild",
    "Gestionar Canales": "manage_channels",
    "Gestionar Roles": "manage_roles",
    "Gestionar Mensajes": "manage_messages",
    "Expulsar Miembros": "kick_members",
    "Banear Miembros": "ban_members",
    "Mencionar @everyone": "mention_everyone",
    "Registro de Auditoría": "view_audit_log",
}


class InfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> Counter({user_id: total_boosts_detectados})
        self._boost_history: dict[int, Counter[int]] = defaultdict(Counter)

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _format_badges(public_flags: discord.PublicUserFlags) -> Optional[str]:
        if not public_flags:
            return None
        out = []
        for flag, emoji in BADGE_EMOJIS.items():
            if getattr(public_flags, flag, False):
                out.append(emoji)
        return " ".join(out) if out else None

    @staticmethod
    def _truncate_list(items: list[str], visible: int = 5) -> str:
        if not items:
            return "—"
        if len(items) <= visible:
            return " ".join(items)
        return f"{' '.join(items[:visible])} y **{len(items) - visible}** más…"

    async def _resolve_target(
        self,
        ctx: commands.Context,
        target: Union[discord.Member, discord.User, int, None]
    ) -> tuple[discord.User, Optional[discord.Member]]:
        """
        Devuelve (user_profile, member_si_aplica).
        • En MD devolvemos siempre User (nunca Member).
        • En servidor intentamos Member; si no, cae a User.
        """
        # Sin argumento → autor
        if target is None:
            if ctx.guild:
                member = ctx.author if isinstance(ctx.author, discord.Member) else None
                user = member or ctx.author
                return (await self.bot.fetch_user(user.id), member if ctx.guild else None)
            else:
                return (await self.bot.fetch_user(ctx.author.id), None)

        # ID crudo
        if isinstance(target, int):
            try:
                user_obj = await self.bot.fetch_user(target)
            except discord.NotFound:
                raise commands.BadArgument("No encontré a ese usuario.")
            if ctx.guild:
                member = ctx.guild.get_member(target) or await self._try_fetch_member(ctx.guild, target)
                return (user_obj, member)
            return (user_obj, None)

        # User/Member
        if isinstance(target, discord.Member):
            # Si estamos en MD, degradamos a User (sin datos del servidor)
            if ctx.guild is None:
                return (await self.bot.fetch_user(target.id), None)
            return (await self.bot.fetch_user(target.id), target)
        else:
            # discord.User
            user_obj = await self.bot.fetch_user(target.id)
            if ctx.guild:
                member = ctx.guild.get_member(target.id) or await self._try_fetch_member(ctx.guild, target.id)
                return (user_obj, member)
            return (user_obj, None)

    @staticmethod
    async def _try_fetch_member(guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return None

    # ──────────────────────────────────────────────────────────────────────
    # EVENTO: trackear inicios de boost para histórico simple (memoria volátil)
    # ──────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            self._boost_history[after.guild.id][after.id] += 1

    # ──────────────────────────────────────────────────────────────────────
    # c!user / c!userinfo / c!ui  → MD: solo público | Servidor: todo
    # ──────────────────────────────────────────────────────────────────────
    @commands.command(name="user", aliases=["userinfo", "ui"])
    async def user_info(self, ctx: commands.Context, *, member: Union[discord.Member, discord.User, int, None] = None):
        """
        • En MD: solo datos públicos (sin roles, join, actividades, etc.)
        • En servidor: datos completos del miembro si existe en el guild.
        """
        user_profile, guild_member = await self._resolve_target(ctx, member)

        # Color consistente
        base_color = getattr(user_profile, "accent_color", None)
        if not base_color and guild_member:
            base_color = guild_member.color

        embed = discord.Embed(
            color=base_color or discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow()
        )

        display_name = guild_member.display_name if guild_member else user_profile.name
        mention_or_name = str(guild_member) if guild_member else str(user_profile)

        embed.set_author(
            name=f"{mention_or_name} ({display_name})",
            icon_url=user_profile.display_avatar.url
        )
        embed.set_thumbnail(url=user_profile.display_avatar.with_size(256).url)
        embed.set_footer(text=f"ID: {user_profile.id}")

        # Banner si tiene
        if user_profile.banner:
            embed.set_image(url=user_profile.banner.url)

        # Siempre: creación de cuenta
        created_at = getattr(user_profile, "created_at", None)
        if created_at:
            embed.add_field(name="Se unió a Discord", value=f"<t:{int(created_at.timestamp())}:R>", inline=True)

        # Insignias (públicas)
        badges = self._format_badges(getattr(user_profile, "public_flags", None))
        if badges:
            embed.add_field(name="Insignias", value=badges, inline=False)

        # ── Modo MD: no hay datos del servidor ──
        if ctx.guild is None or not guild_member:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Foto de Perfil", style=discord.ButtonStyle.link, url=user_profile.display_avatar.url, emoji="🖼️"))
            if user_profile.banner:
                view.add_item(discord.ui.Button(label="Banner", style=discord.ButtonStyle.link, url=user_profile.banner.url, emoji="🌄"))
            return await ctx.reply(embed=embed, view=view, mention_author=False)

        # ── Modo Servidor: datos ampliados ──
        if guild_member.joined_at:
            embed.add_field(name="Se unió al Servidor", value=f"<t:{int(guild_member.joined_at.timestamp())}:R>", inline=True)
        else:
            embed.add_field(name="Se unió al Servidor", value="—", inline=True)

        # Separador visual
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # Roles (sin @everyone)
        roles = [r.mention for r in reversed(guild_member.roles) if not r.is_default()]
        embed.add_field(name=f"Roles [{len(roles)}]", value=self._truncate_list(roles, visible=8), inline=False)

        # Actividad/estado actual si existe
        if guild_member.activity:
            try:
                act_type = getattr(guild_member.activity.type, "name", "Activity").title()
                act_name = getattr(guild_member.activity, "name", "—")
                embed.add_field(name="Actividad Actual", value=f"**{act_type}:** {act_name}", inline=False)
            except Exception:
                pass

        # Boost actual
        if guild_member.premium_since:
            embed.add_field(name="Boosteando desde", value=f"<t:{int(guild_member.premium_since.timestamp())}:R>", inline=True)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Foto de Perfil", style=discord.ButtonStyle.link, url=guild_member.display_avatar.url, emoji="🖼️"))
        if user_profile.banner:
            view.add_item(discord.ui.Button(label="Banner", style=discord.ButtonStyle.link, url=user_profile.banner.url, emoji="🌄"))

        await ctx.reply(embed=embed, view=view, mention_author=False)

    # ──────────────────────────────────────────────────────────────────────
    # c!serverinfo  (solo en servidor)
    # ──────────────────────────────────────────────────────────────────────
    @commands.command(name="serverinfo", aliases=["server"])
    @commands.guild_only()
    async def server_info(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(
            title="Información del Servidor",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )

        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
            embed.set_thumbnail(url=guild.icon.with_size(256).url)
        else:
            embed.set_author(name=guild.name)

        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.set_footer(text=f"ID: {guild.id}")

        total_members = guild.member_count
        humans = sum(1 for m in guild.members if not m.bot)
        bots = total_members - humans
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        stage_channels = len(guild.stage_channels)
        thread_count = sum(len(c.threads) for c in guild.text_channels)

        owner_text = guild.owner.mention if guild.owner else f"ID: `{guild.owner_id}` (No encontrado)"
        embed.add_field(name="Dueño", value=owner_text, inline=True)
        embed.add_field(name="Nivel de Boost", value=f"Nivel {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)

        embed.add_field(
            name="Miembros",
            value=f"**Total:** {total_members}\n**Humanos:** {humans}\n**Bots:** {bots}",
            inline=True
        )

        embed.add_field(
            name="Canales",
            value=f"**Texto:** {text_channels}\n**Voz:** {voice_channels}\n**Stage:** {stage_channels}\n**Hilos:** {thread_count}",
            inline=True
        )

        # Extras no intrusivos
        if guild.verification_level is not None:
            embed.add_field(name="Nivel de Verificación", value=str(guild.verification_level).title(), inline=True)

        view = discord.ui.View()
        if guild.icon:
            view.add_item(discord.ui.Button(label="Icono del Servidor", style=discord.ButtonStyle.link, url=guild.icon.url, emoji="🖼️"))
        if guild.banner:
            view.add_item(discord.ui.Button(label="Banner", style=discord.ButtonStyle.link, url=guild.banner.url, emoji="🌄"))

        await ctx.reply(embed=embed, view=view, mention_author=False)

    # ──────────────────────────────────────────────────────────────────────
    # c!avatar  → funciona en MD y servidor
    # ──────────────────────────────────────────────────────────────────────
    @commands.command(name="avatar", aliases=["pfp"])
    async def avatar(self, ctx: commands.Context, *, target: Union[discord.Member, discord.User, int, None] = None):
        user_profile, member = await self._resolve_target(ctx, target)
        display_name = member.display_name if member else user_profile.name
        embed = discord.Embed(title=f"Avatar de {display_name}", color=(member.color if member and member.color.value else discord.Color.blurple()))
        avatar_url = user_profile.display_avatar.with_size(1024).url
        embed.set_image(url=avatar_url)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Abrir Avatar", style=discord.ButtonStyle.link, url=avatar_url, emoji="🖼️"))
        await ctx.reply(embed=embed, view=view, mention_author=False)

    # ──────────────────────────────────────────────────────────────────────
    # c!roleinfo  (solo en servidor)
    # ──────────────────────────────────────────────────────────────────────
    @commands.command(name="roleinfo", aliases=["role"])
    @commands.guild_only()
    async def role_info(self, ctx: commands.Context, *, role: discord.Role):
        """Muestra información detallada sobre un rol."""
        embed = discord.Embed(title="Información del Rol", color=role.color or discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
        embed.set_author(name=f"@{role.name}")
        embed.set_footer(text=f"ID del Rol: {role.id}")

        # General
        embed.add_field(name="Miembros", value=str(len(role.members)), inline=True)
        embed.add_field(name="Color (HEX)", value=str(role.color), inline=True)
        embed.add_field(name="Posición", value=str(role.position), inline=True)
        embed.add_field(name="Mencionable", value="Sí" if role.mentionable else "No", inline=True)
        embed.add_field(name="Separado", value="Sí" if role.hoist else "No", inline=True)
        if role.created_at:
            embed.add_field(name="Creado", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)

        # Permisos clave
        if role.permissions.administrator:
            perms_text = "✅ **Administrador** (tiene todos los permisos)"
        else:
            enabled = [name for name, attr in KEY_PERMS.items() if getattr(role.permissions, attr, False)]
            perms_text = ", ".join(enabled) if enabled else "Ninguno"
        embed.add_field(name="Permisos Clave", value=perms_text, inline=False)

        await ctx.reply(embed=embed, mention_author=False)

    # ──────────────────────────────────────────────────────────────────────
    # c!boost / c!1boost  (solo en servidor)
    # ──────────────────────────────────────────────────────────────────────
    @commands.command(name="boost", aliases=["1boost"])
    @commands.guild_only()
    async def boost_info(self, ctx: commands.Context, target: Union[discord.Member, discord.User, int, None] = None):
        """
        Muestra cuántas veces (históricamente) ha empezado a boostear en este servidor (en esta sesión),
        y si tiene boost activo ahora mismo.
        """
        user_profile, member = await self._resolve_target(ctx, target)
        # Si no es miembro del servidor, no podemos ver premium_since (datos del guild)
        if member is None:
            return await ctx.reply("Ese usuario no es miembro de este servidor.", mention_author=False)

        total_hist = self._boost_history[ctx.guild.id].get(member.id, 0)
        activo = member.premium_since is not None

        embed = discord.Embed(
            title="Boost del usuario",
            color=discord.Color.fuchsia(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Boost activo ahora mismo", value="Sí ✅" if activo else "No ❌", inline=True)
        embed.add_field(name="Veces detectadas empezando a boostear", value=str(total_hist), inline=True)

        if activo:
            embed.add_field(name="Boost desde", value=f"<t:{int(member.premium_since.timestamp())}:R>", inline=False)

        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))
