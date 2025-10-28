# modules/auto_react_cog.py
import logging
import discord
import json
import re
from discord.ext import commands
import database as db

log = logging.getLogger("bot")

class AutoReactCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="react", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def react(self, ctx: commands.Context):
        """Gestiona reacciones automáticas por palabras clave."""
        await ctx.reply(
            "Comando inválido. Usa `c!react add`, `c!react remove`, `c!react list` o `c!react clear`.",
            mention_author=False
        )

    @react.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def react_add(self, ctx: commands.Context, trigger_word: str, *emojis: str):
        """
        Configura reacciones automáticas para una palabra.
        
        Ejemplo: c!react add wlc 👋 💜 ✨ 🎉
        """
        if not emojis:
            await ctx.reply("❌ Debes proporcionar al menos un emoji.", mention_author=False)
            return

        if len(emojis) > 20:
            await ctx.reply("❌ Puedes agregar máximo 20 reacciones por palabra.", mention_author=False)
            return

        trigger_word = trigger_word.lower()

        # Validar emojis
        validated_emojis = []
        for emoji in emojis:
            # Intentar como emoji unicode
            try:
                await ctx.message.add_reaction(emoji)
                validated_emojis.append(emoji)
                await ctx.message.remove_reaction(emoji, ctx.guild.me)
            except (discord.HTTPException, discord.NotFound):
                # Intentar como emoji custom
                emoji_match = re.match(r'<a?:(\w+):(\d+)>', emoji)
                if emoji_match:
                    emoji_obj = discord.utils.get(ctx.guild.emojis, id=int(emoji_match.group(2)))
                    if emoji_obj:
                        validated_emojis.append(emoji)
                    else:
                        await ctx.reply(
                            f"⚠️ El emoji `{emoji}` no es válido o no está disponible en este servidor. Se omitirá.",
                            mention_author=False
                        )
                else:
                    await ctx.reply(
                        f"⚠️ El emoji `{emoji}` no es válido. Se omitirá.",
                        mention_author=False
                    )

        if not validated_emojis:
            await ctx.reply("❌ Ninguno de los emojis proporcionados es válido.", mention_author=False)
            return

        # Guardar en la base de datos
        db.add_auto_reaction(ctx.guild.id, trigger_word, validated_emojis)
        
        emoji_preview = " ".join(validated_emojis)
        await ctx.reply(
            f"✅ Reacciones automáticas configuradas para **\"{trigger_word}\"**\n"
            f"Reacciones: {emoji_preview}",
            mention_author=False
        )

    @react.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def react_remove(self, ctx: commands.Context, trigger_word: str):
        """
        Elimina las reacciones automáticas de una palabra.
        
        Ejemplo: c!react remove wlc
        """
        trigger_word = trigger_word.lower()
        
        # Verificar si existe
        config = db.get_auto_reaction(ctx.guild.id, trigger_word)
        if not config:
            await ctx.reply(
                f"❌ No hay reacciones configuradas para **\"{trigger_word}\"**.",
                mention_author=False
            )
            return

        db.remove_auto_reaction(ctx.guild.id, trigger_word)
        await ctx.reply(
            f"✅ Reacciones automáticas eliminadas para **\"{trigger_word}\"**.",
            mention_author=False
        )

    @react.command(name="list")
    async def react_list(self, ctx: commands.Context):
        """Muestra todas las reacciones automáticas configuradas en el servidor."""
        configs = db.get_all_auto_reactions(ctx.guild.id)
        
        if not configs:
            await ctx.reply(
                "ℹ️ No hay reacciones automáticas configuradas en este servidor.",
                mention_author=False
            )
            return

        embed = discord.Embed(
            title="😊 Reacciones Automáticas Configuradas",
            description=f"Total: **{len(configs)}** palabra(s) configurada(s)",
            color=0xE74C3C
        )

        # Agrupar en chunks de 10 para no hacer el embed muy largo
        for i, config in enumerate(configs[:25], 1):  # Máximo 25 para no exceder límites
            trigger = config['trigger_word']
            emojis_json = config['emojis']
            try:
                emojis_list = json.loads(emojis_json)
                emoji_preview = " ".join(emojis_list)
            except:
                emoji_preview = "Error al cargar emojis"
            
            embed.add_field(
                name=f"{i}. \"{trigger}\"",
                value=emoji_preview,
                inline=False
            )

        if len(configs) > 25:
            embed.set_footer(text=f"Mostrando primeras 25 de {len(configs)} configuraciones")
        else:
            embed.set_footer(text=f"{len(configs)} configuración(es) en total")

        await ctx.reply(embed=embed, mention_author=False)

    @react.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def react_clear(self, ctx: commands.Context):
        """Elimina TODAS las reacciones automáticas del servidor."""
        configs = db.get_all_auto_reactions(ctx.guild.id)
        
        if not configs:
            await ctx.reply(
                "ℹ️ No hay reacciones automáticas configuradas en este servidor.",
                mention_author=False
            )
            return

        # Confirmación
        count = len(configs)
        await ctx.reply(
            f"⚠️ ¿Estás seguro de que quieres eliminar **{count}** configuración(es) de reacciones automáticas?\n"
            f"Responde con `confirmar` en los próximos 30 segundos para continuar.",
            mention_author=False
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "confirmar"

        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except:
            await ctx.send("❌ Tiempo agotado. Operación cancelada.")
            return

        db.clear_auto_reactions(ctx.guild.id)
        await ctx.send(f"✅ Se eliminaron **{count}** configuración(es) de reacciones automáticas.")

    @commands.Cog.listener("on_message")
    async def auto_react_listener(self, message: discord.Message):
        """Escucha mensajes y aplica reacciones automáticas según las configuraciones."""
        # Ignorar bots y mensajes fuera de servidores
        if message.author.bot or not message.guild:
            return

        # Ignorar si no hay contenido
        if not message.content:
            return

        # Obtener todas las configuraciones del servidor
        configs = db.get_all_auto_reactions(message.guild.id)
        if not configs:
            return

        content_lower = message.content.lower()

        # Buscar coincidencias
        for config in configs:
            trigger = config['trigger_word']
            
            # Buscar la palabra como palabra completa (con word boundaries)
            pattern = r'\b' + re.escape(trigger) + r'\b'
            if re.search(pattern, content_lower):
                try:
                    emojis_list = json.loads(config['emojis'])
                    
                    # Aplicar reacciones
                    for emoji in emojis_list:
                        try:
                            await message.add_reaction(emoji)
                        except discord.HTTPException as e:
                            log.warning(
                                f"No se pudo agregar reacción '{emoji}' en {message.guild.name}: {e}"
                            )
                        except Exception as e:
                            log.error(
                                f"Error inesperado al reaccionar en {message.guild.name}: {e}"
                            )
                
                except json.JSONDecodeError:
                    log.error(f"Error al decodificar emojis para trigger '{trigger}' en guild {message.guild.id}")
                except Exception as e:
                    log.error(f"Error en auto_react_listener: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReactCog(bot))
