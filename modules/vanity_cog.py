"""
🔗 Vanity Role Module
Da roles a usuarios que tengan vanitys en su estado personalizado
"""
import discord
from discord.ext import commands
from discord import ui
import re
from database import (
    setup_vanity_table, get_vanity_settings, set_vanity_settings,
    get_vanity_codes, add_vanity_code, remove_vanity_code, delete_all_vanity
)


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
            placeholder="Ejemplo: ¡Gracias por representarnos!"
        )
        self.desc_input = ui.TextInput(
            label="Descripción",
            style=discord.TextStyle.paragraph,
            default=current_desc,
            max_length=2000,
            required=True,
            placeholder="Variables: {user} {role} {vanity} {server}"
        )
        self.color_input = ui.TextInput(
            label="Color HEX (sin #)",
            default=format(current_color, 'x'),
            max_length=6,
            required=True,
            placeholder="57F287=verde, ED4245=rojo, 5865F2=azul"
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
        except:
            self.new_color = 0x5865F2
        
        self.new_title = self.title_input.value
        self.new_desc = self.desc_input.value
        await interaction.response.defer()


class VanityCog(commands.Cog):
    """Sistema de roles por vanity URL en estado."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        setup_vanity_table()
    
    def convert_emojis(self, text: str, guild: discord.Guild) -> str:
        """Convierte :emoji: al formato <:emoji:id> automáticamente."""
        # Busca patrones :nombre: que no sean ya formato completo
        pattern = r':([a-zA-Z0-9_]+):'
        
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
            if isinstance(activity, discord.CustomActivity) and activity.name:
                if vanity_code.lower() in activity.name.lower():
                    return True
        return False
    
    def get_matching_vanity(self, member: discord.Member, vanity_codes: list) -> tuple:
        """Retorna (vanity_code, role_id) si el usuario tiene alguna vanity."""
        for vc in vanity_codes:
            if self.check_vanity(member, vc['vanity_code']):
                return vc['vanity_code'], vc['role_id']
        return None, None
    
    def build_embed(self, settings: dict, member: discord.Member, vanity: str, role: discord.Role, is_add: bool) -> discord.Embed:
        """Construye el embed personalizado."""
        if is_add:
            title = settings.get('embed_title', '✨ ¡Gracias por representarnos!')
            desc = settings.get('embed_description', '{user} ahora tiene **{vanity}** en su estado y recibió {role}')
            color = settings.get('embed_color', 0x57F287)
        else:
            title = settings.get('remove_title', '👋 Vanity Removida')
            desc = settings.get('remove_description', '{user} quitó **{vanity}** de su estado')
            color = settings.get('remove_color', 0xED4245)
        
        # Reemplazar variables
        desc = desc.replace('{user}', member.mention)
        desc = desc.replace('{role}', role.mention if role else 'rol')
        desc = desc.replace('{vanity}', vanity)
        desc = desc.replace('{server}', member.guild.name)
        
        # Convertir :emoji: a formato completo
        title = self.convert_emojis(title, member.guild)
        desc = self.convert_emojis(desc, member.guild)
        
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        
        if settings.get('embed_image'):
            embed.set_image(url=settings['embed_image'])
        
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
        
        vanity_codes = get_vanity_codes(after.guild.id)
        if not vanity_codes:
            return
        
        settings = get_vanity_settings(after.guild.id) or {}
        channel_id = settings.get('channel_id')
        channel = after.guild.get_channel(channel_id) if channel_id else None
        
        # Ver qué vanity tiene (si alguna)
        matched_vanity, matched_role_id = self.get_matching_vanity(after, vanity_codes)
        
        # Roles de vanity que tiene actualmente
        vanity_role_ids = {vc['role_id'] for vc in vanity_codes}
        current_vanity_roles = [r for r in after.roles if r.id in vanity_role_ids]
        
        if matched_vanity:
            # Tiene una vanity → asegurar que tenga el rol correcto
            role = after.guild.get_role(matched_role_id)
            if role and role not in after.roles:
                try:
                    # Quitar otros roles de vanity si tiene
                    for old_role in current_vanity_roles:
                        if old_role.id != matched_role_id:
                            await after.remove_roles(old_role, reason="Cambió de vanity")
                    
                    await after.add_roles(role, reason=f"Vanity: {matched_vanity}")
                    
                    if channel:
                        embed = self.build_embed(settings, after, matched_vanity, role, is_add=True)
                        await channel.send(embed=embed)
                except discord.Forbidden:
                    pass
        else:
            # No tiene ninguna vanity → quitar roles de vanity
            for role in current_vanity_roles:
                try:
                    vanity_for_role = next((vc['vanity_code'] for vc in vanity_codes if vc['role_id'] == role.id), "vanity")
                    await after.remove_roles(role, reason="Vanity removida")
                    
                    # Enviar embed de removido si está habilitado
                    if settings.get('remove_enabled'):
                        remove_channel_id = settings.get('remove_channel_id')
                        remove_channel = after.guild.get_channel(remove_channel_id) if remove_channel_id else None
                        if remove_channel:
                            embed = self.build_embed(settings, after, vanity_for_role, role, is_add=False)
                            await remove_channel.send(embed=embed)
                except discord.Forbidden:
                    pass
    
    # ══════════════════════════════════════════════════════════
    # COMANDOS PRINCIPALES
    # ══════════════════════════════════════════════════════════
    
    @commands.group(name="vanity", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def vanity(self, ctx: commands.Context):
        """Muestra el panel de configuración de vanity."""
        settings = get_vanity_settings(ctx.guild.id) or {}
        vanity_codes = get_vanity_codes(ctx.guild.id)
        
        embed = discord.Embed(
            title="🔗 Sistema de Vanity Roles",
            color=0x5865F2
        )
        
        # Canal de añadir
        channel = ctx.guild.get_channel(settings.get('channel_id')) if settings.get('channel_id') else None
        embed.add_field(
            name="📢 Canal (Añadir)",
            value=channel.mention if channel else "`No configurado`",
            inline=True
        )
        
        # Canal de removido
        remove_channel = ctx.guild.get_channel(settings.get('remove_channel_id')) if settings.get('remove_channel_id') else None
        remove_enabled = settings.get('remove_enabled', 0)
        remove_status = f"{remove_channel.mention}" if remove_channel else "`No configurado`"
        if not remove_enabled:
            remove_status = f"~~{remove_status}~~ (desactivado)"
        embed.add_field(
            name="📤 Canal (Removido)",
            value=remove_status,
            inline=True
        )
        
        # Cantidad de vanitys
        embed.add_field(
            name="🏷️ Vanitys Activas",
            value=f"`{len(vanity_codes)}`",
            inline=True
        )
        
        # Lista de vanitys
        if vanity_codes:
            vanity_list = []
            for vc in vanity_codes[:10]:  # Máximo 10
                role = ctx.guild.get_role(vc['role_id'])
                role_text = role.mention if role else "❌ Rol eliminado"
                vanity_list.append(f"• `{vc['vanity_code']}` → {role_text}")
            
            embed.add_field(
                name="📋 Lista de Vanitys",
                value="\n".join(vanity_list) or "Ninguna",
                inline=False
            )
        
        # Comandos
        embed.add_field(
            name="⚙️ Comandos",
            value=(
                "`c!vanity add <código> @rol` — Añadir vanity\n"
                "`c!vanity remove <código>` — Quitar vanity\n"
                "`c!vanity channel #canal` — Canal (añadir)\n"
                "`c!vanity removechannel #canal` — Canal (removido)\n"
                "`c!vanity removenotify` — Toggle removido\n"
                "`c!vanity list` — Ver usuarios\n"
                "`c!vanity embed` — Personalizar embeds\n"
                "`c!vanity reset` — Borrar todo"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @vanity.command(name="add")
    @commands.has_permissions(administrator=True)
    async def vanity_add(self, ctx: commands.Context, codigo: str, rol: discord.Role):
        """Añade una vanity y su rol."""
        # Asegurar que exista settings
        if not get_vanity_settings(ctx.guild.id):
            set_vanity_settings(ctx.guild.id)
        
        if add_vanity_code(ctx.guild.id, codigo.lower(), rol.id):
            embed = discord.Embed(
                title="✅ Vanity Añadida",
                description=f"**Código:** `{codigo}`\n**Rol:** {rol.mention}",
                color=0x57F287
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ La vanity `{codigo}` ya existe.")
    
    @vanity.command(name="remove", aliases=["delete", "del"])
    @commands.has_permissions(administrator=True)
    async def vanity_remove(self, ctx: commands.Context, codigo: str):
        """Elimina una vanity."""
        if remove_vanity_code(ctx.guild.id, codigo.lower()):
            await ctx.send(f"✅ Vanity `{codigo}` eliminada.")
        else:
            await ctx.send(f"❌ No existe la vanity `{codigo}`.")
    
    @vanity.command(name="channel", aliases=["canal"])
    @commands.has_permissions(administrator=True)
    async def vanity_channel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Configura el canal de logs (cuando añaden vanity)."""
        set_vanity_settings(ctx.guild.id, channel_id=canal.id if canal else None)
        
        if canal:
            await ctx.send(f"✅ Canal de notificaciones (añadir) configurado: {canal.mention}")
        else:
            await ctx.send("✅ Canal de notificaciones (añadir) desactivado.")
    
    @vanity.command(name="removechannel", aliases=["removecanal"])
    @commands.has_permissions(administrator=True)
    async def vanity_remove_channel(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Configura el canal para notificaciones de removido."""
        set_vanity_settings(ctx.guild.id, remove_channel_id=canal.id if canal else None)
        
        if canal:
            await ctx.send(f"✅ Canal de notificaciones (removido) configurado: {canal.mention}")
        else:
            await ctx.send("✅ Canal de notificaciones (removido) desactivado.")
    
    @vanity.command(name="removenotify", aliases=["removenotificacion"])
    @commands.has_permissions(administrator=True)
    async def vanity_remove_notify(self, ctx: commands.Context):
        """Activa/desactiva notificaciones cuando quitan la vanity."""
        settings = get_vanity_settings(ctx.guild.id) or {}
        current = settings.get('remove_enabled', 0)
        new_value = 0 if current else 1
        
        set_vanity_settings(ctx.guild.id, remove_enabled=new_value)
        
        if new_value:
            await ctx.send("✅ Notificaciones de removido **activadas**.")
        else:
            await ctx.send("✅ Notificaciones de removido **desactivadas**.")
    
    @vanity.command(name="list", aliases=["users", "lista"])
    @commands.has_permissions(administrator=True)
    async def vanity_list(self, ctx: commands.Context):
        """Muestra usuarios con vanity en su estado."""
        vanity_codes = get_vanity_codes(ctx.guild.id)
        
        if not vanity_codes:
            await ctx.send("❌ No hay vanitys configuradas.")
            return
        
        msg = await ctx.send("🔄 Buscando usuarios...")
        
        results = {}
        for vc in vanity_codes:
            results[vc['vanity_code']] = []
        
        for member in ctx.guild.members:
            if member.bot:
                continue
            for vc in vanity_codes:
                if self.check_vanity(member, vc['vanity_code']):
                    results[vc['vanity_code']].append(member)
                    break
        
        embed = discord.Embed(
            title="👥 Usuarios con Vanity",
            color=0x5865F2
        )
        
        total = 0
        for vanity, members in results.items():
            total += len(members)
            if members:
                member_list = ", ".join([m.mention for m in members[:15]])
                if len(members) > 15:
                    member_list += f" y {len(members) - 15} más..."
            else:
                member_list = "*Ninguno*"
            
            embed.add_field(
                name=f"🔗 {vanity} ({len(members)})",
                value=member_list,
                inline=False
            )
        
        embed.set_footer(text=f"Total: {total} usuarios")
        await msg.edit(content=None, embed=embed)
    
    @vanity.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def vanity_embed(self, ctx: commands.Context):
        """Personaliza los embeds de notificación."""
        settings = get_vanity_settings(ctx.guild.id) or {}
        
        # Vista con botones
        class EmbedButtons(ui.View):
            def __init__(self, cog, settings):
                super().__init__(timeout=120)
                self.cog = cog
                self.settings = settings
            
            @ui.button(label="✅ Embed de Añadido", style=discord.ButtonStyle.success)
            async def edit_add(self, interaction: discord.Interaction, button: ui.Button):
                modal = EmbedEditorModal(
                    "add",
                    self.settings.get('embed_title', '✨ ¡Gracias por representarnos!'),
                    self.settings.get('embed_description', '{user} ahora tiene **{vanity}** en su estado y recibió {role}'),
                    self.settings.get('embed_color', 0x57F287)
                )
                await interaction.response.send_modal(modal)
                await modal.wait()
                
                if modal.new_title:
                    set_vanity_settings(
                        ctx.guild.id,
                        embed_title=modal.new_title,
                        embed_description=modal.new_desc,
                        embed_color=modal.new_color
                    )
                    self.settings = get_vanity_settings(ctx.guild.id) or {}
                    await interaction.followup.send("✅ Embed de añadido actualizado.", ephemeral=True)
            
            @ui.button(label="❌ Embed de Removido", style=discord.ButtonStyle.danger)
            async def edit_remove(self, interaction: discord.Interaction, button: ui.Button):
                modal = EmbedEditorModal(
                    "remove",
                    self.settings.get('remove_title', '😢 Vanity removida'),
                    self.settings.get('remove_description', '{user} ha quitado **{vanity}** de su estado y perdió {role}'),
                    self.settings.get('remove_color', 0xED4245)
                )
                await interaction.response.send_modal(modal)
                await modal.wait()
                
                if modal.new_title:
                    set_vanity_settings(
                        ctx.guild.id,
                        remove_title=modal.new_title,
                        remove_description=modal.new_desc,
                        remove_color=modal.new_color
                    )
                    self.settings = get_vanity_settings(ctx.guild.id) or {}
                    await interaction.followup.send("✅ Embed de removido actualizado.", ephemeral=True)
            
            @ui.button(label="👁️ Vista Previa", style=discord.ButtonStyle.secondary)
            async def preview(self, interaction: discord.Interaction, button: ui.Button):
                # Crear un rol falso para la vista previa
                fake_role = ctx.guild.roles[0]  # @everyone como placeholder
                
                embed_add = self.cog.build_embed(self.settings, ctx.author, "discord.gg/ejemplo", fake_role, is_add=True)
                embed_remove = self.cog.build_embed(self.settings, ctx.author, "discord.gg/ejemplo", fake_role, is_add=False)
                
                await interaction.response.send_message(
                    "**Vista previa de los embeds:**",
                    embeds=[embed_add, embed_remove],
                    ephemeral=True
                )
        
        embed = discord.Embed(
            title="✏️ Editor de Embeds",
            description=(
                "Personaliza los mensajes de notificación.\n\n"
                "**Variables:**\n"
                "`{user}` → Mención del usuario\n"
                "`{role}` → Mención del rol\n"
                "`{vanity}` → Código de la vanity\n"
                "`{server}` → Nombre del servidor\n\n"
                "**Formato de texto:**\n"
                "`**texto**` → **negrita**\n"
                "`*texto*` → *cursiva*\n"
                "`__texto__` → subrayado\n\n"
                "**Emojis del servidor:**\n"
                "Solo escribe `:nombre:` y se convierte automático\n"
                "Ejemplo: `:star:` → ⭐"
            ),
            color=0x5865F2
        )
        
        view = EmbedButtons(self, settings)
        await ctx.send(embed=embed, view=view)
    
    @vanity.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def vanity_reset(self, ctx: commands.Context):
        """Elimina toda la configuración de vanity."""
        # Confirmación
        embed = discord.Embed(
            title="⚠️ ¿Estás seguro?",
            description="Esto eliminará **todas** las vanitys y configuración.",
            color=0xFEE75C
        )
        
        class ConfirmView(ui.View):
            def __init__(self):
                super().__init__(timeout=30)
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
        
        view = ConfirmView()
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        
        if view.confirmed:
            delete_all_vanity(ctx.guild.id)
            embed.title = "✅ Configuración Eliminada"
            embed.description = "Toda la configuración de vanity ha sido borrada."
            embed.color = 0x57F287
        else:
            embed.title = "❌ Cancelado"
            embed.description = "No se eliminó nada."
            embed.color = 0xED4245
        
        await msg.edit(embed=embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(VanityCog(bot))
