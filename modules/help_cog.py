# modules/help_cog.py
import discord
from discord.ext import commands
from typing import List, Tuple

PRIVACY_URL = "https://copy.tyr.lat/privacy"
TERMS_URL = "https://copy.tyr.lat/terms"

# ─────────────────────────────────────────────────────────────────────────────
# Generador de Embeds por idioma
# ─────────────────────────────────────────────────────────────────────────────

def get_help_embeds(lang: str = "es") -> List[discord.Embed]:
    """Devuelve la lista de embeds de ayuda en el idioma indicado ('es' o 'en')."""
    if lang not in {"es", "en"}:
        lang = "es"

    if lang == "es":
        # --- Sección 0: Información Importante ---
        embed0 = discord.Embed(
            title="📖 Copy Bot - Guía de Configuración",
            description="**Información importante antes de usar el bot.**",
            color=0xFFD700
        )
        embed0.add_field(
            name="🔧 Jerarquía de Roles",
            value=(
                "Para que Copy pueda asignar roles (Vanity, Clan Tag, Boost, etc.), "
                "su rol debe estar **por encima** de los roles que va a dar.\n\n"
                "**¿Cómo hacerlo?**\n"
                "`Ajustes del Servidor` → `Roles` → Arrastra el rol de **Copy** hacia arriba."
            ),
            inline=False
        )
        embed0.add_field(
            name="⚠️ Problemas Comunes",
            value=(
                "• **El bot no da roles** → El rol de Copy está muy abajo.\n"
                "• **Vanity/Tag no detecta** → Asegúrate de configurarlo con `c!vanity` o `c!clantag`.\n"
                "• **Reacciones incompletas** → El bot necesita permiso de `Añadir Reacciones`."
            ),
            inline=False
        )
        embed0.add_field(
            name="📚 Módulos Principales",
            value=(
                "`c!vanity` — Roles por Vanity URL en estado\n"
                "`c!clantag` — Roles por Clan Tag oficial\n"
                "`c!boost` — Roles personalizados para boosters\n"
                "`c!react` — Reacciones automáticas\n"
                "`c!thread` — Hilos automáticos\n"
                "`c!counting` — Canal de conteo"
            ),
            inline=False
        )
        embed0.add_field(
            name="🔒 Legal",
            value=(
                f"[Política de Privacidad]({PRIVACY_URL})\n"
                f"[Términos y Condiciones]({TERMS_URL})"
            ),
            inline=False
        )
        embed0.set_footer(text="Usa las flechas para navegar por todos los módulos ➡️")

        # --- Sección 1: Módulo de Expresiones ---
        embed1 = discord.Embed(
            title="🤖 Ayuda: Módulo de Expresiones",
            description="Comandos para clonar, crear y extraer emojis y stickers.",
            color=0x1ABC9C
        )
        embed1.add_field(name="`c!copy [nombre]`", value="Clona un emoji o sticker de otro mensaje para usarlo en este servidor.", inline=False)
        embed1.add_field(name="`c!emoji [nombre]`", value="Respondiendo a un adjunto (PNG/JPG/GIF), lo convierte en un emoji.", inline=False)
        embed1.add_field(name="`c!sticker [nombre]`", value="Respondiendo a un adjunto (PNG/JPG/GIF), lo sube como un sticker.", inline=False)
        embed1.add_field(name="`c!get`", value="Respondiendo a un mensaje, te envía la imagen de su sticker o emoji.", inline=False)
        embed1.set_footer(text="Sección: Expresiones")

        # --- Sección 2: Módulo de Hilos ---
        embed2 = discord.Embed(
            title="⚙️ Ayuda: Módulo de Hilos Automáticos",
            description="Comandos para gestionar la creación automática de hilos.",
            color=0x3498DB
        )
        embed2.add_field(
            name="`c!thread add #canal <modo>`",
            value=(
                "Activa los hilos automáticos para un canal.\n"
                "• **Modo `all`**: Para cualquier mensaje.\n"
                "• **Modo `media`**: Solo si el mensaje tiene imágenes/videos.\n"
                "• **Modo `text`**: Solo si el mensaje tiene texto y no multimedia."
            ),
            inline=False
        )
        embed2.add_field(name="`c!thread remove #canal`", value="Desactiva los hilos automáticos para un canal.", inline=False)
        embed2.add_field(name="`c!thread list`", value="Muestra todos los canales configurados en el servidor.", inline=False)
        embed2.set_footer(text="Sección: Hilos")

        # --- Sección 3: Módulo de Información ---
        embed3 = discord.Embed(
            title="ℹ️ Ayuda: Módulo de Información",
            description="Comandos para obtener información de usuarios, roles y servidor.",
            color=0x9B59B6
        )
        embed3.add_field(
            name="Usuarios",
            value=(
                "• `c!user [@usuario/ID]`\n"
                "• Alias: `c!userinfo`, `c!ui`\n"
                "Muestra información del usuario. **MD:** solo datos públicos (avatar, banner, insignias, creación de cuenta). "
                "**Servidor:** añade roles, fecha de ingreso, actividad y estado de boost."
            ),
            inline=False
        )
        embed3.add_field(
            name="Servidor",
            value="• `c!serverinfo` (alias: `c!server`) — Estadísticas y datos del servidor.",
            inline=False
        )
        embed3.add_field(
            name="Avatar",
            value="• `c!avatar [@usuario/ID]` (alias: `c!pfp`) — Muestra el avatar en grande y enlace de descarga.",
            inline=False
        )
        embed3.add_field(
            name="Roles",
            value="• `c!roleinfo <@rol/ID>` (alias: `c!role`) — Información detallada del rol y permisos clave.",
            inline=False
        )
        embed3.add_field(
            name="Boost del usuario (solo en servidor)",
            value="• `c!boost [@usuario/ID]` (alias: `c!1boost`) — Muestra si tiene boost activo y los inicios de boost detectados.",
            inline=False
        )
        embed3.set_footer(text="Sección: Información")

        # --- Sección 4: Conteo ---
        embed4 = discord.Embed(
            title="🎰 Ayuda: Módulo de Conteo",
            description="Configura y gestiona un canal de conteo numérico.",
            color=0xF1C40F
        )
        embed4.add_field(
            name="Configurar",
            value="• `c!counting set <#canal>` — Establece el canal de conteo. Requiere `Gestionar Canales`.",
            inline=False
        )
        embed4.add_field(
            name="Reiniciar",
            value="• `c!counting reset` — Reinicia el contador a 0 en el canal actual. Requiere `Gestionar Canales`.",
            inline=False
        )
        embed4.add_field(
            name="Reglas y comportamiento",
            value=(
                "• Se cuenta de uno en uno (1, 2, 3...).\n"
                "• No puedes contar dos veces seguidas (se borra tu mensaje y se avisa, **sin reiniciar**).\n"
                "• Número incorrecto ⇒ ❌ y **reinicio** a 0.\n"
                "• Mensajes no numéricos (que no sean comandos) se borran."
            ),
            inline=False
        )
        embed4.set_footer(text="Sección: Conteo")

        # --- Sección 5: Reacciones Automáticas ---
        embed5 = discord.Embed(
            title="😊 Ayuda: Módulo de Reacciones Automáticas",
            description="Configura reacciones automáticas por palabras clave.",
            color=0xE74C3C
        )
        embed5.add_field(
            name="Agregar reacciones",
            value=(
                "• `c!react add <palabra> <emoji1> [emoji2] ...`\n"
                "Configura hasta 20 reacciones para una palabra. Requiere `Gestionar Servidor`.\n"
                "Ejemplo: `c!react add wlc 👋 💜 ✨ 🎉`"
            ),
            inline=False
        )
        embed5.add_field(
            name="Eliminar reacciones",
            value="• `c!react remove <palabra>` — Elimina las reacciones de una palabra específica.",
            inline=False
        )
        embed5.add_field(
            name="Ver configuración",
            value="• `c!react list` — Muestra todas las palabras configuradas con sus reacciones.",
            inline=False
        )
        embed5.add_field(
            name="Limpiar todo",
            value="• `c!react clear` — Elimina todas las configuraciones (requiere confirmación).",
            inline=False
        )
        embed5.add_field(
            name="Comportamiento",
            value=(
                "• Detecta palabras completas (case-insensitive).\n"
                "• Soporta emojis Unicode y emojis custom del servidor.\n"
                "• Las reacciones se aplican automáticamente cuando alguien usa la palabra."
            ),
            inline=False
        )
        embed5.set_footer(text="Sección: Reacciones Automáticas")

        # --- Sección 6: Boost Roles (slash commands) ---
        embed6 = discord.Embed(
            title="💜 Ayuda: Módulo Boost Roles",
            description="Gestión de roles exclusivos para boosters y roles normales (comandos slash).",
            color=0xA020F0
        )
        embed6.add_field(
            name="Asignación y estado",
            value=(
                "• `/boostrole add user:<miembro> role:<rol> linked_to_boost:<True|False>`\n"
                "Asigna/actualiza un rol. Si `linked_to_boost=True`, se retira al perder el boost."
            ),
            inline=False
        )
        embed6.add_field(
            name="Eliminación",
            value="• `/boostrole remove user:<miembro> role:<rol>` — Quita el rol y borra su registro.",
            inline=False
        )
        embed6.add_field(
            name="Logs",
            value="• `/boostrole setlog channel:<#canal>` — Define el canal de logs del módulo.",
            inline=False
        )
        embed6.add_field(
            name="Listado",
            value="• `/boostrole list` — Lista la configuración con paginación.",
            inline=False
        )
        embed6.add_field(
            name="Automático",
            value=(
                "• Al perder boost se retiran roles ligados.\n"
                "• Auditoría cada 12 h para retirar roles ligados a quien ya no boostea."
            ),
            inline=False
        )
        embed6.set_footer(text="Sección: Boost Roles")

        # --- Sección 7: Vanity Roles ---
        embed7 = discord.Embed(
            title="🔗 Ayuda: Módulo Vanity Roles",
            description="Da roles a usuarios que pongan tu vanity URL en su estado personalizado.",
            color=0x5865F2
        )
        embed7.add_field(
            name="⚙️ Configuración",
            value=(
                "**`c!vanity`** — Panel de control\n"
                "**`c!vanity add <vanity> @rol`** — Añadir vanity\n"
                "**`c!vanity remove <vanity>`** — Quitar vanity\n"
                "**`c!vanity list`** — Ver usuarios con vanity\n\n"
                "Ejemplo: `c!vanity add discord.gg/miserver @Vanity`"
            ),
            inline=False
        )
        embed7.add_field(
            name="📢 Notificaciones",
            value=(
                "**`c!vanity channel #canal`** — Canal cuando añaden vanity\n"
                "**`c!vanity removechannel #canal`** — Canal cuando quitan vanity\n"
                "**`c!vanity removenotify`** — Activar/desactivar notif. de removido\n"
                "**`c!vanity embed`** — Personalizar embeds (título, descripción, color)"
            ),
            inline=False
        )
        embed7.add_field(
            name="📝 ¿Cómo funciona?",
            value=(
                "Detecta **instantáneamente** cuando un usuario pone\n"
                "tu vanity en su **Estado Personalizado** de Discord.\n\n"
                "Puedes tener múltiples vanitys con diferentes roles."
            ),
            inline=False
        )
        embed7.add_field(
            name="🗑️ Otros",
            value="**`c!vanity reset`** — Borrar toda la configuración",
            inline=False
        )
        embed7.set_footer(text="Sección: Vanity Roles")

        # --- Sección 8: Clan Tag ---
        embed8 = discord.Embed(
            title="🏷️ Ayuda: Módulo Clan Tag",
            description="Da roles a usuarios que tengan el tag del clan de tu servidor.",
            color=0x5865F2
        )
        embed8.add_field(
            name="⚙️ Configuración",
            value=(
                "**`c!clantag`** — Panel de control\n"
                "**`c!clantag role @rol`** — Configurar rol\n"
                "**`c!clantag list`** — Ver usuarios con tag\n\n"
                "El bot detecta **automáticamente** el tag de tu servidor."
            ),
            inline=False
        )
        embed8.add_field(
            name="📢 Notificaciones",
            value=(
                "**`c!clantag channel #canal`** — Canal cuando añaden tag\n"
                "**`c!clantag removechannel #canal`** — Canal cuando quitan tag\n"
                "**`c!clantag removenotify`** — Activar/desactivar notif. de removido\n"
                "**`c!clantag embed`** — Personalizar embeds"
            ),
            inline=False
        )
        embed8.add_field(
            name="📝 ¿Cómo funciona?",
            value=(
                "Detecta cuando un usuario tiene el **Clan Tag oficial**\n"
                "de Discord de tu servidor junto a su nombre.\n\n"
                "⚠️ Tu servidor debe tener un Clan de Discord."
            ),
            inline=False
        )
        embed8.add_field(
            name="🗑️ Otros",
            value="**`c!clantag reset`** — Borrar toda la configuración",
            inline=False
        )
        embed8.set_footer(text="Sección: Clan Tag")

        return [embed0, embed1, embed2, embed3, embed4, embed5, embed6, embed7, embed8]

    # ===================== ENGLISH =====================
    # --- Section 0: Important Info ---
    embed0 = discord.Embed(
        title="📖 Copy Bot - Setup Guide",
        description="**Important information before using the bot.**",
        color=0xFFD700
    )
    embed0.add_field(
        name="🔧 Role Hierarchy",
        value=(
            "For Copy to assign roles (Vanity, Clan Tag, Boost, etc.), "
            "its role must be **above** the roles it needs to give.\n\n"
            "**How to fix it?**\n"
            "`Server Settings` → `Roles` → Drag **Copy's** role higher up."
        ),
        inline=False
    )
    embed0.add_field(
        name="⚠️ Common Issues",
        value=(
            "• **Bot can't give roles** → Copy's role is too low.\n"
            "• **Vanity/Tag not detecting** → Make sure to configure with `c!vanity` or `c!clantag`.\n"
            "• **Incomplete reactions** → Bot needs `Add Reactions` permission."
        ),
        inline=False
    )
    embed0.add_field(
        name="📚 Main Modules",
        value=(
            "`c!vanity` — Roles for Vanity URL in status\n"
            "`c!clantag` — Roles for official Clan Tag\n"
            "`c!boost` — Custom roles for boosters\n"
            "`c!react` — Auto reactions\n"
            "`c!thread` — Auto threads\n"
            "`c!counting` — Counting channel"
        ),
        inline=False
    )
    embed0.add_field(
        name="🔒 Legal",
        value=(
            f"[Privacy Policy]({PRIVACY_URL})\n"
            f"[Terms of Service]({TERMS_URL})"
        ),
        inline=False
    )
    embed0.set_footer(text="Use the arrows to navigate through all modules ➡️")

    # --- Section 1: Expressions Module ---
    embed1 = discord.Embed(
        title="🤖 Help: Expressions Module",
        description="Commands to clone, create, and extract emojis and stickers.",
        color=0x1ABC9C
    )
    embed1.add_field(name="`c!copy [name]`", value="Clone an emoji or sticker from another message to use it in this server.", inline=False)
    embed1.add_field(name="`c!emoji [name]`", value="Replying to an attachment (PNG/JPG/GIF) turns it into an emoji.", inline=False)
    embed1.add_field(name="`c!sticker [name]`", value="Replying to an attachment (PNG/JPG/GIF) uploads it as a sticker.", inline=False)
    embed1.add_field(name="`c!get`", value="Replying to a message sends you the image of its sticker or emoji.", inline=False)
    embed1.set_footer(text="Section: Expressions")

    # --- Section 2: Auto Threads Module ---
    embed2 = discord.Embed(
        title="⚙️ Help: Auto Threads Module",
        description="Commands to manage automatic thread creation.",
        color=0x3498DB
    )
    embed2.add_field(
        name="`c!thread add #channel <mode>`",
        value=(
            "Enable automatic threads for a channel.\n"
            "• **Mode `all`**: For any message.\n"
            "• **Mode `media`**: Only if the message has images/videos.\n"
            "• **Mode `text`**: Only if the message has text and no media."
        ),
        inline=False
    )
    embed2.add_field(name="`c!thread remove #channel`", value="Disable automatic threads for a channel.", inline=False)
    embed2.add_field(name="`c!thread list`", value="Show all configured channels in the server.", inline=False)
    embed2.set_footer(text="Section: Threads")

    # --- Section 3: Info Module ---
    embed3 = discord.Embed(
        title="ℹ️ Help: Information Module",
        description="Commands to get info about users, roles, and the server.",
        color=0x9B59B6
    )
    embed3.add_field(
        name="Users",
        value=(
            "• `c!user [@user/ID]`\n"
            "• Aliases: `c!userinfo`, `c!ui`\n"
            "Shows user information. **DMs:** public data only (avatar, banner, badges, account creation). "
            "**Server:** adds roles, join date, activity, and boost status."
        ),
        inline=False
    )
    embed3.add_field(
        name="Server",
        value="• `c!serverinfo` (alias: `c!server`) — Server statistics and data.",
        inline=False
    )
    embed3.add_field(
        name="Avatar",
        value="• `c!avatar [@user/ID]` (alias: `c!pfp`) — Shows the avatar in full size and a download link.",
        inline=False
    )
    embed3.add_field(
        name="Roles",
        value="• `c!roleinfo <@role/ID>` (alias: `c!role`) — Detailed role info and key permissions.",
        inline=False
    )
    embed3.add_field(
        name="User Boost (server only)",
        value="• `c!boost [@user/ID]` (alias: `c!1boost`) — Shows if they have an active boost and detected boost starts.",
        inline=False
    )
    embed3.set_footer(text="Section: Information")

    # --- Section 4: Counting ---
    embed4 = discord.Embed(
        title="🎰 Help: Counting Module",
        description="Configure and manage a numeric counting channel.",
        color=0xF1C40F
    )
    embed4.add_field(
        name="Setup",
        value="• `c!counting set <#channel>` — Set the counting channel. Requires `Manage Channels`.",
        inline=False
    )
    embed4.add_field(
        name="Reset",
        value="• `c!counting reset` — Reset the counter to 0 in the current channel. Requires `Manage Channels`.",
        inline=False
    )
    embed4.add_field(
        name="Rules & behavior",
        value=(
            "• Count up by one (1, 2, 3...).\n"
            "• You can’t count twice in a row (your message is deleted and warned, **no reset**).\n"
            "• Wrong number ⇒ ❌ and **reset** to 0.\n"
            "• Non-numeric messages (that aren’t commands) are deleted."
        ),
        inline=False
    )
    embed4.set_footer(text="Section: Counting")

    # --- Section 5: Auto Reactions ---
    embed5 = discord.Embed(
        title="😊 Help: Auto Reactions Module",
        description="Configure automatic reactions for keywords.",
        color=0xE74C3C
    )
    embed5.add_field(
        name="Add reactions",
        value=(
            "• `c!react add <word> <emoji1> [emoji2] ...`\n"
            "Configure up to 20 reactions for a word. Requires `Manage Server`.\n"
            "Example: `c!react add wlc 👋 💜 ✨ 🎉`"
        ),
        inline=False
    )
    embed5.add_field(
        name="Remove reactions",
        value="• `c!react remove <word>` — Remove reactions for a specific word.",
        inline=False
    )
    embed5.add_field(
        name="View configuration",
        value="• `c!react list` — Show all configured words with their reactions.",
        inline=False
    )
    embed5.add_field(
        name="Clear all",
        value="• `c!react clear` — Remove all configurations (requires confirmation).",
        inline=False
    )
    embed5.add_field(
        name="Behavior",
        value=(
            "• Detects whole words (case-insensitive).\n"
            "• Supports Unicode and custom server emojis.\n"
            "• Reactions are applied automatically when someone uses the word."
        ),
        inline=False
    )
    embed5.set_footer(text="Section: Auto Reactions")

    # --- Section 6: Boost Roles (slash commands) ---
    embed6 = discord.Embed(
        title="💜 Help: Boost Roles Module",
        description="Manage booster-exclusive roles and regular roles (slash commands).",
        color=0xA020F0
    )
    embed5.add_field(
        name="Assign & status",
        value=(
            "• `/boostrole add user:<member> role:<role> linked_to_boost:<True|False>`\n"
            "Assign/update a role. If `linked_to_boost=True`, it’s removed when the boost ends."
        ),
        inline=False
    )
    embed5.add_field(
        name="Removal",
        value="• `/boostrole remove user:<member> role:<role>` — Remove the role and delete its record.",
        inline=False
    )
    embed5.add_field(
        name="Logs",
        value="• `/boostrole setlog channel:<#channel>` — Set the module log channel.",
        inline=False
    )
    embed5.add_field(
        name="List",
        value="• `/boostrole list` — List the configuration with pagination.",
        inline=False
    )
    embed5.add_field(
        name="Automatic",
        value=(
            "• When a user loses boost, linked roles are removed.\n"
            "• Audit every 12h to remove linked roles from users who no longer boost."
        ),
        inline=False
    )
    embed5.set_footer(text="Section: Auto Reactions")

    # --- Section 6: Boost Roles (slash commands) ---
    embed6 = discord.Embed(
        title="💜 Help: Boost Roles Module",
        description="Manage booster-exclusive roles and regular roles (slash commands).",
        color=0xA020F0
    )
    embed6.add_field(
        name="Assign & status",
        value=(
            "• `/boostrole add user:<member> role:<role> linked_to_boost:<True|False>`\n"
            "Assign/update a role. If `linked_to_boost=True`, it's removed when the boost ends."
        ),
        inline=False
    )
    embed6.add_field(
        name="Removal",
        value="• `/boostrole remove user:<member> role:<role>` — Remove the role and delete its record.",
        inline=False
    )
    embed6.add_field(
        name="Logs",
        value="• `/boostrole setlog channel:<#channel>` — Set the module log channel.",
        inline=False
    )
    embed6.add_field(
        name="List",
        value="• `/boostrole list` — List the configuration with pagination.",
        inline=False
    )
    embed6.add_field(
        name="Automatic",
        value=(
            "• When a user loses boost, linked roles are removed.\n"
            "• Audit every 12h to remove linked roles from users who no longer boost."
        ),
        inline=False
    )
    embed6.set_footer(text="Section: Boost Roles")

    # --- Section 7: Vanity Roles ---
    embed7 = discord.Embed(
        title="🔗 Help: Vanity Roles Module",
        description="Give roles to users who put your vanity URL in their custom status.",
        color=0x5865F2
    )
    embed7.add_field(
        name="⚙️ Configuration",
        value=(
            "**`c!vanity`** — Control panel\n"
            "**`c!vanity add <vanity> @role`** — Add vanity\n"
            "**`c!vanity remove <vanity>`** — Remove vanity\n"
            "**`c!vanity list`** — View users with vanity\n\n"
            "Example: `c!vanity add discord.gg/myserver @Vanity`"
        ),
        inline=False
    )
    embed7.add_field(
        name="📢 Notifications",
        value=(
            "**`c!vanity channel #channel`** — Channel when vanity added\n"
            "**`c!vanity removechannel #channel`** — Channel when vanity removed\n"
            "**`c!vanity removenotify`** — Toggle remove notifications\n"
            "**`c!vanity embed`** — Customize embeds (title, description, color)"
        ),
        inline=False
    )
    embed7.add_field(
        name="📝 How does it work?",
        value=(
            "**Instantly** detects when a user puts your\n"
            "vanity in their **Custom Status** on Discord.\n\n"
            "You can have multiple vanitys with different roles."
        ),
        inline=False
    )
    embed7.add_field(
        name="🗑️ Other",
        value="**`c!vanity reset`** — Delete all configuration",
        inline=False
    )
    embed7.set_footer(text="Section: Vanity Roles")

    # --- Section 8: Clan Tag ---
    embed8 = discord.Embed(
        title="🏷️ Help: Clan Tag Module",
        description="Give roles to users who have your server's clan tag.",
        color=0x5865F2
    )
    embed8.add_field(
        name="⚙️ Configuration",
        value=(
            "**`c!clantag`** — Control panel\n"
            "**`c!clantag role @role`** — Configure role\n"
            "**`c!clantag list`** — View users with tag\n\n"
            "The bot **automatically** detects your server's tag."
        ),
        inline=False
    )
    embed8.add_field(
        name="📢 Notifications",
        value=(
            "**`c!clantag channel #channel`** — Channel when tag added\n"
            "**`c!clantag removechannel #channel`** — Channel when tag removed\n"
            "**`c!clantag removenotify`** — Toggle remove notifications\n"
            "**`c!clantag embed`** — Customize embeds"
        ),
        inline=False
    )
    embed8.add_field(
        name="📝 How does it work?",
        value=(
            "Detects when a user has the **official Discord Clan Tag**\n"
            "of your server next to their name.\n\n"
            "⚠️ Your server must have a Discord Clan."
        ),
        inline=False
    )
    embed8.add_field(
        name="🗑️ Other",
        value="**`c!clantag reset`** — Delete all configuration",
        inline=False
    )
    embed8.set_footer(text="Section: Clan Tag")

    return [embed0, embed1, embed2, embed3, embed4, embed5, embed6, embed7, embed8]


