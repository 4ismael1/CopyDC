import ast
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest
from PIL import Image

import localization
import sticker_processing as processing
from modules.expression_cog import ExpressionCog, StickerPreview
from sticker_processing import StickerProcessingError, prepare_sticker_attachment


def encode(image, fmt="PNG", **kwargs):
    stream = io.BytesIO()
    image.save(stream, format=fmt, **kwargs)
    return stream.getvalue()


def decode(result):
    return Image.open(io.BytesIO(result.data)).convert("RGBA")


def test_transparent_margins_do_not_shrink_artwork():
    image = Image.new("RGBA", (2000, 2000))
    image.paste((255, 0, 0, 255), (800, 800, 1200, 1200))
    result = prepare_sticker_attachment(encode(image))
    assert decode(result).size == (320, 320)
    assert decode(result).getchannel("A").getbbox() == (0, 0, 320, 320)
    assert result.warnings == ()


def test_small_image_is_enlarged_but_requires_confirmation():
    result = prepare_sticker_attachment(encode(Image.new("RGB", (64, 64), "red")))
    assert result.content_size == (320, 320)
    assert "expression.sticker_warn_upscale" in result.warnings


@pytest.mark.parametrize(
    "size,visible", [((1600, 200), (320, 40)), ((200, 1600), (40, 320)), ((640, 320), (320, 160))]
)
def test_aspect_ratio_preserved_and_narrow_artwork_warned(size, visible):
    result = prepare_sticker_attachment(encode(Image.new("RGB", size, "blue")))
    assert result.content_size == visible
    assert ("expression.sticker_warn_small" in result.warnings) == (min(visible) < 96)


def test_opaque_white_background_is_not_cropped():
    image = Image.new("RGB", (320, 320), "white")
    image.paste("red", (100, 100, 200, 200))
    result = prepare_sticker_attachment(encode(image))
    assert decode(result).getpixel((0, 0)) == (255, 255, 255, 255)


def test_nonzero_transparency_is_preserved_not_used_as_crop_threshold():
    image = Image.new("RGBA", (320, 320), (0, 0, 0, 1))
    image.paste((255, 0, 0, 255), (128, 128, 192, 192))
    result = prepare_sticker_attachment(encode(image))
    assert decode(result).getpixel((0, 0))[3] == 1
    assert result.content_size == (64, 64)
    assert "expression.sticker_warn_small" in result.warnings


def test_palette_transparency_is_detected():
    image = Image.new("P", (320, 320), 0)
    image.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
    image.paste(1, (60, 60, 260, 260))
    result = prepare_sticker_attachment(encode(image, transparency=0))
    assert decode(result).getpixel((0, 0)) == (255, 0, 0, 255)


def test_exif_orientation_applied_before_fitting():
    image = Image.new("RGB", (80, 160), "red")
    exif = Image.Exif()
    exif[274] = 6
    result = prepare_sticker_attachment(encode(image, "JPEG", exif=exif))
    assert result.content_size == (320, 160)


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF"])
def test_static_formats_are_real_png(fmt):
    result = prepare_sticker_attachment(encode(Image.new("RGB", (320, 320), "red"), fmt))
    assert result.extension == ".png" and result.data.startswith(b"\x89PNG")
    assert not result.animated


def test_png_lossless_at_target_size_and_under_limit():
    import random

    raw = random.Random(42).randbytes(320 * 320 * 4)
    image = Image.frombytes("RGBA", (320, 320), raw)
    result = prepare_sticker_attachment(encode(image))
    assert decode(result).tobytes() == raw
    assert len(result.data) <= processing.MAX_BYTES


def test_empty_and_invalid_inputs_rejected():
    with pytest.raises(StickerProcessingError, match="sticker_empty"):
        prepare_sticker_attachment(encode(Image.new("RGBA", (320, 320))))
    for data in (b"not an image", b"", encode(Image.new("RGB", (320, 320)))[:40]):
        with pytest.raises(StickerProcessingError, match="sticker_invalid"):
            prepare_sticker_attachment(data)


def test_no_further_shrink_if_output_exceeds_limit(monkeypatch):
    monkeypatch.setattr(processing, "MAX_BYTES", 1)
    with pytest.raises(StickerProcessingError, match="sticker_static_large"):
        prepare_sticker_attachment(encode(Image.new("RGB", (320, 320), "red")))


