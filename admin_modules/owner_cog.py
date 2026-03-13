# modules/owner_cog.py
# ✔ Owner-only
# ✔ Funciona por MD o en servidores
# ✔ Lista interactiva con Select y botones ◀️ ▶️
# ✔ Ficha del servidor con pestañas (Resumen, Miembros/Canales, Roles/Emojis, Seguridad/Nitro, Permisos del bot)
# ✔ Sin invitaciones y sin jump link

import os
import math
from typing import Optional, List, Tuple

import discord
from discord.ext import commands
from discord import ui
from dotenv import load_dotenv

import database as db
from command_utils import build_presence_activity, looks_like_custom_emoji_reference, resolve_presence_status, split_custom_status_input

load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID", 0))

# ───────────────────── Utils ─────────────────────

def is_owner_check(ctx: commands.Context) -> bool:
    return ctx.author and ctx.author.id == OWNER_ID

def owner_only():
    return commands.check(is_owner_check)

def fmt_bool(b: bool) -> str:
    return "✅" if b else "❌"

def trim(text: str, max_len: int = 100) -> str:
    text = text or ""
    return (text[: max_len - 1] + "…") if len(text) > max_len else text

def resolve_guild(bot: commands.Bot, query: str) -> Optional[discord.Guild]:
    """Busca un guild por ID o por nombre (contiene, case-insensitive)."""
    if query.isdigit():
        g = bot.get_guild(int(query))
        if g:
            return g
    q = query.lower()
    matches = [g for g in bot.guilds if q in g.name.lower()]
    if not matches:
        return None
    # Prioriza coincidencia simple y nombres más cortos
    matches.sort(key=lambda g: (-len(set(g.name.lower()) & set(q)), len(g.name)))
    return matches[0]

def boost_bar(boosts: int, tier: int) -> str:
    # Aproximaciones decorativas a los tiers (no son límites exactos)
    steps = [2, 7, 14]  # Tier 1/2/3 aprox
    filled = sum(1 for s in steps if boosts >= s)
    total = len(steps)
    return "⛽ " + "█" * filled + "░" * (total - filled) + f"  (Tier {tier} • {boosts})"

# ─────────────── Embeds builders ───────────────

PRESENCE_ACTIVITY_TYPES = ("custom", "playing", "listening", "watching", "competing")
PRESENCE_STATUSES = ("online", "idle", "dnd", "invisible")


def normalize_presence_activity_type(raw: str) -> Optional[str]:
    value = (raw or "").strip().lower()
    aliases = {
        "custom": "custom",
        "status": "custom",
        "playing": "playing",
        "game": "playing",
        "listening": "listening",
        "watching": "watching",
        "watch": "watching",
        "competing": "competing",
        "competition": "competing",
    }
    return aliases.get(value)


def normalize_presence_status(raw: str) -> Optional[str]:
    value = (raw or "").strip().lower()
    aliases = {
        "online": "online",
        "idle": "idle",
        "afk": "idle",
        "dnd": "dnd",
        "busy": "dnd",
        "invisible": "invisible",
        "offline": "invisible",
    }
    return aliases.get(value)


def build_presence_embed(row: Optional[dict], *, title: str = "Estado del bot") -> discord.Embed:
    embed = discord.Embed(title=title, color=discord.Color.blurple())
    if not row:
        embed.description = "No hay ningun preset de presencia activo."
        return embed

    embed.add_field(name="Nombre", value=f"`{row['name']}`", inline=True)
    embed.add_field(name="Tipo", value=f"`{row['activity_type']}`", inline=True)
    embed.add_field(name="Estado", value=f"`{row['status']}`", inline=True)
    if row.get("activity_emoji"):
        embed.add_field(name="Emoji", value=row["activity_emoji"], inline=True)
    embed.add_field(name="Texto", value=row["activity_text"], inline=False)
    return embed


