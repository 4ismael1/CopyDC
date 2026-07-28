"""
🏷️ Clan Tag Module
Da roles a usuarios que tengan el tag del clan del servidor
"""

import asyncio
import logging
import re
import time

import discord
from discord import ui
from discord.ext import commands

from command_utils import RestrictedView
from database import delete_clantag_settings, get_clantag_settings, set_clantag_settings, setup_clantag_table

log = logging.getLogger("bot")


class EmbedEditorModal(ui.Modal, title="✏️ Editar Embed"):
    """Modal para editar el embed."""

    def __init__(self, embed_type: str, current_title: str, current_desc: str, current_color: int):
        super().__init__()
        self.embed_type = embed_type

        self.title_input = ui.TextInput(
            label="Título",
            default=current_title,
            max_length=256,
            required=True,
            placeholder="Ejemplo: ¡Gracias por representarnos!",
        )
        self.desc_input = ui.TextInput(
            label="Descripción",
            style=discord.TextStyle.paragraph,
            default=current_desc,
            max_length=2000,
            required=True,
            placeholder="Variables: {user} {role} {tag} {server}",
        )
        self.color_input = ui.TextInput(
            label="Color HEX (sin #)",
            default=format(current_color, "x"),
            max_length=6,
            required=True,
            placeholder="57F287=verde, ED4245=rojo, 5865F2=azul",
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


class ClanTagCog(commands.Cog):
    """Sistema de roles por clan tag del servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        setup_clantag_table()
        # Cache para evitar spam de peticiones
        self._clan_cache = {}
        self._clan_cache_ttl_sec = 60.0
        # Anti-duplicados: {(guild_id, user_id): {'action': 'add'/'remove', 'time': float}}
        self._recent_actions = {}
        self._settings_cache = {}
        self._settings_cache_ttl_sec = 30.0

    def _invalidate_settings_cache(self, guild_id: int):
        self._settings_cache.pop(guild_id, None)

    def _get_settings_cached(self, guild_id: int) -> dict:
        now = time.monotonic()
        cached = self._settings_cache.get(guild_id)
        if cached and now < cached["expires_at"]:
            return dict(cached["value"])

        settings = get_clantag_settings(guild_id) or {}
        self._settings_cache[guild_id] = {
            "expires_at": now + self._settings_cache_ttl_sec,
            "value": settings,
        }
        return dict(settings)

    def _refresh_settings_cache(self, guild_id: int):
        self._invalidate_settings_cache(guild_id)
        self._get_settings_cached(guild_id)

    @staticmethod
    def _extract_primary_guild(user: discord.User | discord.Member) -> dict | None:
        primary_guild = getattr(user, "primary_guild", None)
        if primary_guild is None or primary_guild.identity_enabled is False:
            return None

        guild_id = getattr(primary_guild, "id", None)
        tag = getattr(primary_guild, "tag", None)
        if guild_id is None or not tag:
            return None

        return {
            "tag": tag,
            "badge": getattr(primary_guild, "badge", None),
            "guild_id": int(guild_id),
        }

    async def fetch_user_clan(self, user_id: int) -> dict | None:
        """Obtiene el servidor principal mediante la API soportada por discord.py."""
        cached = self._clan_cache.get(user_id)
        now = time.monotonic()
        if cached and now < cached["expires_at"]:
            return cached["value"]

        user = self.bot.get_user(user_id)
        try:
            if user is None:
                user = await self.bot.fetch_user(user_id)
            value = self._extract_primary_guild(user)
        except (discord.NotFound, discord.Forbidden):
            value = None
        except discord.HTTPException as exc:
            log.warning("No pude consultar primary_guild para user=%s: %s", user_id, exc)
            return None

        self._clan_cache[user_id] = {
            "value": value,
            "expires_at": now + self._clan_cache_ttl_sec,
        }
        return value

    def convert_emojis(self, text: str, guild: discord.Guild) -> str:
        """Convierte :emoji: al formato <:emoji:id> automáticamente."""
        pattern = r":([a-zA-Z0-9_]+):"

        def replace_emoji(match):
            emoji_name = match.group(1)
            for emoji in guild.emojis:
                if emoji.name.lower() == emoji_name.lower():
                    if emoji.animated:
                        return f"<a:{emoji.name}:{emoji.id}>"
                    else:
                        return f"<:{emoji.name}:{emoji.id}>"
            return match.group(0)

        return re.sub(pattern, replace_emoji, text)

    async def get_guild_clan_tag(self, guild: discord.Guild) -> str | None:
        """Obtiene el clan tag del servidor buscando en los miembros via API."""
        for member in guild.members:
            if member.bot:
                continue
            clan_data = self._extract_primary_guild(member)
            if clan_data and clan_data.get("guild_id") == guild.id:
                return clan_data.get("tag")
        return None

    async def member_has_server_clan(self, member: discord.Member, guild_id: int) -> tuple[bool, str | None]:
        """Verifica si el miembro tiene el clan del servidor específico via API.
        Retorna (tiene_clan, tag)"""
        clan_data = self._extract_primary_guild(member)
        if clan_data is None:
            clan_data = await self.fetch_user_clan(member.id)
        if clan_data and clan_data.get("guild_id") == guild_id:
            return True, clan_data.get("tag")
        return False, None

    def build_embed(
        self, settings: dict, member: discord.Member, tag: str, role: discord.Role, is_add: bool
    ) -> discord.Embed:
        """Construye el embed personalizado."""
        if is_add:
            title = settings.get("embed_title", "🏷️ ¡Gracias por representarnos!")
            desc = settings.get("embed_description", "{user} ahora tiene el tag **{tag}** y recibió {role}")
            color = settings.get("embed_color", 0x57F287)
        else:
            title = settings.get("remove_title", "😢 Tag removido")
            desc = settings.get("remove_description", "{user} ya no tiene el tag **{tag}**")
            color = settings.get("remove_color", 0xED4245)

        # Reemplazar variables
        desc = desc.replace("{user}", member.mention)
        desc = desc.replace("{role}", role.mention if role else "rol")
        desc = desc.replace("{tag}", tag)
        desc = desc.replace("{server}", member.guild.name)

        # Convertir :emoji: a formato completo
        title = self.convert_emojis(title, member.guild)
        desc = self.convert_emojis(desc, member.guild)

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        return embed

    # ══════════════════════════════════════════════════════════
    # EVENTO: Detecta cambios de clan tag
    # ══════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Detecta cuando un miembro cambia su clan tag."""
        if after.bot:
            return

        settings = await asyncio.to_thread(self._get_settings_cached, after.guild.id)
        if not settings or not settings.get("role_id"):
            return

        role_id = settings.get("role_id")
        role = after.guild.get_role(role_id)
        if not role:
            return

        # Obtener clan actual via API HTTP
        has_clan, clan_tag = await self.member_has_server_clan(after, after.guild.id)
        has_role = role in after.roles

        # Anti-duplicados: verificar si ya procesamos esta acción recientemente
        key = (after.guild.id, after.id)
        action = "add" if has_clan else "remove"
        now = time.time()

        recent = self._recent_actions.get(key)
        if recent and recent["action"] == action and (now - recent["time"]) < 3:
            return  # Ignorar duplicado (menos de 3 segundos)

        # Si tiene el clan y no tiene el rol → dar rol
        if has_clan and not has_role:
            try:
                self._recent_actions[key] = {"action": "add", "time": now}
                await after.add_roles(role, reason=f"Clan Tag: {clan_tag}")

                # Enviar embed
                channel_id = settings.get("channel_id")
                if channel_id:
                    channel = after.guild.get_channel(channel_id)
                    if channel:
                        embed = self.build_embed(settings, after, clan_tag, role, is_add=True)
                        await channel.send(embed=embed)
            except discord.Forbidden:
                log.warning(
                    "No pude asignar el rol de clan tag en guild=%s member=%s.",
                    after.guild.id,
                    after.id,
                )
            except discord.HTTPException as exc:
                log.warning(
                    "Discord rechazó la asignación de clan tag en guild=%s member=%s: %s",
                    after.guild.id,
                    after.id,
                    exc,
                )

        # Si no tiene el clan y tiene el rol → quitar rol
        elif not has_clan and has_role:
            try:
                self._recent_actions[key] = {"action": "remove", "time": now}
                await after.remove_roles(role, reason="Clan Tag removido")

                # Enviar embed de removido si está habilitado
                if settings.get("remove_enabled"):
                    remove_channel_id = settings.get("remove_channel_id")
                    if remove_channel_id:
                        remove_channel = after.guild.get_channel(remove_channel_id)
                        if remove_channel:
                            embed = self.build_embed(settings, after, "TAG", role, is_add=False)
                            await remove_channel.send(embed=embed)
            except discord.Forbidden:
                log.warning(
                    "No pude retirar el rol de clan tag en guild=%s member=%s.",
                    after.guild.id,
                    after.id,
                )
            except discord.HTTPException as exc:
                log.warning(
                    "Discord rechazó el retiro de clan tag en guild=%s member=%s: %s",
                    after.guild.id,
                    after.id,
                    exc,
                )

    # ══════════════════════════════════════════════════════════
    # COMANDOS PRINCIPALES
    # ══════════════════════════════════════════════════════════

    @commands.group(name="clantag", aliases=["tag", "clan"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def clantag(self, ctx: commands.Context):
        """Muestra el panel de configuración de clan tag."""
        settings = self._get_settings_cached(ctx.guild.id)

        # Detectar clan tag del servidor (async)
        clan_tag = await self.get_guild_clan_tag(ctx.guild)

        embed = discord.Embed(title="🏷️ Sistema de Clan Tag", color=0x5865F2)

        # Tag del servidor
        embed.add_field(
            name="🏷️ Tag del Servidor",
            value=f"`{clan_tag}`" if clan_tag else "🔄 Usa `c!clantag list` para detectar",
            inline=True,
        )

        # Rol configurado
        role = ctx.guild.get_role(settings.get("role_id")) if settings.get("role_id") else None
        embed.add_field(name="🎭 Rol", value=role.mention if role else "`No configurado`", inline=True)

        # Canal de añadir
        channel = ctx.guild.get_channel(settings.get("channel_id")) if settings.get("channel_id") else None
        embed.add_field(
            name="📢 Canal (Añadir)", value=channel.mention if channel else "`No configurado`", inline=True
        )

        # Canal de removido
        remove_channel = (
            ctx.guild.get_channel(settings.get("remove_channel_id"))
            if settings.get("remove_channel_id")
            else None
        )
        remove_enabled = settings.get("remove_enabled", 0)
        remove_status = f"{remove_channel.mention}" if remove_channel else "`No configurado`"
        if not remove_enabled:
            remove_status = f"~~{remove_status}~~ (desactivado)"
        embed.add_field(name="📤 Canal (Removido)", value=remove_status, inline=True)

        # Comandos
        embed.add_field(
            name="⚙️ Comandos",
            value=(
                "`c!clantag role @rol` — Configurar rol\n"
                "`c!clantag channel #canal` — Canal (añadir)\n"
                "`c!clantag removechannel #canal` — Canal (removido)\n"
                "`c!clantag removenotify` — Toggle removido\n"
                "`c!clantag list` — Ver usuarios\n"
                "`c!clantag embed` — Personalizar embeds\n"
                "`c!clantag reset` — Borrar todo"
            ),
            inline=False,
        )

        if not clan_tag:
            embed.set_footer(text="⚠️ No se detectó ningún miembro con el clan de este servidor")

        await ctx.send(embed=embed)

    @clantag.command(name="role", aliases=["rol"])
    @commands.has_permissions(administrator=True)
    async def clantag_role(self, ctx: commands.Context, rol: discord.Role):
        """Configura el rol para usuarios con el clan tag."""
        me = ctx.guild.me
        if rol.is_default() or rol.managed or (me is not None and rol >= me.top_role):
            await ctx.send(
                "❌ No puedo administrar ese rol. Usa un rol normal situado debajo del rol del bot."
            )
            return

        set_clantag_settings(ctx.guild.id, role_id=rol.id)
        self._refresh_settings_cache(ctx.guild.id)

        embed = discord.Embed(
            title="✅ Rol Configurado",
            description=f"Los usuarios con el clan tag del servidor recibirán {rol.mention}",
            color=0x57F287,
        )
        await ctx.send(embed=embed)

    @clantag.command(name="channel", aliases=["canal"])
    @commands.has_permissions(administrator=True)
    async def clantag_channel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Configura el canal de notificaciones (cuando añaden tag)."""
        set_clantag_settings(ctx.guild.id, channel_id=canal.id if canal else None)
        self._refresh_settings_cache(ctx.guild.id)

        if canal:
            await ctx.send(f"✅ Canal de notificaciones (añadir) configurado: {canal.mention}")
        else:
            await ctx.send("✅ Canal de notificaciones (añadir) desactivado.")

    @clantag.command(name="removechannel", aliases=["removecanal"])
    @commands.has_permissions(administrator=True)
    async def clantag_remove_channel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Configura el canal para notificaciones de removido."""
        set_clantag_settings(ctx.guild.id, remove_channel_id=canal.id if canal else None)
        self._refresh_settings_cache(ctx.guild.id)

        if canal:
            await ctx.send(f"✅ Canal de notificaciones (removido) configurado: {canal.mention}")
        else:
            await ctx.send("✅ Canal de notificaciones (removido) desactivado.")

    @clantag.command(name="removenotify", aliases=["removenotificacion"])
    @commands.has_permissions(administrator=True)
    async def clantag_remove_notify(self, ctx: commands.Context):
        """Activa/desactiva notificaciones cuando quitan el tag."""
        settings = self._get_settings_cached(ctx.guild.id)
        current = settings.get("remove_enabled", 0)
        new_value = 0 if current else 1

        set_clantag_settings(ctx.guild.id, remove_enabled=new_value)
        self._refresh_settings_cache(ctx.guild.id)

        if new_value:
            await ctx.send("✅ Notificaciones de removido **activadas**.")
        else:
            await ctx.send("✅ Notificaciones de removido **desactivadas**.")

    @clantag.command(name="list", aliases=["users", "lista"])
    @commands.has_permissions(administrator=True)
    async def clantag_list(self, ctx: commands.Context):
        """Muestra usuarios con el clan tag via API."""
        msg = await ctx.send("🔄 Buscando usuarios con el clan tag del servidor...")

        users_with_tag = []
        clan_tag = None
        checked = 0

        for member in ctx.guild.members:
            if member.bot:
                continue
            checked += 1

            # Actualizar mensaje cada 50 usuarios
            if checked % 50 == 0:
                await msg.edit(content=f"🔄 Verificando... ({checked}/{len(ctx.guild.members)})")

            has_clan, tag = await self.member_has_server_clan(member, ctx.guild.id)
            if has_clan:
                users_with_tag.append(member)
                if not clan_tag:
                    clan_tag = tag

        if not users_with_tag:
            embed = discord.Embed(
                title="🏷️ Usuarios con el Clan Tag",
                description="No hay usuarios con el clan tag de este servidor.",
                color=0xFEE75C,
            )
            await msg.edit(content=None, embed=embed)
            return

        # Crear embed con lista
        embed = discord.Embed(title=f"🏷️ Usuarios con tag `{clan_tag}`", color=0x5865F2)

        # Mostrar máximo 20 usuarios
        user_list = users_with_tag[:20]
        user_text = "\n".join(f"• {m.mention}" for m in user_list)

        if len(users_with_tag) > 20:
            user_text += f"\n... y {len(users_with_tag) - 20} más"

        embed.description = user_text
        embed.set_footer(text=f"Total: {len(users_with_tag)} usuarios")
        await msg.edit(content=None, embed=embed)

    @clantag.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def clantag_embed(self, ctx: commands.Context):
        """Personaliza los embeds de notificación."""
        settings = self._get_settings_cached(ctx.guild.id)

        class EmbedButtons(RestrictedView):
            def __init__(self, cog, settings, author_id: int):
                super().__init__(
                    author_id=author_id,
                    timeout=120,
                    required_permissions=("administrator",),
                )
                self.cog = cog
                self.settings = settings

            @ui.button(label="✅ Embed de Añadido", style=discord.ButtonStyle.success)
            async def edit_add(self, interaction: discord.Interaction, button: ui.Button):
                modal = EmbedEditorModal(
                    "add",
                    self.settings.get("embed_title", "🏷️ ¡Gracias por representarnos!"),
                    self.settings.get(
                        "embed_description", "{user} ahora tiene el tag **{tag}** y recibió {role}"
                    ),
                    self.settings.get("embed_color", 0x57F287),
                )
                await interaction.response.send_modal(modal)
                await modal.wait()

                if modal.new_title:
                    set_clantag_settings(
                        ctx.guild.id,
                        embed_title=modal.new_title,
                        embed_description=modal.new_desc,
                        embed_color=modal.new_color,
                    )
                    self.cog._refresh_settings_cache(ctx.guild.id)
                    self.settings = self.cog._get_settings_cached(ctx.guild.id)
                    await interaction.followup.send("✅ Embed de añadido actualizado.", ephemeral=True)

            @ui.button(label="❌ Embed de Removido", style=discord.ButtonStyle.danger)
            async def edit_remove(self, interaction: discord.Interaction, button: ui.Button):
                modal = EmbedEditorModal(
                    "remove",
                    self.settings.get("remove_title", "😢 Tag removido"),
                    self.settings.get("remove_description", "{user} ya no tiene el tag **{tag}**"),
                    self.settings.get("remove_color", 0xED4245),
                )
                await interaction.response.send_modal(modal)
                await modal.wait()

                if modal.new_title:
                    set_clantag_settings(
                        ctx.guild.id,
                        remove_title=modal.new_title,
                        remove_description=modal.new_desc,
                        remove_color=modal.new_color,
                    )
                    self.cog._refresh_settings_cache(ctx.guild.id)
                    self.settings = self.cog._get_settings_cached(ctx.guild.id)
                    await interaction.followup.send("✅ Embed de removido actualizado.", ephemeral=True)

            @ui.button(label="👁️ Vista Previa", style=discord.ButtonStyle.secondary)
            async def preview(self, interaction: discord.Interaction, button: ui.Button):
                fake_role = ctx.guild.roles[0]
                clan_tag = await self.cog.get_guild_clan_tag(ctx.guild) or "TAG"

                embed_add = self.cog.build_embed(self.settings, ctx.author, clan_tag, fake_role, is_add=True)
                embed_remove = self.cog.build_embed(
                    self.settings, ctx.author, clan_tag, fake_role, is_add=False
                )

                await interaction.response.send_message(
                    "**Vista previa de los embeds:**", embeds=[embed_add, embed_remove], ephemeral=True
                )

        embed = discord.Embed(
            title="✏️ Editor de Embeds",
            description=(
                "Personaliza los mensajes de notificación.\n\n"
                "**Variables:**\n"
                "`{user}` → Mención del usuario\n"
                "`{role}` → Mención del rol\n"
                "`{tag}` → Tag del clan\n"
                "`{server}` → Nombre del servidor\n\n"
                "**Formato de texto:**\n"
                "`**texto**` → **negrita**\n"
                "`*texto*` → *cursiva*\n"
                "`__texto__` → subrayado\n\n"
                "**Emojis del servidor:**\n"
                "Solo escribe `:nombre:` y se convierte automático"
            ),
            color=0x5865F2,
        )

        view = EmbedButtons(self, settings, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @clantag.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def clantag_reset(self, ctx: commands.Context):
        """Elimina toda la configuración de clan tag."""
        embed = discord.Embed(
            title="⚠️ ¿Estás seguro?",
            description="Esto eliminará **toda** la configuración de clan tag.",
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
            delete_clantag_settings(ctx.guild.id)
            self._invalidate_settings_cache(ctx.guild.id)
            embed.title = "✅ Configuración Eliminada"
            embed.description = "Toda la configuración de clan tag ha sido borrada."
            embed.color = 0x57F287
        else:
            embed.title = "❌ Cancelado"
            embed.description = "No se eliminó nada."
            embed.color = 0xED4245

        await msg.edit(embed=embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(ClanTagCog(bot))