def test_pixel_and_file_limits_checked(monkeypatch):
    monkeypatch.setattr(processing, "MAX_PIXELS", 100)
    with pytest.raises(StickerProcessingError, match="image_pixels"):
        prepare_sticker_attachment(encode(Image.new("RGB", (11, 10))))
    monkeypatch.setattr(processing, "MAX_INPUT_BYTES", 3)
    with pytest.raises(StickerProcessingError, match="input_large"):
        prepare_sticker_attachment(b"1234")


def animation(fmt="GIF", size=(320, 320), duration=100):
    frames = [Image.new("RGBA", size, color) for color in ("red", "blue")]
    return encode(frames[0], fmt, save_all=True, append_images=frames[1:], duration=duration, loop=0)


@pytest.mark.parametrize("fmt,extension", [("GIF", ".gif"), ("PNG", ".png")])
def test_compliant_animation_passed_through_byte_for_byte(fmt, extension):
    data = animation(fmt)
    result = prepare_sticker_attachment(data)
    assert result.data == data and result.extension == extension
    assert result.animated and not result.changed


@pytest.mark.parametrize(
    "data,key",
    [
        (animation(size=(160, 160)), "animation_dimensions"),
        (animation(duration=3000), "animation_duration"),
        (animation(duration=0), "animation_timing"),
        (animation("WEBP"), "animation_format"),
    ],
)
def test_incompatible_animation_not_flattened(data, key):
    with pytest.raises(StickerProcessingError, match=key):
        prepare_sticker_attachment(data)


def test_animation_limits(monkeypatch):
    data = animation()
    monkeypatch.setattr(processing, "MAX_BYTES", len(data) - 1)
    with pytest.raises(StickerProcessingError, match="animation_large"):
        prepare_sticker_attachment(data)
    monkeypatch.setattr(processing, "MAX_BYTES", len(data))
    monkeypatch.setattr(processing, "MAX_ANIMATION_FRAMES", 1)
    with pytest.raises(StickerProcessingError, match="animation_complex"):
        prepare_sticker_attachment(data)


def test_all_processing_translation_keys_exist():
    tree = ast.parse(Path(processing.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("expression.")
        ):
            for language in ("es", "en"):
                assert node.value in localization.catalog_keys(language)


def context():
    author = SimpleNamespace(
        id=10, guild_permissions=SimpleNamespace(manage_expressions=True, administrator=False)
    )
    guild = SimpleNamespace(
        id=20,
        preferred_locale="es-ES",
        create_sticker=AsyncMock(return_value=SimpleNamespace(name="sticker")),
    )
    return SimpleNamespace(author=author, guild=guild, reply=AsyncMock(), send=AsyncMock())


@pytest.mark.asyncio
async def test_conversion_offloaded_to_thread_and_semaphore_released():
    cog = ExpressionCog(SimpleNamespace())
    attachment = SimpleNamespace(size=10, read=AsyncMock(return_value=b"test"))
    with patch(
        "modules.expression_cog.asyncio.to_thread", new_callable=AsyncMock, return_value="prepared"
    ) as threaded:
        assert await cog.convert_sticker_attachment(attachment) == "prepared"
        threaded.assert_awaited_once_with(prepare_sticker_attachment, b"test")
    assert not cog.sticker_processing.locked()


@pytest.mark.asyncio
async def test_preview_requires_owner_and_current_permissions():
    ctx = context()
    cog = ExpressionCog(SimpleNamespace())
    prepared = prepare_sticker_attachment(encode(Image.new("RGB", (32, 32), "red")))
    view = StickerPreview(cog, ctx, SimpleNamespace(), "name", prepared)
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=11), guild=ctx.guild, response=SimpleNamespace(send_message=AsyncMock())
    )
    assert not await view.interaction_check(interaction)
    interaction.user = ctx.author
    ctx.author.guild_permissions.manage_expressions = False
    assert not await view.interaction_check(interaction)
    ctx.guild.create_sticker.assert_not_called()
    view.finish()