def build_overview_embed(g: discord.Guild) -> discord.Embed:
    shard = getattr(g, "shard_id", None)
    locale = getattr(g, "preferred_locale", "N/D")
    owner = getattr(g, "owner", None)
    owner_tag = f"{owner} ({owner.id})" if owner else "desconocido"

    e = discord.Embed(title=g.name, description=g.description or "", color=discord.Color.green())
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    if getattr(g, "banner", None):
        e.set_image(url=g.banner.url)

    e.add_field(name="ID", value=f"`{g.id}`", inline=True)
    e.add_field(name="Dueño", value=owner_tag, inline=True)
    e.add_field(name="Creado", value=discord.utils.format_dt(g.created_at, style="F"), inline=True)

    total = getattr(g, "member_count", None)
    humans = bots = "N/D"
    if g.members:
        humans = sum(1 for m in g.members if not m.bot)
        bots = sum(1 for m in g.members if m.bot)
    e.add_field(name="Miembros", value=f"Total: {total if total is not None else 'N/D'}\n🙂 Humanos: {humans}\n🤖 Bots: {bots}", inline=False)

    text_count = len(g.text_channels)
    voice_count = len(g.voice_channels)
    categories = len(g.categories)
    stage_count = len(getattr(g, "stage_channels", []))
    forum_cls = getattr(discord, "ForumChannel", None)
    forums = len([c for c in g.channels if forum_cls and isinstance(c, forum_cls)])
    e.add_field(
        name="Canales",
        value=f"💬 Texto: {text_count} • 🔊 Voz: {voice_count}\n🗂️ Categorías: {categories} • 🧵 Foros: {forums}\n🎙️ Stage: {stage_count}",
        inline=False,
    )

    roles_text = f"🎭 Roles: {max(0, len(g.roles)-1)} (sin @everyone)"
    e.add_field(name="Roles", value=roles_text, inline=True)

    emojis_text = f"😊 Emojis: {len(g.emojis)} • 🩹 Stickers: {len(getattr(g, 'stickers', []))}"
    e.add_field(name="Emojis/Stickers", value=emojis_text, inline=True)

    misc_text = f"🌐 Locale: {locale}\n🧩 Shard: {shard if shard is not None else '—'}\n🔗 Vanity: {getattr(g, 'vanity_url_code', None) or '—'}"
    e.add_field(name="Misc", value=misc_text, inline=True)

    return e

def build_people_channels_embed(g: discord.Guild) -> discord.Embed:
    e = discord.Embed(title=f"{g.name} — Miembros & Canales", color=discord.Color.blurple())
    total = getattr(g, "member_count", None)
    humans = bots = "N/D"
    if g.members:
        humans = sum(1 for m in g.members if not m.bot)
        bots = sum(1 for m in g.members if m.bot)
    e.add_field(name="Miembros", value=f"👥 Total: {total if total is not None else 'N/D'}\n🙂 Humanos: {humans}\n🤖 Bots: {bots}", inline=False)

    forum_cls = getattr(discord, "ForumChannel", None)
    t = [c for c in g.text_channels]
    v = [c for c in g.voice_channels]
    cat = [c for c in g.categories]
    st = list(getattr(g, "stage_channels", []))
    fo = [c for c in g.channels if forum_cls and isinstance(c, forum_cls)]
    e.add_field(name="Texto", value=str(len(t)), inline=True)
    e.add_field(name="Voz", value=str(len(v)), inline=True)
    e.add_field(name="Stage", value=str(len(st)), inline=True)
    e.add_field(name="Categorías", value=str(len(cat)), inline=True)
    e.add_field(name="Foros", value=str(len(fo)), inline=True)

    specials = []
    if g.system_channel:
        specials.append(f"📰 System: #{g.system_channel.name}")
    if g.rules_channel:
        specials.append(f"📜 Rules: #{g.rules_channel.name}")
    if g.public_updates_channel:
        specials.append(f"📣 Updates: #{g.public_updates_channel.name}")
    if g.afk_channel:
        specials.append(f"😴 AFK: #{g.afk_channel.name} ({g.afk_timeout}s)")
    e.add_field(name="Especiales", value="\n".join(specials) if specials else "—", inline=False)

    return e

