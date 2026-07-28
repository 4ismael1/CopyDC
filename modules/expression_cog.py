# modules/expression_cog.py
import io
import logging
import os
import random
import re
import string

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageOps

log = logging.getLogger("bot")

# ────────────── UTILIDADES ──────────────
TAG_REGEX = re.compile(r"<a?:\w+:\d+>")
PARSE_REGEX = re.compile(r"<(a?):(\w+):(\d+)>")
EMOJI_MAX_BYTES = 256 * 1024
STICKER_MAX_BYTES = 512 * 1024
EMOJI_MAX_SIDE = 128
STICKER_MAX_SIDE = 320
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_INPUT_PIXELS = 25_000_000
ANIMATED_FORMATS = {"GIF", "APNG"}
IMAGE_ATTACHMENT_FORMATS = (".png", ".apng", ".gif", ".jpg", ".jpeg", ".webp")
STICKER_COPY_HELP = "Ese ya es un sticker. El comando correcto es `!copy` respondiendo al sticker."
IMAGE_COPY_HELP = "Eso es una imagen. Usa `!sticker` para sticker o `!emoji` para emoji."
STICKER_USAGE_HELP = "Responde a una imagen con `!sticker` para subirla como sticker."
EMOJI_COPY_HELP = "Ese ya es un emoji. El comando correcto es `!copy` respondiendo al mensaje."
EMOJI_USAGE_HELP = "Responde a una imagen con `!emoji` para subirla como emoji."
NO_EXPRESSION_HELP = "No detecte imagen, sticker ni emoji en ese mensaje."


def parse_custom_emoji(tag: str):
    m = PARSE_REGEX.fullmatch(tag)
    return (bool(m[1]), m[2], m[3]) if m else None


def clean_name_tokens(tokens):
    return " ".join(t for t in tokens if not TAG_REGEX.fullmatch(t)) or None


def sanitize(raw: str, max_len=32, prefix="emo"):
    clean = re.sub(r"\W", "", raw.lower())
    if len(clean) < 2:
        clean = f"{prefix}{''.join(random.choices(string.ascii_lowercase, k=4))}"
    return clean[:max_len]


async def fetch_bytes(session: aiohttp.ClientSession, url: str, *, max_bytes: int = MAX_INPUT_BYTES):
    async with session.get(url) as response:
        if response.status != 200:
            return None
        if response.content_length is not None and response.content_length > max_bytes:
            raise ValueError("El archivo de origen supera el límite de descarga permitido.")

        chunks = []
        total = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("El archivo de origen supera el límite de descarga permitido.")
            chunks.append(chunk)
        return b"".join(chunks)


def has_expr_perm(member: discord.Member):
    p = member.guild_permissions
    return p.administrator or getattr(p, "manage_expressions", False)


def get_image_attachment(message: discord.Message):
    for attachment in message.attachments:
        content_type = (attachment.content_type or "").lower()
        filename = attachment.filename.lower()
        if content_type.startswith("image/") or filename.endswith(IMAGE_ATTACHMENT_FORMATS):
            return attachment
    return None


def _resample_filter():
    return getattr(Image, "Resampling", Image).LANCZOS


def _save_png_bytes(img: Image.Image) -> bytes:
    with io.BytesIO() as buffer:
        img.save(buffer, format="PNG", optimize=True, compress_level=9)
        return buffer.getvalue()


def _prepare_static_image(img: Image.Image, max_side: int, *, square_canvas: bool) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
    img = img.convert("RGBA" if has_alpha or square_canvas else "RGB")
    img.thumbnail((max_side, max_side), _resample_filter())

    if not square_canvas:
        return img

    canvas = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))
    x = (max_side - img.width) // 2
    y = (max_side - img.height) // 2
    canvas.alpha_composite(img.convert("RGBA"), (x, y))
    return canvas