def get_select_options(lang: str, current_index: int = 0) -> Tuple[List[discord.SelectOption], str]:
    """Opciones del menú por idioma. Retorna (options, placeholder)."""
    if lang == "en":
        labels = [
            ("📖 Setup Guide", "Important info before starting", "📖"),
            ("Expressions", "Emojis & stickers", "🤖"),
            ("Threads", "Automatic threads", "⚙️"),
            ("Information", "Users, roles & server", "ℹ️"),
            ("Counting", "Numeric counting channel", "🎰"),
            ("Auto Reactions", "Automatic emoji reactions", "😊"),
            ("Boost Roles", "Roles for boosters (slash)", "💜"),
            ("Vanity Roles", "Vanity URL in custom status", "🔗"),
            ("Clan Tag", "Server clan tag roles", "🏷️"),
        ]
        placeholder = "Choose a help section…"
    else:
        labels = [
            ("📖 Guía de Configuración", "Info importante antes de empezar", "📖"),
            ("Expresiones", "Emojis y stickers", "🤖"),
            ("Hilos", "Hilos automáticos", "⚙️"),
            ("Información", "Usuarios, roles y servidor", "ℹ️"),
            ("Conteo", "Canal de conteo numérico", "🎰"),
            ("Reacciones", "Reacciones automáticas", "😊"),
            ("Boost Roles", "Roles para boosters (slash)", "💜"),
            ("Vanity Roles", "Vanity URL en estado", "🔗"),
            ("Clan Tag", "Roles por tag del clan", "🏷️"),
        ]
        placeholder = "Elige una sección de ayuda…"

    options: List[discord.SelectOption] = []
    for idx, (label, desc, emoji) in enumerate(labels):
        options.append(
            discord.SelectOption(
                label=label, description=desc, value=str(idx), emoji=emoji, default=(idx == current_index)
            )
        )
    return options, placeholder


