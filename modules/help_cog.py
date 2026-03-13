import discord
from discord.ext import commands
from typing import List, Tuple

PRIVACY_URL = "https://copy.tyr.lat/privacy"
TERMS_URL = "https://copy.tyr.lat/terms"


def resolve_help_language(locale: object | None) -> str:
    """Mapea un locale de Discord a 'es' o 'en'."""
    if locale is None:
        return "es"

    normalized = str(locale).lower()
    if normalized.startswith("es"):
        return "es"
    return "en"


def get_help_embeds(lang: str = "es") -> List[discord.Embed]:
    """Devuelve la lista de embeds de ayuda en el idioma indicado ('es' o 'en')."""
    if lang not in {"es", "en"}:
        lang = "es"

    if lang == "es":
        embed0 = discord.Embed(
            title="Copy Bot - Guia de configuracion",
            description="Informacion importante antes de usar el bot.",
            color=0xFFD700,
        )
        embed0.add_field(
            name="Jerarquia de roles",
            value=(
                "Para que Copy pueda asignar roles, su rol debe estar por encima de los roles que va a dar.\n"
                "Ruta rapida: Ajustes del servidor -> Roles -> mueve el rol de Copy hacia arriba."
            ),
            inline=False,
        )
        embed0.add_field(
            name="Formatos de comando",
            value=(
                "Prefijos de texto: `c!` y `!`\n"
                "Slash disponibles: `/help`, `/thread`, `/counting`, `/react`, `/vanity`, `/clantag`, `/boostrole`"
            ),
            inline=False,
        )
        embed0.add_field(
            name="Modulos principales",
            value=(
                "`vanity` - Roles por vanity URL en estado\n"
                "`clantag` - Roles por clan tag\n"
                "`boostrole` - Roles para boosters\n"
                "`react` - Reacciones automaticas\n"
                "`thread` - Hilos automaticos\n"
                "`counting` - Canal de conteo"
            ),
            inline=False,
        )
        embed0.add_field(
            name="Legal",
            value=f"[Politica de privacidad]({PRIVACY_URL})\n[Terminos y condiciones]({TERMS_URL})",
            inline=False,
        )
        embed0.set_footer(text="Usa el selector para cambiar de seccion.")

        embed1 = discord.Embed(
            title="Ayuda: Expresiones",
            description="Comandos para clonar, crear y extraer emojis y stickers.",
            color=0x1ABC9C,
        )
        embed1.add_field(name="Disponible por texto", value="Usa `c!` o `!` para este modulo.", inline=False)
        embed1.add_field(name="`c!copy [nombre]`", value="Clona un emoji o sticker de otro mensaje.", inline=False)
        embed1.add_field(name="`c!emoji [nombre]`", value="Convierte un adjunto en emoji.", inline=False)
        embed1.add_field(name="`c!sticker [nombre]`", value="Sube un adjunto como sticker.", inline=False)
        embed1.add_field(name="`c!get`", value="Extrae la imagen de un emoji o sticker de un mensaje.", inline=False)
        embed1.set_footer(text="Seccion: Expresiones")

        embed2 = discord.Embed(
            title="Ayuda: Hilos automaticos",
            description="Gestiona la creacion automatica de hilos.",
            color=0x3498DB,
        )
        embed2.add_field(name="Formatos disponibles", value="Puedes usar `c!thread`, `!thread` o `/thread`.", inline=False)
        embed2.add_field(
            name="`thread add #canal <modo>`",
            value="Activa hilos automaticos para un canal. Modos: `all`, `media`, `text`.",
            inline=False,
        )
        embed2.add_field(name="`thread remove #canal`", value="Desactiva los hilos automaticos para un canal.", inline=False)
        embed2.add_field(name="`thread list`", value="Muestra los canales configurados en el servidor.", inline=False)
        embed2.set_footer(text="Seccion: Hilos")

        embed3 = discord.Embed(
            title="Ayuda: Informacion",
            description="Comandos para obtener informacion de usuarios, roles y servidor.",
            color=0x9B59B6,
        )
        embed3.add_field(name="Disponible por texto", value="Usa `c!` o `!` para este modulo.", inline=False)
        embed3.add_field(
            name="Usuarios",
            value="`c!user`, `c!userinfo`, `c!ui` - Informacion del usuario en MD o servidor.",
            inline=False,
        )
        embed3.add_field(name="Servidor", value="`c!serverinfo` o `c!server` - Estadisticas del servidor.", inline=False)
        embed3.add_field(name="Avatar", value="`c!avatar` o `c!pfp` - Avatar en grande y descarga.", inline=False)
        embed3.add_field(name="Roles", value="`c!roleinfo` o `c!role` - Detalle de roles y permisos.", inline=False)
        embed3.add_field(name="Boost", value="`c!boost` o `c!1boost` - Estado de boost del usuario.", inline=False)
        embed3.set_footer(text="Seccion: Informacion")

        embed4 = discord.Embed(
            title="Ayuda: Conteo",
            description="Configura y gestiona un canal de conteo numerico.",
            color=0xF1C40F,
        )
        embed4.add_field(name="Formatos disponibles", value="Puedes usar `c!counting`, `!counting` o `/counting`.", inline=False)
        embed4.add_field(name="`counting set <#canal>`", value="Establece el canal de conteo.", inline=False)
        embed4.add_field(name="`counting reset`", value="Reinicia el contador a 0 en el canal actual.", inline=False)
        embed4.add_field(name="`counting status`", value="Muestra el progreso actual del canal.", inline=False)
        embed4.add_field(
            name="Reglas",
            value=(
                "Se cuenta de uno en uno.\n"
                "No puedes contar dos veces seguidas.\n"
                "Numero incorrecto reinicia el conteo.\n"
                "Mensajes no numericos que no sean comandos se borran."
            ),
            inline=False,
        )
        embed4.set_footer(text="Seccion: Conteo")

        embed5 = discord.Embed(
            title="Ayuda: Reacciones automaticas",
            description="Configura reacciones automaticas por palabras clave.",
            color=0xE74C3C,
        )
        embed5.add_field(name="Formatos disponibles", value="Puedes usar `c!react`, `!react` o `/react`.", inline=False)
        embed5.add_field(
            name="`react add <palabra> <emoji...>`",
            value="Configura hasta 20 reacciones para una palabra o frase.",
            inline=False,
        )
        embed5.add_field(name="`react remove <palabra>`", value="Elimina una configuracion.", inline=False)
        embed5.add_field(name="`react list`", value="Muestra la configuracion actual.", inline=False)
        embed5.add_field(name="`react clear`", value="Elimina todas las configuraciones con confirmacion.", inline=False)
        embed5.add_field(
            name="Comportamiento",
            value="Soporta emojis unicode y custom del servidor. Detecta palabras completas.",
            inline=False,
        )
        embed5.set_footer(text="Seccion: Reacciones")

        embed6 = discord.Embed(
            title="Ayuda: Boost Roles",
            description="Gestiona roles para boosters.",
            color=0xA020F0,
        )
        embed6.add_field(name="Disponible por slash", value="Este modulo se configura con `/boostrole`.", inline=False)
        embed6.add_field(name="`/boostrole add`", value="Asigna o actualiza un rol para un miembro.", inline=False)
        embed6.add_field(name="`/boostrole remove`", value="Quita el rol y borra su registro.", inline=False)
        embed6.add_field(name="`/boostrole setlog`", value="Define el canal de logs del modulo.", inline=False)
        embed6.add_field(name="`/boostrole list`", value="Lista la configuracion actual.", inline=False)
        embed6.set_footer(text="Seccion: Boost Roles")

        embed7 = discord.Embed(
            title="Ayuda: Vanity Roles",
            description="Da roles a usuarios que pongan tu vanity URL en su estado personalizado.",
            color=0x5865F2,
        )
        embed7.add_field(
            name="Formatos disponibles",
            value="Puedes usar `c!vanity`, `!vanity` o `/vanity` para la configuracion principal. `embed` sigue siendo solo texto.",
            inline=False,
        )
        embed7.add_field(name="`vanity`", value="Abre el panel principal.", inline=False)
        embed7.add_field(name="`vanity add <vanity> @rol`", value="Anade una vanity y su rol.", inline=False)
        embed7.add_field(name="`vanity remove <vanity>`", value="Quita una vanity.", inline=False)
        embed7.add_field(name="`vanity list`", value="Lista usuarios y vanitys detectadas.", inline=False)
        embed7.add_field(
            name="Notificaciones",
            value="`vanity channel`, `vanity removechannel`, `vanity removenotify`, `vanity reset`.",
            inline=False,
        )
        embed7.set_footer(text="Seccion: Vanity")

        embed8 = discord.Embed(
            title="Ayuda: Clan Tag",
            description="Da roles a usuarios que tengan el clan tag del servidor.",
            color=0x5865F2,
        )
        embed8.add_field(
            name="Formatos disponibles",
            value="Puedes usar `c!clantag`, `!clantag` o `/clantag` para la configuracion principal. `embed` sigue siendo solo texto.",
            inline=False,
        )
        embed8.add_field(name="`clantag`", value="Abre el panel principal.", inline=False)
        embed8.add_field(name="`clantag role @rol`", value="Configura el rol a entregar.", inline=False)
        embed8.add_field(name="`clantag list`", value="Lista usuarios con tag detectado.", inline=False)
        embed8.add_field(
            name="Notificaciones",
            value="`clantag channel`, `clantag removechannel`, `clantag removenotify`, `clantag reset`.",
            inline=False,
        )
        embed8.add_field(
            name="Nota",
            value="Tu servidor debe tener un clan tag oficial de Discord para que este modulo funcione.",
            inline=False,
        )
        embed8.set_footer(text="Seccion: Clan Tag")

        return [embed0, embed1, embed2, embed3, embed4, embed5, embed6, embed7, embed8]

    embed0 = discord.Embed(
        title="Copy Bot - Setup guide",
        description="Important information before using the bot.",
        color=0xFFD700,
    )
    embed0.add_field(
        name="Role hierarchy",
        value=(
            "For Copy to assign roles, its role must be above the roles it needs to give.\n"
            "Quick path: Server Settings -> Roles -> move Copy higher."
        ),
        inline=False,
    )
    embed0.add_field(
        name="Command formats",
        value=(
            "Text prefixes: `c!` and `!`\n"
            "Available slash commands: `/help`, `/thread`, `/counting`, `/react`, `/vanity`, `/clantag`, `/boostrole`"
        ),
        inline=False,
    )
    embed0.add_field(
        name="Main modules",
        value=(
            "`vanity` - Roles from vanity URL in custom status\n"
            "`clantag` - Roles from clan tag\n"
            "`boostrole` - Booster role management\n"
            "`react` - Automatic reactions\n"
            "`thread` - Automatic threads\n"
            "`counting` - Counting channel"
        ),
        inline=False,
    )
    embed0.add_field(
        name="Legal",
        value=f"[Privacy Policy]({PRIVACY_URL})\n[Terms of Service]({TERMS_URL})",
        inline=False,
    )
    embed0.set_footer(text="Use the selector to switch sections.")

    embed1 = discord.Embed(
        title="Help: Expressions",
        description="Commands to clone, create, and extract emojis and stickers.",
        color=0x1ABC9C,
    )
    embed1.add_field(name="Text only", value="Use `c!` or `!` for this module.", inline=False)
    embed1.add_field(name="`c!copy [name]`", value="Clone an emoji or sticker from another message.", inline=False)
    embed1.add_field(name="`c!emoji [name]`", value="Turn an attachment into an emoji.", inline=False)
    embed1.add_field(name="`c!sticker [name]`", value="Upload an attachment as a sticker.", inline=False)
    embed1.add_field(name="`c!get`", value="Extract an emoji or sticker image from a message.", inline=False)
    embed1.set_footer(text="Section: Expressions")

    embed2 = discord.Embed(
        title="Help: Auto threads",
        description="Manage automatic thread creation.",
        color=0x3498DB,
    )
    embed2.add_field(name="Available formats", value="You can use `c!thread`, `!thread`, or `/thread`.", inline=False)
    embed2.add_field(name="`thread add #channel <mode>`", value="Enable automatic threads. Modes: `all`, `media`, `text`.", inline=False)
    embed2.add_field(name="`thread remove #channel`", value="Disable automatic threads for a channel.", inline=False)
    embed2.add_field(name="`thread list`", value="Show configured channels.", inline=False)
    embed2.set_footer(text="Section: Threads")

    embed3 = discord.Embed(
        title="Help: Information",
        description="Commands to get information about users, roles, and the server.",
        color=0x9B59B6,
    )
    embed3.add_field(name="Text only", value="Use `c!` or `!` for this module.", inline=False)
    embed3.add_field(name="Users", value="`c!user`, `c!userinfo`, `c!ui` - User information in DMs or server.", inline=False)
    embed3.add_field(name="Server", value="`c!serverinfo` or `c!server` - Server statistics.", inline=False)
    embed3.add_field(name="Avatar", value="`c!avatar` or `c!pfp` - Large avatar preview and download.", inline=False)
    embed3.add_field(name="Roles", value="`c!roleinfo` or `c!role` - Role details and permissions.", inline=False)
    embed3.add_field(name="Boost", value="`c!boost` or `c!1boost` - User boost status.", inline=False)
    embed3.set_footer(text="Section: Information")

    embed4 = discord.Embed(
        title="Help: Counting",
        description="Configure and manage a numeric counting channel.",
        color=0xF1C40F,
    )
    embed4.add_field(name="Available formats", value="You can use `c!counting`, `!counting`, or `/counting`.", inline=False)
    embed4.add_field(name="`counting set <#channel>`", value="Set the counting channel.", inline=False)
    embed4.add_field(name="`counting reset`", value="Reset the counter to 0 in the current channel.", inline=False)
    embed4.add_field(name="`counting status`", value="Show the current progress for this channel.", inline=False)
    embed4.add_field(
        name="Rules",
        value=(
            "Count one by one.\n"
            "You cannot count twice in a row.\n"
            "A wrong number resets the count.\n"
            "Non-numeric non-command messages are deleted."
        ),
        inline=False,
    )
    embed4.set_footer(text="Section: Counting")

    embed5 = discord.Embed(
        title="Help: Auto reactions",
        description="Configure automatic reactions for keywords.",
        color=0xE74C3C,
    )
    embed5.add_field(name="Available formats", value="You can use `c!react`, `!react`, or `/react`.", inline=False)
    embed5.add_field(name="`react add <word> <emoji...>`", value="Configure up to 20 reactions for a word or phrase.", inline=False)
    embed5.add_field(name="`react remove <word>`", value="Remove one configuration.", inline=False)
    embed5.add_field(name="`react list`", value="Show the current configuration.", inline=False)
    embed5.add_field(name="`react clear`", value="Remove all configurations with confirmation.", inline=False)
    embed5.add_field(name="Behavior", value="Supports unicode and custom server emojis. Detects whole words.", inline=False)
    embed5.set_footer(text="Section: Auto reactions")

    embed6 = discord.Embed(
        title="Help: Boost Roles",
        description="Manage booster roles.",
        color=0xA020F0,
    )
    embed6.add_field(name="Slash only", value="This module is configured with `/boostrole`.", inline=False)
    embed6.add_field(name="`/boostrole add`", value="Assign or update a role for a member.", inline=False)
    embed6.add_field(name="`/boostrole remove`", value="Remove the role and delete its record.", inline=False)
    embed6.add_field(name="`/boostrole setlog`", value="Set the module log channel.", inline=False)
    embed6.add_field(name="`/boostrole list`", value="List current configuration.", inline=False)
    embed6.set_footer(text="Section: Boost Roles")

    embed7 = discord.Embed(
        title="Help: Vanity Roles",
        description="Give roles to users who put your vanity URL in their custom status.",
        color=0x5865F2,
    )
    embed7.add_field(
        name="Available formats",
        value="You can use `c!vanity`, `!vanity`, or `/vanity` for the main setup. `embed` remains text-only.",
        inline=False,
    )
    embed7.add_field(name="`vanity`", value="Open the main panel.", inline=False)
    embed7.add_field(name="`vanity add <vanity> @role`", value="Add a vanity and role.", inline=False)
    embed7.add_field(name="`vanity remove <vanity>`", value="Remove a vanity.", inline=False)
    embed7.add_field(name="`vanity list`", value="List detected users and vanity entries.", inline=False)
    embed7.add_field(name="Notifications", value="`vanity channel`, `vanity removechannel`, `vanity removenotify`, `vanity reset`.", inline=False)
    embed7.set_footer(text="Section: Vanity")

    embed8 = discord.Embed(
        title="Help: Clan Tag",
        description="Give roles to users who have the server clan tag.",
        color=0x5865F2,
    )
    embed8.add_field(
        name="Available formats",
        value="You can use `c!clantag`, `!clantag`, or `/clantag` for the main setup. `embed` remains text-only.",
        inline=False,
    )
    embed8.add_field(name="`clantag`", value="Open the main panel.", inline=False)
    embed8.add_field(name="`clantag role @role`", value="Set the role to give.", inline=False)
    embed8.add_field(name="`clantag list`", value="List users with detected tag.", inline=False)
    embed8.add_field(name="Notifications", value="`clantag channel`, `clantag removechannel`, `clantag removenotify`, `clantag reset`.", inline=False)
    embed8.add_field(name="Note", value="Your server must have an official Discord clan tag for this module to work.", inline=False)
    embed8.set_footer(text="Section: Clan Tag")

    return [embed0, embed1, embed2, embed3, embed4, embed5, embed6, embed7, embed8]


