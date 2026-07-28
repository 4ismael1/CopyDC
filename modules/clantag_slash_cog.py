from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from command_utils import RestrictedView
from database import delete_clantag_settings, set_clantag_settings
from localization import get_language, translate, translate_language
from modules.clantag_cog import ClanTagCog


class ConfirmResetView(RestrictedView):
    def __init__(self, author_id: int, language: str):
        super().__init__(
            author_id=author_id,
            timeout=30,
            required_permissions=("administrator",),
        )
        self.confirmed = False
        self.confirm.label = translate_language(language, "clantag.reset_confirm")
        self.cancel.label = translate_language(language, "common.cancel")

    @discord.ui.button(label="Eliminar todo", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.confirmed = True
        self.disable_all_items()
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.disable_all_items()
        await interaction.response.edit_message(view=self)
        self.stop()


class ClanTagSlashCog(commands.Cog):
    clantag = app_commands.Group(name="clantag", description="Gestiona roles por clan tag")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_clantag_cog(self) -> ClanTagCog | None:
        cog = self.bot.get_cog("ClanTagCog")
        return cog if isinstance(cog, ClanTagCog) else None

    @staticmethod
    async def _is_admin_or_owner(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        if interaction.user.id == interaction.guild.owner_id:
            return True

        resolved_permissions = getattr(interaction, "permissions", None)
        if resolved_permissions and resolved_permissions.administrator:
            return True

        permissions = getattr(interaction.user, "guild_permissions", None)
        if permissions and permissions.administrator:
            return True

        member = interaction.guild.get_member(interaction.user.id)
        if member is not None and member.guild_permissions.administrator:
            return True

        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.HTTPException:
            member = None

        return bool(member and member.guild_permissions.administrator)

    async def _send(
        self,
        interaction: discord.Interaction,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        ephemeral: bool = True,
    ):
        kwargs = {"ephemeral": ephemeral}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view

        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)

    async def _ensure_ready(self, interaction: discord.Interaction) -> ClanTagCog | None:
        if interaction.guild is None:
            await self._send(interaction, translate(interaction, "common.server_only"))
            return None

        if not await self._is_admin_or_owner(interaction):
            await self._send(interaction, translate(interaction, "common.admin_required"))
            return None

        cog = self._get_clantag_cog()
        if cog is None:
            await self._send(interaction, translate(interaction, "clantag.module_unavailable"))
            return None

        return cog

    @clantag.command(name="panel", description="Muestra el panel de configuracion de clan tag")
    async def clantag_panel(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        settings = cog._get_settings_cached(interaction.guild.id)
        clan_tag = await cog.get_guild_clan_tag(interaction.guild)

        embed = discord.Embed(title=translate(interaction, "clantag.panel_title"), color=0x5865F2)
        role = interaction.guild.get_role(settings.get("role_id")) if settings.get("role_id") else None
        channel = (
            interaction.guild.get_channel(settings.get("channel_id")) if settings.get("channel_id") else None
        )
        remove_channel = (
            interaction.guild.get_channel(settings.get("remove_channel_id"))
            if settings.get("remove_channel_id")
            else None
        )
        remove_enabled = settings.get("remove_enabled", 0)
        remove_status = (
            remove_channel.mention if remove_channel else translate(interaction, "common.not_configured_code")
        )
        if not remove_enabled:
            remove_status = f"~~{remove_status}~~ ({translate(interaction, 'common.disabled')})"

        embed.add_field(
            name=translate(interaction, "clantag.server_tag_field"),
            value=f"`{clan_tag}`" if clan_tag else translate(interaction, "clantag.no_detected"),
            inline=True,
        )
        embed.add_field(
            name=translate(interaction, "clantag.role_field"),
            value=role.mention if role else translate(interaction, "common.not_configured_code"),
            inline=True,
        )
        embed.add_field(
            name=translate(interaction, "clantag.channel_add_field"),
            value=channel.mention if channel else translate(interaction, "common.not_configured_code"),
            inline=True,
        )
        embed.add_field(
            name=translate(interaction, "clantag.channel_remove_field"),
            value=remove_status,
            inline=True,
        )
        embed.add_field(
            name=translate(interaction, "common.commands"),
            value=translate(interaction, "clantag.commands_value"),
            inline=False,
        )
        await self._send(interaction, embed=embed)

    @clantag.command(name="role", description="Configura el rol para usuarios con clan tag")
    @app_commands.describe(rol="Rol que recibiran los usuarios con el clan tag del servidor")
    async def clantag_role(self, interaction: discord.Interaction, rol: discord.Role):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        me = interaction.guild.me
        if rol.is_default() or rol.managed or (me is not None and rol >= me.top_role):
            await self._send(
                interaction,
                translate(interaction, "common.role_unmanageable"),
            )
            return

        set_clantag_settings(interaction.guild.id, role_id=rol.id)
        cog._refresh_settings_cache(interaction.guild.id)
        embed = discord.Embed(
            title=translate(interaction, "clantag.role_configured_title"),
            description=translate(
                interaction,
                "clantag.role_configured_description",
                role=rol.mention,
            ),
            color=0x57F287,
        )
        await self._send(interaction, embed=embed, ephemeral=False)

    @clantag.command(name="channel", description="Configura el canal de notificaciones de anadido")
    @app_commands.describe(canal="Canal donde se avisara cuando alguien anada el clan tag")
    async def clantag_channel(
        self, interaction: discord.Interaction, canal: discord.TextChannel | None = None
    ):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_clantag_settings(interaction.guild.id, channel_id=canal.id if canal else None)
        cog._refresh_settings_cache(interaction.guild.id)
        message = (
            translate(interaction, "common.channel_add_set", channel=canal.mention)
            if canal
            else translate(interaction, "common.channel_add_disabled")
        )
        await self._send(interaction, message, ephemeral=False)

    @clantag.command(name="removechannel", description="Configura el canal de notificaciones de removido")
    @app_commands.describe(canal="Canal donde se avisara cuando alguien quite el clan tag")
    async def clantag_remove_channel(
        self, interaction: discord.Interaction, canal: discord.TextChannel | None = None
    ):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_clantag_settings(interaction.guild.id, remove_channel_id=canal.id if canal else None)
        cog._refresh_settings_cache(interaction.guild.id)
        message = (
            translate(interaction, "common.channel_remove_set", channel=canal.mention)
            if canal
            else translate(interaction, "common.channel_remove_disabled")
        )
        await self._send(interaction, message, ephemeral=False)

    @clantag.command(name="removenotify", description="Activa o desactiva las notificaciones de removido")
    async def clantag_remove_notify(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        settings = cog._get_settings_cached(interaction.guild.id)
        new_value = 0 if settings.get("remove_enabled", 0) else 1
        set_clantag_settings(interaction.guild.id, remove_enabled=new_value)
        cog._refresh_settings_cache(interaction.guild.id)
        message = (
            translate(interaction, "common.remove_notifications_enabled")
            if new_value
            else translate(interaction, "common.remove_notifications_disabled")
        )
        await self._send(interaction, message, ephemeral=False)

    @clantag.command(name="list", description="Lista usuarios con el clan tag del servidor")
    async def clantag_list(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        await interaction.response.defer(ephemeral=True)
        users_with_tag = []
        clan_tag = None

        for member in interaction.guild.members:
            if member.bot:
                continue
            has_clan, tag = await cog.member_has_server_clan(member, interaction.guild.id)
            if has_clan:
                users_with_tag.append(member)
                if not clan_tag:
                    clan_tag = tag
        if not users_with_tag:
            embed = discord.Embed(
                title=translate(interaction, "clantag.list_title"),
                description=translate(interaction, "clantag.list_none"),
                color=0xFEE75C,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=translate(interaction, "clantag.list_title_tag", tag=clan_tag),
            color=0x5865F2,
        )
        listed = users_with_tag[:20]
        description = "\n".join(f"- {member.mention}" for member in listed)
        if len(users_with_tag) > 20:
            description += "\n" + translate(
                interaction,
                "clantag.list_more",
                count=len(users_with_tag) - 20,
            )
        embed.description = description
        embed.set_footer(text=translate(interaction, "common.total_users", count=len(users_with_tag)))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @clantag.command(name="reset", description="Borra toda la configuracion de clan tag")
    async def clantag_reset(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        view = ConfirmResetView(interaction.user.id, get_language(interaction))
        embed = discord.Embed(
            title=translate(interaction, "clantag.reset_title"),
            description=translate(interaction, "clantag.reset_description"),
            color=0xFEE75C,
        )
        await self._send(interaction, embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            await interaction.followup.send(
                translate(interaction, "common.cancelled"),
                ephemeral=True,
            )
            return

        delete_clantag_settings(interaction.guild.id)
        cog._invalidate_settings_cache(interaction.guild.id)
        await interaction.followup.send(
            translate(interaction, "clantag.reset_done"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ClanTagSlashCog(bot))