def compress_static_image_for_discord(
    data: bytes,
    *,
    max_bytes: int,
    max_side: int,
    square_canvas: bool = False,
) -> tuple[bytes, str, bool]:
    if len(data) <= max_bytes:
        try:
            with Image.open(io.BytesIO(data)) as probe:
                if probe.width * probe.height > MAX_INPUT_PIXELS:
                    raise ValueError("La imagen tiene demasiados píxeles para procesarla de forma segura.")
                if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) > 1:
                    return data, ".gif" if probe.format == "GIF" else ".png", False
        except ValueError:
            raise
        except Image.DecompressionBombError as exc:
            raise ValueError("La imagen tiene demasiados píxeles para procesarla de forma segura.") from exc
        except (OSError, SyntaxError):
            return data, ".png", False

    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > MAX_INPUT_PIXELS:
                raise ValueError("La imagen tiene demasiados píxeles para procesarla de forma segura.")
            if (
                img.format in ANIMATED_FORMATS
                or getattr(img, "is_animated", False)
                or getattr(img, "n_frames", 1) > 1
            ):
                if len(data) <= max_bytes:
                    return data, ".gif" if img.format == "GIF" else ".png", False
                raise ValueError(
                    "La imagen animada supera el limite y no puedo optimizar animaciones todavia."
                )

            prepared = _prepare_static_image(img, max_side, square_canvas=square_canvas)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"No pude procesar la imagen: {exc}") from exc

    png_data = _save_png_bytes(prepared)
    if len(png_data) <= max_bytes:
        return png_data, ".png", True

    raise ValueError(
        "La imagen sigue pesando demasiado incluso despues de optimizarla. "
        "Para evitar perder calidad visible, no la reduje mas."
    )


def describe_expression_upload_error(exc: discord.HTTPException, kind: str) -> str:
    raw_text = str(getattr(exc, "text", "") or exc)
    lowered = raw_text.lower()
    code = getattr(exc, "code", None)

    if kind == "sticker" and (
        code == 30039
        or "maximum number of stickers" in lowered
        or ("sticker" in lowered and "maximum" in lowered)
    ):
        return (
            "No pude agregar el sticker porque este servidor ya alcanzo su limite de stickers. "
            "Borra un sticker existente o aumenta el nivel del servidor antes de intentarlo otra vez."
        )

    if kind == "emoji" and (
        code == 30008
        or "maximum number of emojis" in lowered
        or ("emoji" in lowered and "maximum" in lowered)
    ):
        return (
            "No pude agregar el emoji porque este servidor ya alcanzo su limite de emojis. "
            "Borra un emoji existente o aumenta el nivel del servidor antes de intentarlo otra vez."
        )

    if getattr(exc, "status", None) == 400:
        return (
            f"Discord rechazo el {kind}. Puede que el archivo siga superando el limite, "
            "tenga un formato no aceptado o el servidor haya alcanzado su limite."
        )

    return f"No se pudo subir el {kind}: {exc}"


