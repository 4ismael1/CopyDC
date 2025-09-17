# modules/expression_cog.py
import os
import io
import re
import string
import random
import aiohttp
import discord
from discord.ext import commands
from PIL import Image

# ────────────── UTILIDADES ──────────────
TAG_REGEX = re.compile(r'<a?:\w+:\d+>')
PARSE_REGEX = re.compile(r'<(a?):(\w+):(\d+)>')

def parse_custom_emoji(tag: str):
    m = PARSE_REGEX.fullmatch(tag)
    return (bool(m[1]), m[2], m[3]) if m else None

def clean_name_tokens(tokens):
    return " ".join(t for t in tokens if not TAG_REGEX.fullmatch(t)) or None

def sanitize(raw: str, max_len=32, prefix="emo"):
    clean = re.sub(r'\W', '', raw.lower())
    if len(clean) < 2:
        clean = f"{prefix}{''.join(random.choices(string.ascii_lowercase, k=4))}"
    return clean[:max_len]

async def fetch_bytes(url: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.read() if r.status == 200 else None

def has_expr_perm(member: discord.Member):
    p = member.guild_permissions
    return p.administrator or getattr(p, "manage_expressions", False)

# ────────────── COG DE EXPRESIONES ──────────────
class ExpressionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ... (los comandos 'copy', 'emoji', 'sticker' no cambian) ...
    @commands.command()
    @commands.guild_only()
    async def copy(self, ctx: commands.Context, *args):
        if not isinstance(ctx.author, discord.Member) or not has_expr_perm(ctx.author):
            await ctx.reply("Necesitas el permiso de 'Gestionar Expresiones'.", mention_author=False)
            return

        if ctx.message.reference:
            ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            custom_name = clean_name_tokens(args)

            if ref.stickers:
                st = ref.stickers[0]
                if st.format not in (discord.StickerFormatType.png, discord.StickerFormatType.apng) and not st.url.lower().endswith(".gif"):
                    await ctx.reply("Solo puedo copiar stickers PNG, APNG o GIF.", mention_author=False)
                    return
                
                data = await fetch_bytes(str(st.url))
                if not data:
                    await ctx.reply("No pude descargar el sticker.", mention_author=False)
                    return

                name = sanitize(custom_name or st.name, max_len=30, prefix="stk")
                try:
                    sticker = await ctx.guild.create_sticker(name=name, description="Agregado por bot", emoji="🙂", file=discord.File(io.BytesIO(data), filename="sticker.png"))
                    await ref.reply(f'Sticker `{sticker.name}` agregado al servidor ✅', mention_author=False)
                except Exception as e:
                    await ctx.reply(f"Error: {e}", mention_author=False)
                return

            tag = TAG_REGEX.search(ref.content)
            if tag:
                parsed = parse_custom_emoji(tag.group())
                if not parsed: return
                animated, orig_name, eid = parsed
                url = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animated else 'png'}"
                data = await fetch_bytes(url)
                if not data:
                    await ctx.reply("No pude descargar el emoji.", mention_author=False)
                    return

                name = sanitize(custom_name or orig_name)
                try:
                    emoji = await ctx.guild.create_custom_emoji(name=name, image=data)
                    await ref.reply(f'Emoji {emoji} (`{name}`) agregado al servidor ✅', mention_author=False)
                except Exception as e:
                    await ctx.reply(f"Error: {e}", mention_author=False)
                return
            
            await ctx.reply("No encontré sticker ni emoji en ese mensaje.", mention_author=False)
            return

        if not args:
            await ctx.reply("Responde a un mensaje o pon un emoji personalizado para copiar.", mention_author=False)
            return

        parsed = parse_custom_emoji(args[0])
        if not parsed:
            await ctx.reply("El primer argumento debe ser un emoji personalizado válido.", mention_author=False)
            return

        animated, orig_name, eid = parsed
        url = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animated else 'png'}"
        data = await fetch_bytes(url)
        if not data:
            await ctx.reply("No pude descargar el emoji.", mention_author=False)
            return

        name = sanitize(clean_name_tokens(args[1:]) or orig_name)
        try:
            emoji = await ctx.guild.create_custom_emoji(name=name, image=data)
            await ctx.reply(f'Emoji {emoji} (`{name}`) agregado al servidor ✅', mention_author=False)
        except Exception as e:
            await ctx.reply(f"Error: {e}", mention_author=False)

    @commands.command()
    @commands.guild_only()
    async def emoji(self, ctx: commands.Context, *, nombre: str | None = None):
        """Sube un archivo adjunto (PNG, GIF, JPG) como un emoji."""
        if not isinstance(ctx.author, discord.Member) or not has_expr_perm(ctx.author):
            await ctx.reply("Necesitas el permiso de 'Gestionar Expresiones'.", mention_author=False)
            return

        if not ctx.message.reference:
            await ctx.reply("Responde al archivo que quieres subir como emoji.", mention_author=False)
            return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if not ref.attachments:
            await ctx.reply("Ese mensaje no tiene ningún archivo adjunto.", mention_author=False)
            return

        att = ref.attachments[0]
        if att.size > 262144: # 256 KiB
            await ctx.reply("El archivo pesa más de 256 KB. Discord no lo aceptará.", mention_author=False)
            return

        data = await att.read()
        base_name = os.path.splitext(att.filename)[0]
        new_name = sanitize(nombre or base_name)

        try:
            new_emoji = await ctx.guild.create_custom_emoji(name=new_name, image=data)
            await ref.reply(f'Emoji {new_emoji} (`{new_name}`) agregado al servidor ✅', mention_author=False)
        except Exception as e:
            await ctx.reply(f"No se pudo subir el emoji: {e}", mention_author=False)

    @commands.command()
    @commands.guild_only()
    async def sticker(self, ctx: commands.Context, *, nombre: str | None = None):
        """Sube un archivo adjunto como sticker (convierte JPG a PNG si es necesario)."""
        if not isinstance(ctx.author, discord.Member) or not has_expr_perm(ctx.author):
            await ctx.reply("Necesitas el permiso de 'Gestionar Expresiones'.", mention_author=False)
            return

        if not ctx.message.reference:
            await ctx.reply("Responde al archivo que quieres subir como sticker.", mention_author=False)
            return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if not ref.attachments:
            await ctx.reply("Ese mensaje no tiene ningún archivo adjunto.", mention_author=False)
            return

        att = ref.attachments[0]
        if att.size > 524288: # 512 KiB
            await ctx.reply("El archivo pesa más de 512 KiB. Discord no lo aceptará.", mention_author=False)
            return

        allowed_formats = (".png", ".apng", ".gif", ".jpg", ".jpeg")
        if not att.filename.lower().endswith(allowed_formats):
            await ctx.reply(f"Formato no soportado. Usa {', '.join(allowed_formats)}.", mention_author=False)
            return

        data = await att.read()
        final_filename = att.filename

        if att.filename.lower().endswith((".jpg", ".jpeg")):
            try:
                with Image.open(io.BytesIO(data)) as img:
                    with io.BytesIO() as buffer:
                        img.save(buffer, format="PNG")
                        buffer.seek(0)
                        data = buffer.read()
                final_filename = os.path.splitext(att.filename)[0] + ".png"
            except Exception as e:
                await ctx.reply(f"No pude convertir la imagen JPG a PNG: {e}", mention_author=False)
                return

        base_name = os.path.splitext(att.filename)[0]
        new_name = sanitize(nombre or base_name, max_len=30, prefix="stk")

        try:
            new_sticker = await ctx.guild.create_sticker(
                name=new_name,
                description="Agregado por bot",
                emoji="🙂",
                file=discord.File(io.BytesIO(data), filename=final_filename)
            )
            await ref.reply(f'Sticker `{new_sticker.name}` agregado al servidor ✅', mention_author=False)
        except Exception as e:
            await ctx.reply(f"No se pudo subir el sticker: {e}", mention_author=False)
            
    # ---- NUEVO COMANDO 'GET' ----
    @commands.command(name="get", aliases=["robar", "extract"])
    @commands.guild_only()
    async def get_expression(self, ctx: commands.Context):
        """Envía la imagen de un sticker o emoji de un mensaje respondido."""
        if not ctx.message.reference:
            await ctx.reply("Debes responder a un mensaje que contenga un sticker o emoji personalizado.", mention_author=False)
            return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        # Primero, buscamos un sticker
        if ref.stickers:
            sticker = ref.stickers[0]
            url = sticker.url
            # Los stickers de Discord suelen ser PNG, pero por si acaso, forzamos la extensión.
            filename = sanitize(sticker.name, max_len=30, prefix="stk") + ".png"
            
            data = await fetch_bytes(url)
            if data:
                await ctx.reply(file=discord.File(io.BytesIO(data), filename=filename), mention_author=False)
            else:
                await ctx.reply("No pude descargar la imagen del sticker.", mention_author=False)
            return

        # Si no hay sticker, buscamos un emoji
        tag = TAG_REGEX.search(ref.content)
        if tag:
            parsed = parse_custom_emoji(tag.group())
            if not parsed:
                await ctx.reply("No pude identificar el emoji personalizado.", mention_author=False)
                return
            
            animated, name, eid = parsed
            extension = "gif" if animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{eid}.{extension}"
            filename = f"{name}.{extension}"

            data = await fetch_bytes(url)
            if data:
                await ctx.reply(file=discord.File(io.BytesIO(data), filename=filename), mention_author=False)
            else:
                await ctx.reply("No pude descargar la imagen del emoji.", mention_author=False)
            return

        await ctx.reply("No encontré ningún sticker o emoji personalizado en el mensaje respondido.", mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(ExpressionCog(bot))