# ─────────────────────────────────────────────────────────────────────────────
# UI: Select (Secciones) + Botones de idioma
# ─────────────────────────────────────────────────────────────────────────────

class HelpSelect(discord.ui.Select):
    def __init__(self, *, lang: str, current_index: int):
        self.lang = lang
        options, placeholder = get_select_options(lang, current_index)
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        assert isinstance(self.view, HelpView)
        self.view.current_index = index
        # Actualiza el embed mostrado en el idioma actual
        await interaction.response.edit_message(
            embed=self.view.embeds[index],
            view=self.view
        )


class LangButton(discord.ui.Button):
    def __init__(self, lang: str, active: bool = False):
        self.lang = lang
        label = "ES" if lang == "es" else "EN"
        emoji = "🇪🇸" if lang == "es" else "🇺🇸"
        style = discord.ButtonStyle.primary if active else discord.ButtonStyle.secondary
        super().__init__(label=label, emoji=emoji, style=style, disabled=active)

    async def callback(self, interaction: discord.Interaction):
        assert isinstance(self.view, HelpView)
        # Si ya estamos en ese idioma, no hacemos nada visible
        if self.view.lang == self.lang:
            await interaction.response.defer()
            return

        # Reconstruir la vista en el nuevo idioma conservando la sección actual
        new_view = HelpView(lang=self.lang, current_index=self.view.current_index)
        new_embed = new_view.embeds[self.view.current_index]
        await interaction.response.edit_message(embed=new_embed, view=new_view)


class HelpView(discord.ui.View):
    def __init__(self, *, lang: str = "es", current_index: int = 0):
        super().__init__(timeout=180)
        self.lang = lang
        self.current_index = current_index
        self.embeds = get_help_embeds(lang)

        # Menú de secciones
        self.add_item(HelpSelect(lang=self.lang, current_index=self.current_index))
        # Botones de idioma (activo/inactivo)
        self.add_item(LangButton("es", active=(self.lang == "es")))
        self.add_item(LangButton("en", active=(self.lang == "en")))
        # Enlaces legales visibles en todas las secciones de help
        self.add_item(discord.ui.Button(label="Privacy", style=discord.ButtonStyle.link, url=PRIVACY_URL, row=2))
        self.add_item(discord.ui.Button(label="Terms", style=discord.ButtonStyle.link, url=TERMS_URL, row=2))


# ─────────────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────────────

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Reemplaza el help por defecto del bot
        self.bot.remove_command('help')

    @commands.command(name="help")
    async def custom_help(self, ctx: commands.Context):
        """Muestra el menú de ayuda con selector de idioma y secciones."""
        view = HelpView(lang="es", current_index=0)
        await ctx.reply(embed=view.embeds[0], view=view, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

