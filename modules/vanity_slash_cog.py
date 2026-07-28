from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from command_utils import RestrictedView
from database import add_vanity_code, delete_all_vanity, remove_vanity_code, set_vanity_settings
from modules.vanity_cog import VanityCog


class ConfirmResetView(RestrictedView):
    def __init__(self, author_id: int):
        super().__init__(
            author_id=author_id,
            timeout=30,
            required_permissions=("administrator",),
        )
        self.confirmed = False

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


class VanitySlashCog(commands.Cog):
    vanity = app_commands.Group(name="vanity", description="Gestiona vanity roles")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_vanity_cog(self) -> VanityCog | None:
        cog = self.bot.get_cog("VanityCog")
        return cog if isinstance(cog, VanityCog) else None

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

    async def _ensure_ready(self, interaction: discord.Interaction) -> VanityCog | None:
        if interaction.guild is None:
            await self._send(interaction, "Este comando solo funciona dentro de un servidor.")
            return None

        if not await self._is_admin_or_owner(interaction):
            await self._send(interaction, "Necesitas **Administrador** para usar este comando.")
            return None

        cog = self._get_vanity_cog()
        if cog is None:
            await self._send(interaction, "El modulo de vanity no esta cargado ahora mismo.")
            return None

        return cog

    @vanity.command(name="panel", description="Muestra el panel de configuracion de vanity")
    async def vanity_panel(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        settings = cog._get_settings_cached(interaction.guild.id)
        vanity_codes = cog._get_codes_cached(interaction.guild.id)

        embed = discord.Embed(title="Sistema de Vanity Roles", color=0x5865F2)

        channel = (
            interaction.guild.get_channel(settings.get("channel_id")) if settings.get("channel_id") else None
        )
        remove_channel = (
            interaction.guild.get_channel(settings.get("remove_channel_id"))
            if settings.get("remove_channel_id")
            else None
        )
        remove_enabled = settings.get("remove_enabled", 0)
        remove_status = remove_channel.mention if remove_channel else "`No configurado`"
        if not remove_enabled:
            remove_status = f"~~{remove_status}~~ (desactivado)"

        embed.add_field(
            name="Canal (anadir)", value=channel.mention if channel else "`No configurado`", inline=True
        )
        embed.add_field(name="Canal (removido)", value=remove_status, inline=True)
        embed.add_field(name="Vanitys activas", value=f"`{len(vanity_codes)}`", inline=True)

        if vanity_codes:
            lines = []
            for item in vanity_codes[:10]:
                role = interaction.guild.get_role(item["role_id"])
                role_text = role.mention if role else "Rol eliminado"
                lines.append(f"- `{item['vanity_code']}` -> {role_text}")
            embed.add_field(name="Lista de vanitys", value="\n".join(lines), inline=False)

        embed.add_field(
            name="Comandos",
            value=(
                "`/vanity add`  `/vanity remove`\n"
                "`/vanity channel`  `/vanity removechannel`\n"
                "`/vanity removenotify`  `/vanity list`  `/vanity reset`\n"
                "Editor avanzado: `c!vanity embed` o `!vanity embed`"
            ),
            inline=False,
        )
        await self._send(interaction, embed=embed)

    @vanity.command(name="add", description="Anade una vanity y el rol asociado")
    @app_commands.describe(codigo="Codigo vanity, por ejemplo discord.gg/miserver", rol="Rol a asignar")
    async def vanity_add(self, interaction: discord.Interaction, codigo: str, rol: discord.Role):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        me = interaction.guild.me
        if rol.is_default() or rol.managed or (me is not None and rol >= me.top_role):
            await self._send(
                interaction,
                "No puedo administrar ese rol. Usa un rol normal situado debajo del rol del bot.",
            )
            return

        if not cog._get_settings_cached(interaction.guild.id):
            set_vanity_settings(interaction.guild.id)
            cog._refresh_guild_cache(interaction.guild.id)

        if add_vanity_code(interaction.guild.id, codigo.lower(), rol.id):
            cog._refresh_guild_cache(interaction.guild.id)
            embed = discord.Embed(
                title="Vanity anadida",
                description=f"**Codigo:** `{codigo}`\n**Rol:** {rol.mention}",
                color=0x57F287,
            )
            await self._send(interaction, embed=embed, ephemeral=False)
            return

        await self._send(interaction, f"La vanity `{codigo}` ya existe.")

    @vanity.command(name="remove", description="Elimina una vanity configurada")
    @app_commands.describe(codigo="Codigo vanity que quieres eliminar")
    async def vanity_remove(self, interaction: discord.Interaction, codigo: str):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        if remove_vanity_code(interaction.guild.id, codigo.lower()):
            cog._refresh_guild_cache(interaction.guild.id)
            await self._send(interaction, f"Vanity `{codigo}` eliminada.", ephemeral=False)
            return

        await self._send(interaction, f"No existe la vanity `{codigo}`.")

    @vanity.command(name="channel", description="Configura el canal de notificaciones de anadido")
    @app_commands.describe(canal="Canal donde se avisara cuando alguien anada la vanity")
    async def vanity_channel(
        self, interaction: discord.Interaction, canal: discord.TextChannel | None = None
    ):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_vanity_settings(interaction.guild.id, channel_id=canal.id if canal else None)
        cog._refresh_guild_cache(interaction.guild.id)
        message = (
            f"Canal de notificaciones (anadir) configurado: {canal.mention}"
            if canal
            else "Canal de notificaciones (anadir) desactivado."
        )
        await self._send(interaction, message, ephemeral=False)

    @vanity.command(name="removechannel", description="Configura el canal de notificaciones de removido")
    @app_commands.describe(canal="Canal donde se avisara cuando alguien quite la vanity")
    async def vanity_remove_channel(
        self, interaction: discord.Interaction, canal: discord.TextChannel | None = None
    ):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        set_vanity_settings(interaction.guild.id, remove_channel_id=canal.id if canal else None)
        cog._refresh_guild_cache(interaction.guild.id)
        message = (
            f"Canal de notificaciones (removido) configurado: {canal.mention}"
            if canal
            else "Canal de notificaciones (removido) desactivado."
        )
        await self._send(interaction, message, ephemeral=False)

    @vanity.command(name="removenotify", description="Activa o desactiva las notificaciones de removido")
    async def vanity_remove_notify(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        settings = cog._get_settings_cached(interaction.guild.id)
        new_value = 0 if settings.get("remove_enabled", 0) else 1
        set_vanity_settings(interaction.guild.id, remove_enabled=new_value)
        cog._refresh_guild_cache(interaction.guild.id)
        message = (
            "Notificaciones de removido activadas."
            if new_value
            else "Notificaciones de removido desactivadas."
        )
        await self._send(interaction, message, ephemeral=False)

    @vanity.command(name="list", description="Lista usuarios con vanity en su estado")
    async def vanity_list(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        await interaction.response.defer(ephemeral=True)
        vanity_codes = cog._get_codes_cached(interaction.guild.id)
        if not vanity_codes:
            await interaction.followup.send("No hay vanitys configuradas.", ephemeral=True)
            return

        results = {item["vanity_code"]: [] for item in vanity_codes}
        for member in interaction.guild.members:
            if member.bot:
                continue
            for item in vanity_codes:
                if cog.check_vanity(member, item["vanity_code"]):
                    results[item["vanity_code"]].append(member)
                    break

        embed = discord.Embed(title="Usuarios con Vanity", color=0x5865F2)
        total = 0
        for vanity, members in results.items():
            total += len(members)
            member_list = ", ".join(member.mention for member in members[:15]) if members else "*Ninguno*"
            if len(members) > 15:
                member_list += f" y {len(members) - 15} mas..."
            embed.add_field(name=f"{vanity} ({len(members)})", value=member_list, inline=False)

        embed.set_footer(text=f"Total: {total} usuarios")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @vanity.command(name="reset", description="Borra toda la configuracion de vanity")
    async def vanity_reset(self, interaction: discord.Interaction):
        cog = await self._ensure_ready(interaction)
        if cog is None:
            return

        view = ConfirmResetView(interaction.user.id)
        embed = discord.Embed(
            title="Estas seguro?",
            description="Esto eliminara todas las vanitys y su configuracion.",
            color=0xFEE75C,
        )
        await self._send(interaction, embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            await interaction.followup.send("Operacion cancelada.", ephemeral=True)
            return

        delete_all_vanity(interaction.guild.id)
        cog._invalidate_guild_cache(interaction.guild.id)
        await interaction.followup.send("Toda la configuracion de vanity ha sido borrada.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VanitySlashCog(bot))
