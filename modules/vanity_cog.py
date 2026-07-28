"""
🔗 Vanity Role Module
Da roles a usuarios que tengan vanitys en su estado personalizado
"""

import asyncio
import logging
import re
import time

import discord
from discord import ui
from discord.ext import commands

from command_utils import RestrictedView
from database import (
    add_vanity_code,
    delete_all_vanity,
    get_vanity_codes,
    get_vanity_settings,
    remove_vanity_code,
    set_vanity_settings,
    setup_vanity_table,
)
from localization import get_language, translate, translate_language

log = logging.getLogger("bot")


class EmbedEditorModal(ui.Modal):
    """Modal para editar el embed."""

    def __init__(
        self,
        embed_type: str,
        current_title: str,
        current_desc: str,
        current_color: int,
        language: str,
    ):
        super().__init__(title=translate_language(language, "common.embed_editor_title"))
        self.embed_type = embed_type

        self.title_input = ui.TextInput(
            label=translate_language(language, "common.embed_title"),
            default=current_title,
            max_length=256,
            required=True,
            placeholder=translate_language(language, "vanity.default_add_title"),
        )
        self.desc_input = ui.TextInput(
            label=translate_language(language, "common.embed_description"),
            style=discord.TextStyle.paragraph,
            default=current_desc,
            max_length=2000,
            required=True,
            placeholder="Variables: {user} {role} {vanity} {server}",
        )
        self.color_input = ui.TextInput(
            label=translate_language(language, "common.embed_color"),
            default=format(current_color, "x"),
            max_length=6,
            required=True,
            placeholder=translate_language(language, "common.embed_color_placeholder"),
        )

        self.add_item(self.title_input)
        self.add_item(self.desc_input)
        self.add_item(self.color_input)

        self.new_title = None
        self.new_desc = None
        self.new_color = None

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.new_color = int(self.color_input.value, 16)
        except ValueError:
            self.new_color = 0x5865F2

        self.new_title = self.title_input.value
        self.new_desc = self.desc_input.value
        await interaction.response.defer()