def build_roles_emojis_embed(g: discord.Guild) -> discord.Embed:
    e = discord.Embed(title=f"{g.name} — Roles & Emojis", color=discord.Color.teal())
    roles: List[discord.Role] = [r for r in g.roles if not r.is_default()]
    roles.sort(key=lambda r: r.position, reverse=True)
    preview = ", ".join([discord.utils.escape_markdown(r.name) for r in roles[:10]]) if roles else "—"
    e.add_field(name="Roles", value=f"Total (sin @everyone): {len(roles)}\nTop 10: {preview}", inline=False)

    e.add_field(name="Emojis", value=str(len(g.emojis)), inline=True)
    e.add_field(name="Stickers", value=str(len(getattr(g, "stickers", []))), inline=True)
    e.add_field(name="Icono animado", value=fmt_bool(bool(getattr(g, "icon", None) and g.icon.is_animated())), inline=True)

    return e

def build_security_boosts_embed(g: discord.Guild) -> discord.Embed:
    e = discord.Embed(title=f"{g.name} — Seguridad & Nitro", color=discord.Color.orange())
    v_level = str(g.verification_level).split(".")[-1].upper()
    nsfw_level = str(getattr(g, "nsfw_level", "—")).split(".")[-1]
    explicit_filter = str(getattr(g, "explicit_content_filter", "—")).split(".")[-1]
    e.add_field(name="Seguridad", value=f"Verificación: {v_level}\nNSFW: {nsfw_level}\nFiltro explícito: {explicit_filter}", inline=True)

    boosts = getattr(g, "premium_subscription_count", 0) or 0
    tier = getattr(g, "premium_tier", 0) or 0
    e.add_field(name="Boosts", value=boost_bar(boosts, tier), inline=False)

    features = ", ".join(sorted(g.features)) if g.features else "—"
    e.add_field(name="Features", value=features, inline=False)
    return e

def build_bot_perms_embed(g: discord.Guild) -> discord.Embed:
    e = discord.Embed(title=f"{g.name} — Permisos del bot", color=discord.Color.brand_red())
    me = g.me
    if not me:
        e.description = "No pude resolver la membresía del bot."
        return e
    p = me.guild_permissions
    checks = {
        "manage_guild": p.manage_guild,
        "manage_channels": p.manage_channels,
        "manage_roles": p.manage_roles,
        "view_audit_log": p.view_audit_log,
        "kick_members": p.kick_members,
        "ban_members": p.ban_members,
        "manage_messages": p.manage_messages,
        "read_message_history": p.read_message_history,
        "mention_everyone": p.mention_everyone,
        "timeout_members/moderate_members": getattr(p, "moderate_members", False) or getattr(p, "timeout_members", False),
        "create_instant_invite": p.create_instant_invite,
        "connect": p.connect,
        "speak": p.speak,
    }
    items = list(checks.items())
    mid = (len(items) + 1) // 2
    left = "\n".join(f"{fmt_bool(ok)} {name}" for name, ok in items[:mid]) or "—"
    right = "\n".join(f"{fmt_bool(ok)} {name}" for name, ok in items[mid:]) or "—"
    e.add_field(name="Permisos (1/2)", value=left, inline=True)
    e.add_field(name="Permisos (2/2)", value=right, inline=True)

    top_role = me.top_role
    e.add_field(name="Top role del bot", value=f"{top_role.name} (pos. {top_role.position})" if top_role else "—", inline=False)
    return e

# ───────────────────── Views ─────────────────────

