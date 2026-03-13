# modules/boost_roles_cog.py
# ────────────────────────────────────────────────────────────────────────────
#  BoostRolesCog  –  módulo completo (corregido)
#  • /boostrole add      – asigna o actualiza un rol (True / False obligatorio)
#  • /boostrole remove   – quita el rol a un usuario y borra la entrada
#  • /boostrole setlog   – define el canal de logs
#  • /boostrole list     – lista la configuración con paginación (◀️ / ▶️)
#  • Listener & auditoría – retira roles al perder boost y revisa cada 12 h
#  • Todos los embeds llevan footer con el ejecutor o “Sistema automático”
# ────────────────────────────────────────────────────────────────────────────
import math
import discord
from discord import app_commands
from discord.ext import commands, tasks

import database as db

ENTRIES_PER_PAGE = 10  # roles por página en /boostrole list


# ╭────────────────────────── Paginated View ───────────────────────────╮
class PaginationView(discord.ui.View):
    """Botones ◀️ / ▶️ para navegar páginas de /boostrole list."""
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.index = 0
        self.message: discord.Message | None = None
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= len(self.embeds) - 1

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, _):
        self.index -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _):
        self.index += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)
# ╰──────────────────────────────────────────────────────────────────────────╯


class BoostRolesCog(commands.Cog):
    """Gestión de roles exclusivos para boosters."""

    # ───────────────── Ciclo de vida ─────────────────
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.audit_boost_roles.start()  # loop periódico

    def cog_unload(self):
        self.audit_boost_roles.cancel()

    # ─────────────── Slash command group ─────────────
    boostrole = app_commands.Group(
        name="boostrole",
        description="Comandos para roles (ligados o no) a Boost.",
    )

    # ╭──────────────────── /boostrole add ───────────────────╮
    @boostrole.command(name="add", description="Asigna o actualiza un rol.")
    @app_commands.describe(
        user="Usuario que recibirá el rol",
        role="Rol a asignar o actualizar",
        linked_to_boost="True → se quita al dejar de boostear",
    )
    async def add_role(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
        linked_to_boost: bool,
    ):
        # Permisos básicos
        if not interaction.user.guild_permissions.manage_roles:
            return await self._send_error(
                interaction, "⛔ Permiso insuficiente",
                "Necesitas **Gestionar roles** para usar este comando."
            )

        # Chequeo de jerarquía
        if role >= interaction.guild.me.top_role:
            return await self._send_error(
                interaction, "⛔ Rol demasiado alto",
                "Ese rol está por encima de mi rol; no puedo asignarlo."
            )

        existing = db.get_boost_role(interaction.guild.id, role.id)
        prev_state = bool(existing["linked_to_boost"]) if existing else None
        user_has = role in user.roles

        # Usuario debe ser booster si se liga
        if linked_to_boost and user.premium_since is None:
            return await self._send_error(
                interaction, "⚠️ Usuario no es booster",
                f"{user.mention} no está boosteando el servidor."
            )

        # ① Duplicado
        if user_has and prev_state == linked_to_boost:
            embed = discord.Embed(
                title="ℹ️ Rol ya asignado",
                description=(
                    f"{user.mention} ya posee {role.mention}\n"
                    f"Estado: {'🔒 Ligado a Boost' if linked_to_boost else '🔓 Normal'}"
                ),
                color=discord.Color.orange(),
            )
            embed = self._with_footer(embed, interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=False)
            await self._send_log(interaction.guild, embed.copy())
            return

        # ② Solo cambia el estado Boost
        if user_has and prev_state is not None and prev_state != linked_to_boost:
            db.add_boost_role(interaction.guild.id, role.id, linked_to_boost)
            embed = discord.Embed(
                title="🔄 Rol actualizado",
                description=(
                    f"{role.mention} para {user.mention} cambió de "
                    f"{'🔒' if prev_state else '🔓'} ➜ "
                    f"{'🔒 Ligado a Boost' if linked_to_boost else '🔓 Normal'}."
                ),
                color=discord.Color.gold(),
            )
            embed = self._with_footer(embed, interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=False)
            await self._send_log(interaction.guild, embed.copy())
            return

        # ③ Nueva asignación
        await user.add_roles(role, reason="BoostRoles | add")
        db.add_boost_role(interaction.guild.id, role.id, linked_to_boost)

        embed = discord.Embed(
            title="✅ Rol asignado",
            description=(
                f"{role.mention} asignado a {user.mention}\n"
                f"{'*(Ligado a Boost – se retirará si deja de boostear)*' if linked_to_boost else ''}"
            ),
            color=discord.Color.green(),
        )
        embed = self._with_footer(embed, interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)
        await self._send_log(interaction.guild, embed.copy())
    # ╰────────────────────────────────────────────────────────╯

    # ╭─────────────────── /boostrole remove ─────────────────╮
    @boostrole.command(name="remove",
                       description="Retira el rol a un usuario y borra su registro.")
    @app_commands.describe(
        user="Miembro al que se retirará el rol",
        role="Rol a eliminar de la configuración",
    )
    async def remove_role(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        role: discord.Role,
    ):
        if not interaction.user.guild_permissions.manage_roles:
            return await self._send_error(
                interaction, "⛔ Permiso insuficiente",
                "Necesitas **Gestionar roles** para usar este comando."
            )

        # Existe en configuración?
        if not db.get_boost_role(interaction.guild.id, role.id):
            return await self._send_error(
                interaction, "ℹ️ Rol no registrado",
                f"{role.mention} no forma parte de la configuración.",
                color=discord.Color.orange(), ephemeral=True
            )

        # Usuario realmente tiene el rol?
        if role not in user.roles:
            return await self._send_error(
                interaction, "ℹ️ El usuario no tiene ese rol",
                f"{user.mention} no posee {role.mention}.",
                color=discord.Color.orange(), ephemeral=True
            )

        await user.remove_roles(role, reason="BoostRoles | remove")
        db.delete_boost_role(interaction.guild.id, role.id)

        embed = discord.Embed(
            title="🗑️ Rol eliminado",
            description=(
                f"{role.mention} se quitó a {user.mention} "
                "y se eliminó de la configuración."
            ),
            color=discord.Color.red(),
        )
        embed = self._with_footer(embed, interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)
        await self._send_log(interaction.guild, embed.copy())
    # ╰────────────────────────────────────────────────────────╯

    # ╭────────────────── /boostrole setlog ──────────────────╮
    @boostrole.command(name="setlog", description="Define el canal de logs.")
    async def set_log_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        if not interaction.user.guild_permissions.manage_guild:
            return await self._send_error(
                interaction, "⛔ Permiso insuficiente",
                "Necesitas **Gestionar servidor** para usar este comando."
            )

        db.set_boost_log_channel(interaction.guild.id, channel.id)

        embed = discord.Embed(
            title="✅ Canal de logs establecido",
            description=f"Los eventos del módulo irán a {channel.mention}.",
            color=discord.Color.green(),
        )
        embed = self._with_footer(embed, interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    # ╰────────────────────────────────────────────────────────╯

    # ╭────────────────── /boostrole list ────────────────────╮
    @boostrole.command(name="list", description="Lista los roles configurados.")
    async def list_roles(self, interaction: discord.Interaction):
        rows = db.get_boost_roles_for_guild(interaction.guild.id)
        if not rows:
            return await self._send_error(
                interaction, "ℹ️ Sin roles registrados",
                "No se han configurado roles en este servidor.",
                color=discord.Color.blurple(), ephemeral=True
            )

        total_pages = math.ceil(len(rows) / ENTRIES_PER_PAGE)
        embeds: list[discord.Embed] = []

        for page in range(total_pages):
            start = page * ENTRIES_PER_PAGE
            chunk = rows[start:start + ENTRIES_PER_PAGE]

            embed = discord.Embed(
                title=f"📋 Roles configurados (página {page+1}/{total_pages})",
                color=discord.Color.blurple(),
            )

            for row in chunk:
                role = interaction.guild.get_role(row["role_id"])
                if not role:
                    continue
                estado = "🔒 Ligado a Boost" if row["linked_to_boost"] else "🔓 Normal"
                miembros = ", ".join(m.mention for m in role.members) or "Sin asignar"
                embed.add_field(
                    name=f"{role.name} ― ID: {role.id}",
                    value=f"{estado}\n**Miembros:** {miembros}",
                    inline=False,
                )

            embeds.append(self._with_footer(embed, interaction.user))

        if len(embeds) == 1:
            await interaction.response.send_message(embed=embeds[0], ephemeral=True)
        else:
            view = PaginationView(embeds)
            msg = await interaction.response.send_message(
                embed=embeds[0], view=view, ephemeral=True
            )
            view.message = await msg.original_response()
    # ╰────────────────────────────────────────────────────────╯

    # ───────────── Listener: pérdida de boost ───────────────
    @commands.Cog.listener("on_member_update")
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since and after.premium_since is None:
            linked = db.get_linked_roles_for_guild(after.guild.id)
            to_remove = [r for r in after.roles if r.id in linked]
            if to_remove:
                await after.remove_roles(*to_remove, reason="Dejó de boostear")
                embed = discord.Embed(
                    title="⚠️ Booster perdido",
                    description=(
                        f"{after.mention} dejó de boostear.\n"
                        f"Roles retirados: {', '.join(r.mention for r in to_remove)}"
                    ),
                    color=discord.Color.red(),
                )
                embed = self._with_footer(embed, None)
                await self._send_log(after.guild, embed)

    # ─────────────── Auditoría periódica ────────────────
    @tasks.loop(hours=12)
    async def audit_boost_roles(self):
        """Revisa cada 12 h que los 'boost-linked' sigan en boosters."""
        for guild in self.bot.guilds:
            linked = db.get_linked_roles_for_guild(guild.id)
            if not linked:
                continue
            for role_id in linked:
                role = guild.get_role(role_id)
                if not role:
                    continue
                for member in role.members:
                    if member.premium_since is None:
                        await member.remove_roles(
                            role, reason="Auditoría Boost: dejó de boostear"
                        )
                        embed = discord.Embed(
                            title="🚫 Auditoría: rol retirado",
                            description=f"Se retiró {role.mention} de {member.mention}.",
                            color=discord.Color.red(),
                        )
                        embed = self._with_footer(embed, None)
                        await self._send_log(guild, embed)

    @audit_boost_roles.before_loop
    async def before_audit(self):
        await self.bot.wait_until_ready()

    # ─────────────── Helpers embeds / logs ────────────────
    def _with_footer(self, embed: discord.Embed, user: discord.User | None):
        embed.set_footer(
            text=f"Solicitado por {user.display_name}" if user else "Sistema automático",
            icon_url=user.display_avatar.url if user else None
        )
        return embed

    async def _send_error(
        self, interaction: discord.Interaction, title: str, description: str,
        *, color: discord.Color = discord.Color.red(), ephemeral: bool = True
    ):
        embed = discord.Embed(title=title, description=description, color=color)
        embed = self._with_footer(embed, interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed):
        if not embed.footer.text:
            embed = self._with_footer(embed, None)
        data = db.get_boost_log_channel(guild.id)
        if data:
            channel = guild.get_channel(data["channel_id"])
            if channel:
                await channel.send(embed=embed)

# ─────────────── setup para load_extension ────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(BoostRolesCog(bot))