def get_select_options(lang: str, current_index: int = 0) -> Tuple[List[discord.SelectOption], str]:
    """Opciones del menu por idioma. Retorna (options, placeholder)."""
    if lang == "en":
        labels = [
            ("Setup Guide", "Important info before starting"),
            ("Expressions", "Emojis and stickers"),
            ("Threads", "Automatic threads"),
            ("Information", "Users, roles and server"),
            ("Counting", "Numeric counting channel"),
            ("Auto Reactions", "Automatic emoji reactions"),
            ("Boost Roles", "Roles for boosters"),
            ("Vanity Roles", "Vanity URL in custom status"),
            ("Clan Tag", "Server clan tag roles"),
        ]
        placeholder = "Choose a help section..."
    else:
        labels = [
            ("Guia de configuracion", "Info importante antes de empezar"),
            ("Expresiones", "Emojis y stickers"),
            ("Hilos", "Hilos automaticos"),
            ("Informacion", "Usuarios, roles y servidor"),
            ("Conteo", "Canal de conteo numerico"),
            ("Reacciones", "Reacciones automaticas"),
            ("Boost Roles", "Roles para boosters"),
            ("Vanity Roles", "Vanity URL en estado"),
            ("Clan Tag", "Roles por clan tag"),
        ]
        placeholder = "Elige una seccion de ayuda..."

    options: List[discord.SelectOption] = []
    for idx, (label, desc) in enumerate(labels):
        options.append(
            discord.SelectOption(
                label=label,
                description=desc,
                value=str(idx),
                default=(idx == current_index),
            )
        )
    return options, placeholder


