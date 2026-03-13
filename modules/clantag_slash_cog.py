from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from database import delete_clantag_settings, set_clantag_settings
from modules.clantag_cog import ClanTagCog


class ConfirmResetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Eliminar todo", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class ClanTagSlashCog(commands.Cog):
    clantag = app_commands.Group(name="clantag", description="Gestiona roles por clan tag")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_clantag_cog(self) -> ClanTagCog | None:
        cog = self.bot.get_cog("ClanTagCog")
        return cog if isinstance(cog, ClanTagCog) else None

    async def _send(self, interaction: discord.Interaction, content: str | None = None, *, embed: discord.Embed | None = None, view: discord.ui.View | None = None, ephemeral: bool = True):
        if interaction.response.is_done():
            await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)

    async def _ensure_ready(self, interaction: discord.Interaction) -> ClanTagCog | None:
        if interaction.guild is None:
            await self._send(interaction, "Este comando solo funciona dentro de un servidor.")
            return None

        if not interaction.user.guild_permissions.administrator:
            await self._send(interaction, "Necesitas **Administrador** para usar este comando.")
            return None

        cog = self._get_clantag_cog()
        if cog is None:
            await self._send(interaction, "El modulo de clantag no esta cargado ahora mismo.")
            return None

        return cog

    @clantag.command(name="panel", description="Muestra el panel de configuracion de clan tag")
    async def clantag_panel(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        settings = cog._get_settings_cached(interaction.guild.id)
        clan_tag = await cog.get_guild_clan_tag(interaction.guild)

        embed = discord.Embed(title="Sistema de Clan Tag", color=0x5865F2)
        role = interaction.guild.get_role(settings.get("role_id")) if settings.get("role_id") else None
        channel = interaction.guild.get_channel(settings.get("channel_id")) if settings.get("channel_id") else None
        remove_channel = interaction.guild.get_channel(settings.get("remove_channel_id")) if settings.get("remove_channel_id") else None
        remove_enabled = settings.get("remove_enabled", 0)
        remove_status = remove_channel.mention if remove_channel else "`No configurado`"
        if not remove_enabled:
            remove_status = f"~~{remove_status}~~ (desactivado)"

        embed.add_field(name="Tag del servidor", value=f"`{clan_tag}`" if clan_tag else "Sin detectar", inline=True)
        embed.add_field(name="Rol", value=role.mention if role else "`No configurado`", inline=True)
        embed.add_field(name="Canal (anadir)", value=channel.mention if channel else "`No configurado`", inline=True)
        embed.add_field(name="Canal (removido)", value=remove_status, inline=True)
        embed.add_field(
            name="Comandos",
            value=(
                "`/clantag role`  `/clantag channel`\n"
                "`/clantag removechannel`  `/clantag removenotify`\n"
                "`/clantag list`  `/clantag reset`\n"
                "Editor avanzado: `c!clantag embed` o `!clantag embed`"
            ),
            inline=False,
        )
        await self._send(interaction, embed=embed)

    @clantag.command(name="role", description="Configura el rol para usuarios con clan tag")
    @app_commands.describe(rol="Rol que recibiran los usuarios con el clan tag del servidor")
    async def clantag_role(self, interaction: discord.Interaction, rol: discord.Role):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_clantag_settings(interaction.guild.id, role_id=rol.id)
        cog._refresh_settings_cache(interaction.guild.id)
        embed = discord.Embed(
            title="Rol configurado",
            description=f"Los usuarios con el clan tag del servidor recibiran {rol.mention}",
            color=0x57F287,
        )
        await self._send(interaction, embed=embed, ephemeral=False)

    @clantag.command(name="channel", description="Configura el canal de notificaciones de anadido")
    @app_commands.describe(canal="Canal donde se avisara cuando alguien anada el clan tag")
    async def clantag_channel(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_clantag_settings(interaction.guild.id, channel_id=canal.id if canal else None)
        cog._refresh_settings_cache(interaction.guild.id)
        message = (
            f"Canal de notificaciones (anadir) configurado: {canal.mention}"
            if canal
            else "Canal de notificaciones (anadir) desactivado."
        )
        await self._send(interaction, message, ephemeral=False)

    @clantag.command(name="removechannel", description="Configura el canal de notificaciones de removido")
    @app_commands.describe(canal="Canal donde se avisara cuando alguien quite el clan tag")
    async def clantag_remove_channel(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_clantag_settings(interaction.guild.id, remove_channel_id=canal.id if canal else None)
        cog._refresh_settings_cache(interaction.guild.id)
        message = (
            f"Canal de notificaciones (removido) configurado: {canal.mention}"
            if canal
            else "Canal de notificaciones (removido) desactivado."
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
        message = "Notificaciones de removido activadas." if new_value else "Notificaciones de removido desactivadas."
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
            await asyncio.sleep(0.05)

        if not users_with_tag:
            embed = discord.Embed(
                title="Usuarios con el Clan Tag",
                description="No hay usuarios con el clan tag de este servidor.",
                color=0xFEE75C,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title=f"Usuarios con tag `{clan_tag}`", color=0x5865F2)
        listed = users_with_tag[:20]
        description = "\n".join(f"• {member.mention}" for member in listed)
        if len(users_with_tag) > 20:
            description += f"\n... y {len(users_with_tag) - 20} mas"
        embed.description = description
        embed.set_footer(text=f"Total: {len(users_with_tag)} usuarios")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @clantag.command(name="reset", description="Borra toda la configuracion de clan tag")
    async def clantag_reset(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        view = ConfirmResetView()
        embed = discord.Embed(
            title="Estas seguro?",
            description="Esto eliminara toda la configuracion de clan tag.",
            color=0xFEE75C,
        )
        await self._send(interaction, embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            await interaction.followup.send("Operacion cancelada.", ephemeral=True)
            return

        delete_clantag_settings(interaction.guild.id)
        cog._invalidate_settings_cache(interaction.guild.id)
        await interaction.followup.send("Toda la configuracion de clan tag ha sido borrada.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ClanTagSlashCog(bot))