# ────────────── COG DE EXPRESIONES ──────────────
class ExpressionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        timeout = aiohttp.ClientTimeout(total=20, connect=8, sock_read=15)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def cog_unload(self):
        if self.session is not None and not self.session.closed:
            await self.session.close()

    async def _fetch_bytes(self, url: str) -> bytes | None:
        if self.session is None or self.session.closed:
            raise RuntimeError("La sesión HTTP del módulo no está disponible.")
        try:
            return await fetch_bytes(self.session, url)
        except (TimeoutError, aiohttp.ClientError) as exc:
            log.warning("No pude descargar un recurso de expresión: %s", exc)
            return None

    @staticmethod
    async def _read_attachment(attachment: discord.Attachment) -> bytes:
        if attachment.size > MAX_INPUT_BYTES:
            raise ValueError(
                f"El archivo supera el límite de entrada de {MAX_INPUT_BYTES // (1024 * 1024)} MB."
            )
        return await attachment.read()

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
                if st.format not in (
                    discord.StickerFormatType.png,
                    discord.StickerFormatType.apng,
                ) and not st.url.lower().endswith(".gif"):
                    await ctx.reply("Solo puedo copiar stickers PNG, APNG o GIF.", mention_author=False)
                    return

                data = await self._fetch_bytes(str(st.url))
                if not data:
                    await ctx.reply("No pude descargar el sticker.", mention_author=False)
                    return

                name = sanitize(custom_name or st.name, max_len=30, prefix="stk")
                try:
                    data, extension, compressed = compress_static_image_for_discord(
                        data,
                        max_bytes=STICKER_MAX_BYTES,
                        max_side=STICKER_MAX_SIDE,
                        square_canvas=True,
                    )
                    sticker = await ctx.guild.create_sticker(
                        name=name,
                        description="Agregado por bot",
                        emoji="🙂",
                        file=discord.File(io.BytesIO(data), filename=f"sticker{extension}"),
                    )
                    note = " 🛠️" if compressed else ""
                    await ref.reply(
                        f"Sticker `{sticker.name}` agregado al servidor ✅{note}", mention_author=False
                    )
                except ValueError as e:
                    await ctx.reply(str(e), mention_author=False)
                except discord.HTTPException as e:
                    await ctx.reply(describe_expression_upload_error(e, "sticker"), mention_author=False)
                except Exception as e:
                    await ctx.reply(f"Error: {e}", mention_author=False)
                return

            tag = TAG_REGEX.search(ref.content)
            if tag:
                parsed = parse_custom_emoji(tag.group())
                if not parsed:
                    return
                animated, orig_name, eid = parsed
                url = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animated else 'png'}"
                data = await self._fetch_bytes(url)
                if not data:
                    await ctx.reply("No pude descargar el emoji.", mention_author=False)
                    return

                name = sanitize(custom_name or orig_name)
                try:
                    emoji = await ctx.guild.create_custom_emoji(name=name, image=data)
                    await ref.reply(f"Emoji {emoji} (`{name}`) agregado al servidor ✅", mention_author=False)
                except discord.HTTPException as e:
                    await ctx.reply(describe_expression_upload_error(e, "emoji"), mention_author=False)
                except Exception as e:
                    await ctx.reply(f"Error: {e}", mention_author=False)
                return

            if get_image_attachment(ref):
                await ctx.reply(IMAGE_COPY_HELP, mention_author=False)
                return

            await ctx.reply("No encontré sticker ni emoji en ese mensaje.", mention_author=False)
            return

        if not args:
            await ctx.reply(
                "Responde a un mensaje o pon un emoji personalizado para copiar.", mention_author=False
            )
            return

        parsed = parse_custom_emoji(args[0])
        if not parsed:
            await ctx.reply(
                "El primer argumento debe ser un emoji personalizado válido.", mention_author=False
            )
            return

        animated, orig_name, eid = parsed
        url = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animated else 'png'}"
        data = await self._fetch_bytes(url)
        if not data:
            await ctx.reply("No pude descargar el emoji.", mention_author=False)
            return

        name = sanitize(clean_name_tokens(args[1:]) or orig_name)
        try:
            emoji = await ctx.guild.create_custom_emoji(name=name, image=data)
            await ctx.reply(f"Emoji {emoji} (`{name}`) agregado al servidor ✅", mention_author=False)
        except discord.HTTPException as e:
            await ctx.reply(describe_expression_upload_error(e, "emoji"), mention_author=False)
        except Exception as e:
            await ctx.reply(f"Error: {e}", mention_author=False)

    @commands.command(aliases=["emojis"])
    @commands.guild_only()
    async def emoji(self, ctx: commands.Context, *, nombre: str | None = None):
        """Sube un archivo adjunto (PNG, GIF, JPG) como un emoji."""
        if not isinstance(ctx.author, discord.Member) or not has_expr_perm(ctx.author):
            await ctx.reply("Necesitas el permiso de 'Gestionar Expresiones'.", mention_author=False)
            return

        if not ctx.message.reference:
            await ctx.reply(EMOJI_USAGE_HELP, mention_author=False)
            return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if ref.stickers:
            await ctx.reply(STICKER_COPY_HELP, mention_author=False)
            return
        if TAG_REGEX.search(ref.content):
            await ctx.reply(EMOJI_COPY_HELP, mention_author=False)
            return

        if not ref.attachments:
            await ctx.reply(NO_EXPRESSION_HELP, mention_author=False)
            return

        att = ref.attachments[0]
        allowed_formats = (".png", ".apng", ".gif", ".jpg", ".jpeg", ".webp")
        if not att.filename.lower().endswith(allowed_formats):
            await ctx.reply(f"Formato no soportado. Usa {', '.join(allowed_formats)}.", mention_author=False)
            return

        try:
            data = await self._read_attachment(att)
        except ValueError as exc:
            await ctx.reply(str(exc), mention_author=False)
            return
        base_name = os.path.splitext(att.filename)[0]
        new_name = sanitize(nombre or base_name)

        try:
            data, extension, compressed = compress_static_image_for_discord(
                data,
                max_bytes=EMOJI_MAX_BYTES,
                max_side=EMOJI_MAX_SIDE,
            )
            new_emoji = await ctx.guild.create_custom_emoji(name=new_name, image=data)
            note = " 🛠️" if compressed else ""
            await ref.reply(
                f"Emoji {new_emoji} (`{new_name}`) agregado al servidor ✅{note}", mention_author=False
            )
        except ValueError as e:
            await ctx.reply(str(e), mention_author=False)
        except discord.HTTPException as e:
            await ctx.reply(describe_expression_upload_error(e, "emoji"), mention_author=False)
        except Exception as e:
            await ctx.reply(f"No se pudo subir el emoji: {e}", mention_author=False)

    @commands.command(aliases=["stickers", "stk"])
    @commands.guild_only()
    async def sticker(self, ctx: commands.Context, *, nombre: str | None = None):
        """Sube un archivo adjunto como sticker (convierte JPG a PNG si es necesario)."""
        if not isinstance(ctx.author, discord.Member) or not has_expr_perm(ctx.author):
            await ctx.reply("Necesitas el permiso de 'Gestionar Expresiones'.", mention_author=False)
            return

        if not ctx.message.reference:
            await ctx.reply(STICKER_USAGE_HELP, mention_author=False)
            return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if ref.stickers:
            await ctx.reply(STICKER_COPY_HELP, mention_author=False)
            return
        if TAG_REGEX.search(ref.content):
            await ctx.reply(EMOJI_COPY_HELP, mention_author=False)
            return

        if not ref.attachments:
            await ctx.reply(NO_EXPRESSION_HELP, mention_author=False)
            return

        att = ref.attachments[0]
        allowed_formats = (".png", ".apng", ".gif", ".jpg", ".jpeg", ".webp")
        if not att.filename.lower().endswith(allowed_formats):
            await ctx.reply(f"Formato no soportado. Usa {', '.join(allowed_formats)}.", mention_author=False)
            return

        try:
            data = await self._read_attachment(att)
        except ValueError as exc:
            await ctx.reply(str(exc), mention_author=False)
            return
        base_name = os.path.splitext(att.filename)[0]
        new_name = sanitize(nombre or base_name, max_len=30, prefix="stk")

        try:
            data, extension, compressed = compress_static_image_for_discord(
                data,
                max_bytes=STICKER_MAX_BYTES,
                max_side=STICKER_MAX_SIDE,
                square_canvas=True,
            )
            new_sticker = await ctx.guild.create_sticker(
                name=new_name,
                description="Agregado por bot",
                emoji="🙂",
                file=discord.File(io.BytesIO(data), filename=f"{new_name}{extension}"),
            )
            note = " 🛠️" if compressed else ""
            await ref.reply(
                f"Sticker `{new_sticker.name}` agregado al servidor ✅{note}", mention_author=False
            )
        except ValueError as e:
            await ctx.reply(str(e), mention_author=False)
        except discord.HTTPException as e:
            await ctx.reply(describe_expression_upload_error(e, "sticker"), mention_author=False)
        except Exception as e:
            await ctx.reply(f"No se pudo subir el sticker: {e}", mention_author=False)

    # ---- NUEVO COMANDO 'GET' ----
    @commands.command(name="get", aliases=["robar", "extract"])
    @commands.guild_only()
    async def get_expression(self, ctx: commands.Context):
        """Envía la imagen de un sticker o emoji de un mensaje respondido."""
        if not ctx.message.reference:
            await ctx.reply(
                "Debes responder a un mensaje que contenga un sticker o emoji personalizado.",
                mention_author=False,
            )
            return

        ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)

        # Primero, buscamos un sticker
        if ref.stickers:
            sticker = ref.stickers[0]
            url = sticker.url
            # Los stickers de Discord suelen ser PNG, pero por si acaso, forzamos la extensión.
            filename = sanitize(sticker.name, max_len=30, prefix="stk") + ".png"

            data = await self._fetch_bytes(str(url))
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

            data = await self._fetch_bytes(url)
            if data:
                await ctx.reply(file=discord.File(io.BytesIO(data), filename=filename), mention_author=False)
            else:
                await ctx.reply("No pude descargar la imagen del emoji.", mention_author=False)
            return

        await ctx.reply(
            "No encontré ningún sticker o emoji personalizado en el mensaje respondido.", mention_author=False
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ExpressionCog(bot))