class HelpSelect(discord.ui.Select):
    def __init__(self, *, lang: str, current_index: int):
        self.lang = lang
        options, placeholder = get_select_options(lang, current_index)
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        assert isinstance(self.view, HelpView)
        self.view.current_index = index
        await interaction.response.edit_message(embed=self.view.embeds[index], view=self.view)


class LangButton(discord.ui.Button):
    def __init__(self, lang: str, active: bool = False):
        self.lang = lang
        label = "ES" if lang == "es" else "EN"
        style = discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary
        super().__init__(label=label, style=style, disabled=active)

    async def callback(self, interaction: discord.Interaction):
        assert isinstance(self.view, HelpView)
        if self.view.lang == self.lang:
            await interaction.response.defer()
            return

        new_view = HelpView(lang=self.lang, current_index=self.view.current_index)
        new_embed = new_view.embeds[self.view.current_index]
        await interaction.response.edit_message(embed=new_embed, view=new_view)


class HelpView(discord.ui.View):
    def __init__(self, *, lang: str = "es", current_index: int = 0):
        super().__init__(timeout=180)
        self.lang = lang
        self.current_index = current_index
        self.embeds = get_help_embeds(lang)

        self.add_item(HelpSelect(lang=self.lang, current_index=self.current_index))
        self.add_item(LangButton("es", active=(self.lang == "es")))
        self.add_item(LangButton("en", active=(self.lang == "en")))
        self.add_item(discord.ui.Button(label="Privacy", style=discord.ButtonStyle.link, url=PRIVACY_URL, row=2))
        self.add_item(discord.ui.Button(label="Terms", style=discord.ButtonStyle.link, url=TERMS_URL, row=2))


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.remove_command("help")

    @commands.command(name="help")
    async def custom_help(self, ctx: commands.Context):
        """Muestra el menu de ayuda con selector de idioma y secciones."""
        locale = getattr(ctx.guild, "preferred_locale", None) if ctx.guild else None
        view = HelpView(lang=resolve_help_language(locale), current_index=0)
        await ctx.reply(embed=view.embeds[0], view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