class VanityCog(commands.Cog):
    """Sistema de roles por vanity URL en estado."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        setup_vanity_table()
        self._settings_cache = {}
        self._codes_cache = {}
        self._cache_ttl_sec = 30.0

    def _invalidate_guild_cache(self, guild_id: int):
        self._settings_cache.pop(guild_id, None)
        self._codes_cache.pop(guild_id, None)

    def _get_settings_cached(self, guild_id: int) -> dict:
        now = time.monotonic()
        cached = self._settings_cache.get(guild_id)
        if cached and now < cached["expires_at"]:
            return dict(cached["value"])

        settings = get_vanity_settings(guild_id) or {}
        self._settings_cache[guild_id] = {
            "expires_at": now + self._cache_ttl_sec,
            "value": settings,
        }
        return dict(settings)

    def _get_codes_cached(self, guild_id: int) -> list:
        now = time.monotonic()
        cached = self._codes_cache.get(guild_id)
        if cached and now < cached["expires_at"]:
            return [dict(item) for item in cached["value"]]

        codes = get_vanity_codes(guild_id)
        normalized = [dict(item) for item in codes]
        self._codes_cache[guild_id] = {
            "expires_at": now + self._cache_ttl_sec,
            "value": normalized,
        }
        return [dict(item) for item in normalized]

    def _refresh_guild_cache(self, guild_id: int):
        self._invalidate_guild_cache(guild_id)
        self._get_settings_cached(guild_id)
        self._get_codes_cached(guild_id)

    def convert_emojis(self, text: str, guild: discord.Guild) -> str:
        """Convierte :emoji: al formato <:emoji:id> automáticamente."""
        # Busca patrones :nombre: que no sean ya formato completo
        pattern = r":([a-zA-Z0-9_]+):"

        def replace_emoji(match):
            emoji_name = match.group(1)
            # Buscar el emoji en el servidor
            for emoji in guild.emojis:
                if emoji.name.lower() == emoji_name.lower():
                    if emoji.animated:
                        return f"<a:{emoji.name}:{emoji.id}>"
                    else:
                        return f"<:{emoji.name}:{emoji.id}>"
            # Si no lo encuentra, dejarlo como está
            return match.group(0)

        return re.sub(pattern, replace_emoji, text)

    def check_vanity(self, member: discord.Member, vanity_code: str) -> bool:
        """Revisa si el usuario tiene la vanity en su estado."""
        for activity in member.activities:
            if (
                isinstance(activity, discord.CustomActivity)
                and activity.name
                and vanity_code.lower() in activity.name.lower()
            ):
                return True
        return False

    def get_matching_vanity(self, member: discord.Member, vanity_codes: list) -> tuple:
        """Retorna (vanity_code, role_id) si el usuario tiene alguna vanity."""
        for vc in vanity_codes:
            if self.check_vanity(member, vc["vanity_code"]):
                return vc["vanity_code"], vc["role_id"]
        return None, None

    def build_embed(
        self, settings: dict, member: discord.Member, vanity: str, role: discord.Role, is_add: bool
    ) -> discord.Embed:
        """Construye el embed personalizado."""
        if is_add:
            title = settings.get("embed_title") or translate(member, "vanity.default_add_title")
            desc = settings.get("embed_description") or translate(
                member,
                "vanity.default_add_description",
                user="{user}",
                vanity="{vanity}",
                role="{role}",
            )
            color = settings.get("embed_color", 0x57F287)
        else:
            title = settings.get("remove_title") or translate(member, "vanity.default_remove_title")
            desc = settings.get("remove_description") or translate(
                member,
                "vanity.default_remove_description",
                user="{user}",
                vanity="{vanity}",
            )
            color = settings.get("remove_color", 0xED4245)

        # Reemplazar variables
        desc = desc.replace("{user}", member.mention)
        desc = desc.replace(
            "{role}",
            role.mention if role else translate(member, "clantag.role_field").lower(),
        )
        desc = desc.replace("{vanity}", vanity)
        desc = desc.replace("{server}", member.guild.name)

        # Convertir :emoji: a formato completo
        title = self.convert_emojis(title, member.guild)
        desc = self.convert_emojis(desc, member.guild)

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        if settings.get("embed_image"):
            embed.set_image(url=settings["embed_image"])

        return embed

    # ══════════════════════════════════════════════════════════
    # EVENTO: Detecta cambios de estado
    # ══════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return

        # Ignorar si está offline
        if after.status == discord.Status.offline:
            return

        vanity_codes = await asyncio.to_thread(self._get_codes_cached, after.guild.id)
        if not vanity_codes:
            return

        settings = await asyncio.to_thread(self._get_settings_cached, after.guild.id)
        channel_id = settings.get("channel_id")
        channel = after.guild.get_channel(channel_id) if channel_id else None

        # Ver qué vanity tiene (si alguna)
        matched_vanity, matched_role_id = self.get_matching_vanity(after, vanity_codes)

        # Roles de vanity que tiene actualmente
        vanity_role_ids = {vc["role_id"] for vc in vanity_codes}
        current_vanity_roles = [r for r in after.roles if r.id in vanity_role_ids]

        if matched_vanity:
            # Tiene una vanity → asegurar que tenga el rol correcto
            role = after.guild.get_role(matched_role_id)
            if role:
                try:
                    stale_roles = [
                        old_role for old_role in current_vanity_roles if old_role.id != matched_role_id
                    ]
                    if stale_roles:
                        await after.remove_roles(*stale_roles, reason="Cambió de vanity")

                    role_was_added = role not in after.roles
                    if role_was_added:
                        await after.add_roles(role, reason=f"Vanity: {matched_vanity}")

                    if role_was_added and channel:
                        embed = self.build_embed(settings, after, matched_vanity, role, is_add=True)
                        await channel.send(embed=embed)
                except discord.Forbidden:
                    log.warning(
                        "No pude reconciliar roles de vanity en guild=%s member=%s por jerarquía o permisos.",
                        after.guild.id,
                        after.id,
                    )
                except discord.HTTPException as exc:
                    log.warning(
                        "Discord rechazó una operación de vanity en guild=%s member=%s: %s",
                        after.guild.id,
                        after.id,
                        exc,
                    )
        else:
            # No tiene ninguna vanity → quitar roles de vanity
            for role in current_vanity_roles:
                try:
                    vanity_for_role = next(
                        (vc["vanity_code"] for vc in vanity_codes if vc["role_id"] == role.id), "vanity"
                    )
                    await after.remove_roles(role, reason="Vanity removida")

                    # Enviar embed de removido si está habilitado
                    if settings.get("remove_enabled"):
                        remove_channel_id = settings.get("remove_channel_id")
                        remove_channel = (
                            after.guild.get_channel(remove_channel_id) if remove_channel_id else None
                        )
                        if remove_channel:
                            embed = self.build_embed(settings, after, vanity_for_role, role, is_add=False)
                            await remove_channel.send(embed=embed)
                except discord.Forbidden:
                    log.warning(
                        "No pude retirar un rol de vanity en guild=%s member=%s.",
                        after.guild.id,
                        after.id,
                    )
                except discord.HTTPException as exc:
                    log.warning(
                        "Discord rechazó el retiro de vanity en guild=%s member=%s: %s",
                        after.guild.id,
                        after.id,
                        exc,
                    )

    # ══════════════════════════════════════════════════════════
    # COMANDOS PRINCIPALES
    # ══════════════════════════════════════════════════════════

    @commands.group(name="vanity", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def vanity(self, ctx: commands.Context):
        """Muestra el panel de configuración de vanity."""
        settings = self._get_settings_cached(ctx.guild.id)
        vanity_codes = self._get_codes_cached(ctx.guild.id)

        embed = discord.Embed(title=translate(ctx, "vanity.panel_title"), color=0x5865F2)

        # Canal de añadir
        channel = ctx.guild.get_channel(settings.get("channel_id")) if settings.get("channel_id") else None
        embed.add_field(
            name=translate(ctx, "vanity.channel_add_field"),
            value=channel.mention if channel else translate(ctx, "common.not_configured_code"),
            inline=True,
        )

        # Canal de removido
        remove_channel = (
            ctx.guild.get_channel(settings.get("remove_channel_id"))
            if settings.get("remove_channel_id")
            else None
        )
        remove_enabled = settings.get("remove_enabled", 0)
        remove_status = (
            f"{remove_channel.mention}" if remove_channel else translate(ctx, "common.not_configured_code")
        )
        if not remove_enabled:
            remove_status = f"~~{remove_status}~~ ({translate(ctx, 'common.disabled')})"
        embed.add_field(
            name=translate(ctx, "vanity.channel_remove_field"),
            value=remove_status,
            inline=True,
        )

        # Cantidad de vanitys
        embed.add_field(
            name=translate(ctx, "vanity.active_field"),
            value=f"`{len(vanity_codes)}`",
            inline=True,
        )

        # Lista de vanitys
        if vanity_codes:
            vanity_list = []
            for vc in vanity_codes[:10]:  # Máximo 10
                role = ctx.guild.get_role(vc["role_id"])
                role_text = role.mention if role else translate(ctx, "common.role_deleted")
                vanity_list.append(f"• `{vc['vanity_code']}` → {role_text}")

            embed.add_field(
                name=translate(ctx, "vanity.list_field"),
                value="\n".join(vanity_list) or translate(ctx, "common.none"),
                inline=False,
            )

        # Comandos
        embed.add_field(
            name=translate(ctx, "common.commands"),
            value=translate(ctx, "vanity.commands_value"),
            inline=False,
        )

        await ctx.send(embed=embed)

    @vanity.command(name="add")
    @commands.has_permissions(administrator=True)
    async def vanity_add(self, ctx: commands.Context, codigo: str, rol: discord.Role):
        """Añade una vanity y su rol."""
        me = ctx.guild.me
        if rol.is_default() or rol.managed or (me is not None and rol >= me.top_role):
            await ctx.send(translate(ctx, "common.role_unmanageable"))
            return

        # Asegurar que exista settings
        if not self._get_settings_cached(ctx.guild.id):
            set_vanity_settings(ctx.guild.id)
            self._refresh_guild_cache(ctx.guild.id)

        if add_vanity_code(ctx.guild.id, codigo.lower(), rol.id):
            self._refresh_guild_cache(ctx.guild.id)
            embed = discord.Embed(
                title=translate(ctx, "vanity.add_title"),
                description=translate(
                    ctx,
                    "vanity.add_description",
                    code=codigo,
                    role=rol.mention,
                ),
                color=0x57F287,
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(translate(ctx, "vanity.duplicate", code=codigo))

    @vanity.command(name="remove", aliases=["delete", "del"])
    @commands.has_permissions(administrator=True)
    async def vanity_remove(self, ctx: commands.Context, codigo: str):
        """Elimina una vanity."""
        if remove_vanity_code(ctx.guild.id, codigo.lower()):
            self._refresh_guild_cache(ctx.guild.id)
            await ctx.send(translate(ctx, "vanity.removed", code=codigo))
        else:
            await ctx.send(translate(ctx, "vanity.not_found", code=codigo))

    @vanity.command(name="channel", aliases=["canal"])
    @commands.has_permissions(administrator=True)
    async def vanity_channel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Configura el canal de logs (cuando añaden vanity)."""
        set_vanity_settings(ctx.guild.id, channel_id=canal.id if canal else None)
        self._refresh_guild_cache(ctx.guild.id)

        if canal:
            await ctx.send(translate(ctx, "common.channel_add_set", channel=canal.mention))
        else:
            await ctx.send(translate(ctx, "common.channel_add_disabled"))

    @vanity.command(name="removechannel", aliases=["removecanal"])
    @commands.has_permissions(administrator=True)
    async def vanity_remove_channel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Configura el canal para notificaciones de removido."""
        set_vanity_settings(ctx.guild.id, remove_channel_id=canal.id if canal else None)
        self._refresh_guild_cache(ctx.guild.id)

        if canal:
            await ctx.send(translate(ctx, "common.channel_remove_set", channel=canal.mention))
        else:
            await ctx.send(translate(ctx, "common.channel_remove_disabled"))

    @vanity.command(name="removenotify", aliases=["removenotificacion"])
    @commands.has_permissions(administrator=True)
    async def vanity_remove_notify(self, ctx: commands.Context):
        """Activa/desactiva notificaciones cuando quitan la vanity."""
        settings = self._get_settings_cached(ctx.guild.id)
        current = settings.get("remove_enabled", 0)
        new_value = 0 if current else 1

        set_vanity_settings(ctx.guild.id, remove_enabled=new_value)
        self._refresh_guild_cache(ctx.guild.id)

        if new_value:
            await ctx.send(translate(ctx, "common.remove_notifications_enabled"))
        else:
            await ctx.send(translate(ctx, "common.remove_notifications_disabled"))

    @vanity.command(name="list", aliases=["users", "lista"])
    @commands.has_permissions(administrator=True)
    async def vanity_list(self, ctx: commands.Context):
        """Muestra usuarios con vanity en su estado."""
        vanity_codes = self._get_codes_cached(ctx.guild.id)

        if not vanity_codes:
            await ctx.send(translate(ctx, "vanity.list_none"))
            return

        msg = await ctx.send(translate(ctx, "vanity.list_searching"))

        results = {}
        for vc in vanity_codes:
            results[vc["vanity_code"]] = []

        for member in ctx.guild.members:
            if member.bot:
                continue
            for vc in vanity_codes:
                if self.check_vanity(member, vc["vanity_code"]):
                    results[vc["vanity_code"]].append(member)
                    break

        embed = discord.Embed(title=translate(ctx, "vanity.list_title"), color=0x5865F2)

        total = 0
        visible_results = list(results.items())[:24]
        for vanity, members in visible_results:
            total += len(members)
            if members:
                member_list = ", ".join([m.mention for m in members[:15]])
                if len(members) > 15:
                    member_list += translate(
                        ctx,
                        "vanity.list_more",
                        count=len(members) - 15,
                    )
            else:
                member_list = f"*{translate(ctx, 'common.none')}*"

            embed.add_field(name=f"🔗 {vanity} ({len(members)})", value=member_list, inline=False)

        embed.set_footer(text=translate(ctx, "common.total_users", count=total))
        if len(results) > len(visible_results):
            embed.set_footer(
                text=translate(
                    ctx,
                    "vanity.list_total_limited",
                    total=total,
                    visible=len(visible_results),
                    count=len(results),
                )
            )
        await msg.edit(content=None, embed=embed)

    @vanity.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def vanity_embed(self, ctx: commands.Context):
        """Personaliza los embeds de notificación."""
        settings = self._get_settings_cached(ctx.guild.id)

        # Vista con botones
        class EmbedButtons(RestrictedView):
            def __init__(self, cog, settings, author_id: int):
                super().__init__(
                    author_id=author_id,
                    timeout=120,
                    required_permissions=("administrator",),
                )
                self.cog = cog
                self.settings = settings
                language = get_language(ctx)
                self.edit_add.label = translate_language(language, "common.embed_add_button")
                self.edit_remove.label = translate_language(language, "common.embed_remove_button")
                self.preview.label = translate_language(language, "common.embed_preview_button")

            @ui.button(label="✅ Embed de Añadido", style=discord.ButtonStyle.success)
            async def edit_add(self, interaction: discord.Interaction, button: ui.Button):
                modal = EmbedEditorModal(
                    "add",
                    self.settings.get("embed_title") or translate(interaction, "vanity.default_add_title"),
                    self.settings.get("embed_description")
                    or translate(
                        interaction,
                        "vanity.default_add_description",
                        user="{user}",
                        vanity="{vanity}",
                        role="{role}",
                    ),
                    self.settings.get("embed_color", 0x57F287),
                    get_language(interaction),
                )
                await interaction.response.send_modal(modal)
                await modal.wait()

                if modal.new_title:
                    set_vanity_settings(
                        ctx.guild.id,
                        embed_title=modal.new_title,
                        embed_description=modal.new_desc,
                        embed_color=modal.new_color,
                    )
                    self.cog._refresh_guild_cache(ctx.guild.id)
                    self.settings = self.cog._get_settings_cached(ctx.guild.id)
                    await interaction.followup.send(
                        translate(interaction, "common.embed_add_updated"),
                        ephemeral=True,
                    )

            @ui.button(label="❌ Embed de Removido", style=discord.ButtonStyle.danger)
            async def edit_remove(self, interaction: discord.Interaction, button: ui.Button):
                modal = EmbedEditorModal(
                    "remove",
                    self.settings.get("remove_title")
                    or translate(interaction, "vanity.default_remove_title"),
                    self.settings.get("remove_description")
                    or translate(
                        interaction,
                        "vanity.default_remove_description",
                        user="{user}",
                        vanity="{vanity}",
                    ),
                    self.settings.get("remove_color", 0xED4245),
                    get_language(interaction),
                )
                await interaction.response.send_modal(modal)
                await modal.wait()

                if modal.new_title:
                    set_vanity_settings(
                        ctx.guild.id,
                        remove_title=modal.new_title,
                        remove_description=modal.new_desc,
                        remove_color=modal.new_color,
                    )
                    self.cog._refresh_guild_cache(ctx.guild.id)
                    self.settings = self.cog._get_settings_cached(ctx.guild.id)
                    await interaction.followup.send(
                        translate(interaction, "common.embed_remove_updated"),
                        ephemeral=True,
                    )

            @ui.button(label="👁️ Vista Previa", style=discord.ButtonStyle.secondary)
            async def preview(self, interaction: discord.Interaction, button: ui.Button):
                # Crear un rol falso para la vista previa
                fake_role = ctx.guild.roles[0]  # @everyone como placeholder

                embed_add = self.cog.build_embed(
                    self.settings, ctx.author, "discord.gg/ejemplo", fake_role, is_add=True
                )
                embed_remove = self.cog.build_embed(
                    self.settings, ctx.author, "discord.gg/ejemplo", fake_role, is_add=False
                )

                await interaction.response.send_message(
                    f"**{translate(interaction, 'common.embed_preview')}**",
                    embeds=[embed_add, embed_remove],
                    ephemeral=True,
                )

        embed = discord.Embed(
            title=translate(ctx, "vanity.editor_title"),
            description=translate(ctx, "vanity.editor_description"),
            color=0x5865F2,
        )

        view = EmbedButtons(self, settings, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @vanity.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def vanity_reset(self, ctx: commands.Context):
        """Elimina toda la configuración de vanity."""
        # Confirmación
        embed = discord.Embed(
            title=translate(ctx, "vanity.reset_title"),
            description=translate(ctx, "vanity.reset_description"),
            color=0xFEE75C,
        )

        class ConfirmView(RestrictedView):
            def __init__(self, author_id: int):
                super().__init__(
                    author_id=author_id,
                    timeout=30,
                    required_permissions=("administrator",),
                )
                self.confirmed = False
                self.confirm.label = translate(ctx, "vanity.reset_confirm")
                self.cancel.label = translate(ctx, "common.cancel")

            @ui.button(label="Sí, eliminar", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: ui.Button):
                self.confirmed = True
                self.stop()
                await interaction.response.defer()

            @ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: ui.Button):
                self.stop()
                await interaction.response.defer()

        view = ConfirmView(ctx.author.id)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()

        if view.confirmed:
            delete_all_vanity(ctx.guild.id)
            self._invalidate_guild_cache(ctx.guild.id)
            embed.title = translate(ctx, "common.configuration_deleted")
            embed.description = translate(ctx, "vanity.reset_done")
            embed.color = 0x57F287
        else:
            embed.title = translate(ctx, "common.cancelled")
            embed.description = translate(ctx, "vanity.reset_cancelled")
            embed.color = 0xED4245

        await msg.edit(embed=embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(VanityCog(bot))