class GuildInfoView(ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, owner_id: int, back_to_list: Optional[Tuple[int, int]] = None, timeout: int = 180):
        """
        back_to_list: (page_index, per_page) para reconstruir la lista al volver
        """
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.back_to_list = back_to_list
        self.page = "overview"  # overview | people | roles | security | perms

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo el owner puede usar estos controles.", ephemeral=True)
            return False
        return True

    def get_guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)

    def current_embed(self) -> discord.Embed:
        g = self.get_guild()
        if not g:
            return discord.Embed(
                title="Servidor no disponible",
                description="El bot ya no está en ese servidor.",
                color=discord.Color.red()
            )
        if self.page == "overview":
            return build_overview_embed(g)
        if self.page == "people":
            return build_people_channels_embed(g)
        if self.page == "roles":
            return build_roles_emojis_embed(g)
        if self.page == "security":
            return build_security_boosts_embed(g)
        if self.page == "perms":
            return build_bot_perms_embed(g)
        return build_overview_embed(g)

    # ⬇⬇⬇ Firma correcta: (self, interaction, button)
    @ui.button(label="Resumen", style=discord.ButtonStyle.primary)
    async def btn_overview(self, interaction: discord.Interaction, button: ui.Button):
        self.page = "overview"
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @ui.button(label="Miembros/Canales", style=discord.ButtonStyle.secondary)
    async def btn_people(self, interaction: discord.Interaction, button: ui.Button):
        self.page = "people"
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @ui.button(label="Roles/Emojis", style=discord.ButtonStyle.secondary)
    async def btn_roles(self, interaction: discord.Interaction, button: ui.Button):
        self.page = "roles"
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @ui.button(label="Seguridad/Nitro", style=discord.ButtonStyle.secondary)
    async def btn_security(self, interaction: discord.Interaction, button: ui.Button):
        self.page = "security"
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @ui.button(label="Permisos del bot", style=discord.ButtonStyle.secondary)
    async def btn_perms(self, interaction: discord.Interaction, button: ui.Button):
        self.page = "perms"
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @ui.button(label="Volver a lista", style=discord.ButtonStyle.success, row=1)
    async def btn_back(self, interaction: discord.Interaction, button: ui.Button):
        if not self.back_to_list:
            await interaction.response.edit_message(content="No hay lista previa.", embed=self.current_embed(), view=self)
            return
        page_index, per_page = self.back_to_list
        view = ServerListView(self.bot, self.owner_id, page_index=page_index, per_page=per_page)
        await interaction.response.edit_message(embed=view.build_list_embed(), view=view)

    @ui.button(label="Refrescar", style=discord.ButtonStyle.secondary, row=1)
    async def btn_refresh(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @ui.button(label="Cerrar", style=discord.ButtonStyle.danger, row=1)
    async def btn_close(self, interaction: discord.Interaction, button: ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            await interaction.message.delete()
        except Exception:
            pass

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True

class ServerSelect(ui.Select):
    def __init__(self, bot: commands.Bot, owner_id: int, page_index: int, per_page: int):
        self.bot = bot
        self.owner_id = owner_id
        self.page_index = page_index
        self.per_page = per_page

        guilds = sorted(bot.guilds, key=lambda g: g.id)
        start = page_index * per_page
        chunk = guilds[start : start + per_page]

        options = []
        for g in chunk:
            label = trim(g.name, 90) or "Sin nombre"
            desc = f"ID: {g.id} | 👥 {getattr(g, 'member_count', 'N/D')}"
            options.append(discord.SelectOption(label=label, description=trim(desc, 100), value=str(g.id)))

        super().__init__(placeholder="Selecciona un servidor…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo el owner puede usar estos controles.", ephemeral=True)
            return
        guild_id = int(self.values[0])
        view = GuildInfoView(self.bot, guild_id, self.owner_id, back_to_list=(self.page_index, self.per_page))
        await interaction.response.edit_message(embed=view.current_embed(), view=view)

class ServerListView(ui.View):
    def __init__(self, bot: commands.Bot, owner_id: int, page_index: int = 0, per_page: int = 25, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.owner_id = owner_id
        self.page_index = page_index
        self.per_page = max(1, min(per_page, 25))  # Select soporta hasta 25 opciones
        # Añadimos el Select dinámicamente
        self.select = ServerSelect(bot, owner_id, page_index, self.per_page)
        self.add_item(self.select)

    def total_pages(self) -> int:
        total = len(self.bot.guilds)
        return max(1, math.ceil(total / self.per_page))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo el owner puede usar estos controles.", ephemeral=True)
            return False
        return True

    def build_list_embed(self) -> discord.Embed:
        guilds = sorted(self.bot.guilds, key=lambda g: g.id)
        total = len(guilds)
        start = self.page_index * self.per_page
        chunk = guilds[start : start + self.per_page]

        e = discord.Embed(title=f"Servidores ({total})", color=discord.Color.blurple())
        if not chunk:
            e.description = "_No hay servidores en esta página._"
        else:
            for g in chunk:
                owner = getattr(g, "owner", None)
                owner_txt = f"{owner} ({owner.id})" if owner else "desconocido"
                member_count = getattr(g, "member_count", "N/D")
                value = (
                    f"ID: `{g.id}`\n"
                    f"👑 {owner_txt}\n"
                    f"👥 {member_count} miembros\n"
                    f"🗓️ {discord.utils.format_dt(g.created_at, style='d')}"
                )
                e.add_field(name=discord.utils.escape_markdown(g.name), value=value, inline=False)

        e.set_footer(text=f"Página {self.page_index + 1}/{self.total_pages()} • Selecciona un servidor en el menú para ver su ficha")
        return e

    # ⬇⬇⬇ Firmas correctas y sin clear_items(): reemplazamos solo el Select
    @ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button):
        self.page_index = (self.page_index - 1) % self.total_pages()
        self.remove_item(self.select)
        self.select = ServerSelect(self.bot, self.owner_id, self.page_index, self.per_page)
        self.add_item(self.select)
        await interaction.response.edit_message(embed=self.build_list_embed(), view=self)

    @ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        self.page_index = (self.page_index + 1) % self.total_pages()
        self.remove_item(self.select)
        self.select = ServerSelect(self.bot, self.owner_id, self.page_index, self.per_page)
        self.add_item(self.select)
        await interaction.response.edit_message(embed=self.build_list_embed(), view=self)

    @ui.button(label="Refrescar", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.remove_item(self.select)
        self.select = ServerSelect(self.bot, self.owner_id, self.page_index, self.per_page)
        self.add_item(self.select)
        await interaction.response.edit_message(embed=self.build_list_embed(), view=self)

    @ui.button(label="Cerrar", style=discord.ButtonStyle.danger, row=1)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        try:
            await interaction.message.delete()
        except Exception:
            pass

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True

# ───────────────────── Cog ─────────────────────

class OwnerCog(commands.Cog):
    """Comandos del owner para listar e inspeccionar servidores (sin invitaciones ni jump link)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="servers", invoke_without_command=True)
    @owner_only()
    async def servers_group(self, ctx: commands.Context):
        """Abre la lista interactiva (página 1)."""
        view = ServerListView(self.bot, OWNER_ID, page_index=0, per_page=25)
        await ctx.reply(embed=view.build_list_embed(), view=view, mention_author=False)

    @servers_group.command(name="list")
    @owner_only()
    async def list_cmd(self, ctx: commands.Context, page: int = 1):
        """Abre la lista interactiva en la página indicada (1-indexed)."""
        page = max(1, page) - 1
        view = ServerListView(self.bot, OWNER_ID, page_index=page, per_page=25)
        await ctx.reply(embed=view.build_list_embed(), view=view, mention_author=False)

    @servers_group.command(name="info")
    @owner_only()
    async def info_cmd(self, ctx: commands.Context, *, guild_query: str):
        """Abre la ficha del servidor (con pestañas)."""
        g = resolve_guild(self.bot, guild_query)
        if not g:
            await ctx.reply("No encontré ese servidor por ID o nombre.", mention_author=False)
            return
        view = GuildInfoView(self.bot, g.id, OWNER_ID)
        await ctx.reply(embed=view.current_embed(), view=view, mention_author=False)

    @commands.command(name="slashsync", aliases=["syncslash", "appsync"])
    @owner_only()
    async def slashsync_cmd(self, ctx: commands.Context, scope: str = "global"):
        """Sincroniza slash commands globalmente o por guild."""
        normalized = (scope or "global").strip().lower()
        aliases = {
            "global": "global",
            "guild": "guild",
            "server": "guild",
            "all": "all",
        }
        normalized = aliases.get(normalized)
        if normalized is None:
            await ctx.reply("Uso: `c!slashsync [global|guild|all]`.", mention_author=False)
            return

        summary: list[str] = []

        if normalized in {"global", "all"}:
            synced = await self.bot.tree.sync()
            summary.append(f"Global: {len(synced)} comando(s) sincronizado(s).")

        if normalized == "guild":
            if ctx.guild is None:
                await ctx.reply(
                    "Para `guild` debes usar el comando dentro de un servidor.",
                    mention_author=False,
                )
                return
            synced = await self.bot.tree.sync(guild=ctx.guild)
            summary.append(f"Guild actual ({ctx.guild.name}): {len(synced)} comando(s) sincronizado(s).")
        elif normalized == "all":
            success = 0
            failed: list[str] = []
            for guild in self.bot.guilds:
                try:
                    await self.bot.tree.sync(guild=guild)
                    success += 1
                except discord.HTTPException:
                    failed.append(f"{guild.name} ({guild.id})")

            summary.append(f"Guilds: {success}/{len(self.bot.guilds)} sincronizados.")
            if failed:
                preview = ", ".join(failed[:5])
                suffix = " ..." if len(failed) > 5 else ""
                summary.append(f"Fallos: {preview}{suffix}")

        await ctx.reply("\n".join(summary), mention_author=False)

    async def _apply_presence_preset(self, preset_row) -> None:
        await self.bot.change_presence(
            status=resolve_presence_status(preset_row["status"]),
            activity=build_presence_activity(
                preset_row["activity_type"],
                preset_row["activity_text"],
                preset_row["activity_emoji"],
            ),
        )

    @commands.group(name="presence", invoke_without_command=True)
    @owner_only()
    async def presence_group(self, ctx: commands.Context):
        """Gestiona presets de presencia del bot."""
        current = db.get_active_bot_presence_preset()
        embed = build_presence_embed(dict(current) if current else None, title="Presence presets")
        embed.add_field(
            name="Comandos",
            value=(
                "`c!presence custom <estado> <texto>`\n"
                "`c!presence custom <estado> <emoji> | <texto>`\n"
                "`c!presence add <nombre> <tipo> <estado> <texto>`\n"
                "`c!presence add <nombre> custom <estado> <emoji> | <texto>`\n"
                "`c!presence set <nombre>`\n"
                "`c!presence list`\n"
                "`c!presence remove <nombre>`\n"
                "`c!presence clear`"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                "Tipos: custom, playing, listening, watching, competing | "
                "Estados: online, idle, dnd, invisible | "
                "Emoji visible: usa unicode, por ejemplo 🔗 | Custom emoji de servidor no lo muestra Discord en bots"
            )
        )
        await ctx.reply(embed=embed, mention_author=False)

    @presence_group.command(name="custom", aliases=["bubble", "status"])
    @owner_only()
    async def presence_custom(self, ctx: commands.Context, status: str = "online", *, text: str):
        """Aplica al instante un custom status persistente."""
        normalized_status = normalize_presence_status(status)
        if normalized_status is None:
            await ctx.reply(
                f"Estado invalido. Usa uno de: {', '.join(PRESENCE_STATUSES)}.",
                mention_author=False,
            )
            return
        raw_activity_emoji, activity_text = split_custom_status_input(text)
        if not activity_text:
            await ctx.reply("Debes indicar el texto del custom status.", mention_author=False)
            return
        if len(activity_text) > 128:
            await ctx.reply("El texto del estado no puede superar 128 caracteres.", mention_author=False)
            return
        activity_emoji = raw_activity_emoji.strip() if raw_activity_emoji else None
        if activity_emoji and looks_like_custom_emoji_reference(activity_emoji):
            await ctx.reply(
                "Discord no muestra emojis custom de servidor en el custom status de bots. Usa un emoji unicode en el texto, por ejemplo `c!presence custom online 🔗 | c!help | c!copy`.",
                mention_author=False,
            )
            return

        preset_name = "_quick_custom"
        db.upsert_bot_presence_preset(
            preset_name,
            "custom",
            normalized_status,
            activity_text,
            activity_emoji,
        )
        db.set_active_bot_presence_preset(preset_name)
        preset = db.get_active_bot_presence_preset()
        await self._apply_presence_preset(preset)

        embed = build_presence_embed(dict(preset), title="Custom status activado")
        await ctx.reply(embed=embed, mention_author=False)

    @presence_group.command(name="add")
    @owner_only()
    async def presence_add(self, ctx: commands.Context, name: str, activity_type: str, status: str, *, text: str):
        """Crea o actualiza un preset de presencia."""
        normalized_type = normalize_presence_activity_type(activity_type)
        normalized_status = normalize_presence_status(status)
        if normalized_type is None:
            await ctx.reply(
                f"Tipo invalido. Usa uno de: {', '.join(PRESENCE_ACTIVITY_TYPES)}.",
                mention_author=False,
            )
            return
        if normalized_status is None:
            await ctx.reply(
                f"Estado invalido. Usa uno de: {', '.join(PRESENCE_STATUSES)}.",
                mention_author=False,
            )
            return
        raw_activity_emoji = None
        activity_emoji = None
        activity_text = text
        if normalized_type == "custom":
            raw_activity_emoji, activity_text = split_custom_status_input(text)
            activity_emoji = raw_activity_emoji.strip() if raw_activity_emoji else None
            if activity_emoji and looks_like_custom_emoji_reference(activity_emoji):
                await ctx.reply(
                    "Discord no muestra emojis custom de servidor en el custom status de bots. Usa un emoji unicode en el texto, por ejemplo `c!presence add promo custom online 🔗 | c!help | c!copy`.",
                    mention_author=False,
                )
                return
        if not activity_text:
            await ctx.reply("Debes indicar el texto del estado.", mention_author=False)
            return
        if len(activity_text) > 128:
            await ctx.reply("El texto del estado no puede superar 128 caracteres.", mention_author=False)
            return

        current = db.get_active_bot_presence_preset()
        db.upsert_bot_presence_preset(
            name,
            normalized_type,
            normalized_status,
            activity_text,
            activity_emoji,
        )
        preset = db.get_bot_presence_preset(name)
        if current and current["name"].lower() == preset["name"].lower():
            await self._apply_presence_preset(preset)
        embed = build_presence_embed(dict(preset), title="Preset guardado")
        await ctx.reply(embed=embed, mention_author=False)

    @presence_group.command(name="set", aliases=["use", "apply"])
    @owner_only()
    async def presence_set(self, ctx: commands.Context, *, name: str):
        """Activa un preset guardado y lo aplica al bot."""
        preset = db.get_bot_presence_preset(name)
        if not preset:
            await ctx.reply("No existe un preset con ese nombre.", mention_author=False)
            return

        db.set_active_bot_presence_preset(name)
        preset = db.get_active_bot_presence_preset()
        await self._apply_presence_preset(preset)

        embed = build_presence_embed(dict(preset), title="Preset activado")
        await ctx.reply(embed=embed, mention_author=False)

    @presence_group.command(name="list")
    @owner_only()
    async def presence_list(self, ctx: commands.Context):
        """Lista todos los presets de presencia."""
        rows = db.list_bot_presence_presets()
        if not rows:
            await ctx.reply("No hay presets de presencia guardados.", mention_author=False)
            return

        embed = discord.Embed(title="Presets de presencia", color=discord.Color.blurple())
        for row in rows[:25]:
            active_prefix = "[ACTIVO]\n" if row["is_active"] else ""
            embed.add_field(
                name=row["name"],
                value=(
                    f"{active_prefix}"
                    f"Tipo: `{row['activity_type']}`\n"
                    f"Estado: `{row['status']}`\n"
                    f"Emoji: {row['activity_emoji'] or '—'}\n"
                    f"Texto: {row['activity_text']}"
                ),
                inline=False,
            )

        if len(rows) > 25:
            embed.set_footer(text=f"Mostrando 25 de {len(rows)} presets.")
        await ctx.reply(embed=embed, mention_author=False)

    @presence_group.command(name="remove", aliases=["delete", "del"])
    @owner_only()
    async def presence_remove(self, ctx: commands.Context, *, name: str):
        """Elimina un preset de presencia."""
        removed = db.delete_bot_presence_preset(name)
        if not removed:
            await ctx.reply("No existe un preset con ese nombre.", mention_author=False)
            return

        current = db.get_active_bot_presence_preset()
        if current is None:
            await self.bot.apply_configured_presence()
        await ctx.reply(f"Preset `{name}` eliminado.", mention_author=False)

    @presence_group.command(name="clear")
    @owner_only()
    async def presence_clear(self, ctx: commands.Context):
        """Elimina todos los presets de presencia."""
        db.clear_bot_presence_presets()
        await self.bot.apply_configured_presence()
        await ctx.reply("Todos los presets de presencia fueron eliminados.", mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerCog(bot))