@pytest.mark.asyncio
async def test_confirmation_can_only_upload_once():
    ctx = context()
    cog = ExpressionCog(SimpleNamespace())
    cog.upload_prepared_sticker = AsyncMock(return_value=True)
    result = prepare_sticker_attachment(encode(Image.new("RGB", (32, 32), "red")))
    view = StickerPreview(cog, ctx, SimpleNamespace(), "name", result)
    cog.sticker_previews[(20, 10)] = view
    interaction = SimpleNamespace(
        user=ctx.author,
        guild=ctx.guild,
        response=SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    await view.confirm.callback(interaction)
    await view.confirm.callback(interaction)
    cog.upload_prepared_sticker.assert_awaited_once()
    assert view.prepared is None and not cog.sticker_previews


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [True, False])
async def test_cancel_and_timeout_never_upload(cancel):
    ctx = context()
    cog = ExpressionCog(SimpleNamespace())
    result = prepare_sticker_attachment(encode(Image.new("RGB", (32, 32), "red")))
    view = StickerPreview(cog, ctx, SimpleNamespace(), "name", result)
    view.message = SimpleNamespace(edit=AsyncMock())
    cog.sticker_previews[(20, 10)] = view
    if cancel:
        interaction = SimpleNamespace(guild=ctx.guild, response=SimpleNamespace(edit_message=AsyncMock()))
        await view.cancel.callback(interaction)
    else:
        await view.on_timeout()
    assert not cog.sticker_previews and view.prepared is None
    assert all(item.disabled for item in view.children)
    ctx.guild.create_sticker.assert_not_called()


@pytest.mark.asyncio
async def test_failed_success_notification_does_not_repeat_upload():
    ctx = context()
    cog = ExpressionCog(SimpleNamespace())
    ref = SimpleNamespace(
        reply=AsyncMock(
            side_effect=discord.NotFound(SimpleNamespace(status=404, reason="missing"), "missing")
        )
    )
    result = prepare_sticker_attachment(encode(Image.new("RGB", (320, 320), "red")))
    assert await cog.upload_prepared_sticker(ctx, ref, "name", result, ctx.author)
    ctx.guild.create_sticker.assert_awaited_once()
    ctx.send.assert_awaited_once()


def test_emoji_and_copy_still_use_original_processing_paths():
    tree = ast.parse(Path("modules/expression_cog.py").read_text(encoding="utf-8"))
    methods = {
        node.name: ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
    }
    for method in ("copy", "emoji"):
        assert "compress_static_image_for_discord(" in methods[method]
        assert "convert_sticker_attachment(" not in methods[method]
    assert "convert_sticker_attachment(" in methods["sticker"]
    assert "compress_static_image_for_discord(" not in methods["sticker"]


@pytest.mark.asyncio
@pytest.mark.parametrize("side,needs_preview", [(320, False), (64, True)])
async def test_sticker_command_routes_risky_images_to_preview_without_upload(side, needs_preview):
    ctx = context()
    member = Mock(spec=discord.Member)
    member.id = ctx.author.id
    member.guild_permissions = ctx.author.guild_permissions
    ctx.author = member
    data = encode(Image.new("RGB", (side, side), "red"))
    attachment = SimpleNamespace(filename="image.png", size=len(data), read=AsyncMock(return_value=data))
    ref = SimpleNamespace(stickers=[], content="", attachments=[attachment], reply=AsyncMock())
    ctx.message = SimpleNamespace(reference=SimpleNamespace(message_id=1))
    ctx.channel = SimpleNamespace(fetch_message=AsyncMock(return_value=ref))
    cog = ExpressionCog(SimpleNamespace())
    cog.preview_sticker = AsyncMock()
    with patch("modules.expression_cog.compress_static_image_for_discord") as old_processor:
        await cog.sticker.callback(cog, ctx, nombre="sample")
        old_processor.assert_not_called()
    assert cog.preview_sticker.await_count == int(needs_preview)
    assert ctx.guild.create_sticker.await_count == int(not needs_preview)


@pytest.mark.asyncio
async def test_preview_replaces_previous_request_without_uploading():
    ctx = context()
    cog = ExpressionCog(SimpleNamespace())
    ref = SimpleNamespace()
    result = prepare_sticker_attachment(encode(Image.new("RGB", (64, 64), "red")))
    await cog.preview_sticker(ctx, ref, "first", result)
    previous = cog.sticker_previews[(20, 10)]
    await cog.preview_sticker(ctx, ref, "second", result)
    assert previous.prepared is None and previous.is_finished()
    assert cog.sticker_previews[(20, 10)].name == "second"
    ctx.guild.create_sticker.assert_not_called()
    await cog.cog_unload()


@pytest.mark.asyncio
async def test_processing_error_also_releases_concurrency_slot():
    cog = ExpressionCog(SimpleNamespace())
    attachment = SimpleNamespace(size=10, read=AsyncMock(return_value=b"invalid"))
    with pytest.raises(StickerProcessingError):
        await cog.convert_sticker_attachment(attachment)
    assert not cog.sticker_processing.locked()
