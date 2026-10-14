"""Conversion of attachments to stickers; not used by emoji or copy commands."""

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

SIDE = 320
MAX_BYTES = 512 * 1024
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_ANIMATION_FRAMES = 300
MAX_ANIMATION_PIXELS = 32_000_000


class StickerProcessingError(ValueError):
    def __init__(self, key):
        self.key = key
        super().__init__(key)


@dataclass(frozen=True)
class PreparedSticker:
    data: bytes
    extension: str
    preview: bytes
    warnings: tuple[str, ...]
    content_size: tuple[int, int]
    changed: bool
    animated: bool = False


def _png(image):
    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG", optimize=True, compress_level=9)
        return buffer.getvalue()


def _visibility(image):
    """Only a warning heuristic; faint pixels are NEVER cropped using this threshold."""
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bbox is None:
        return (0, 0), ["expression.sticker_warn_faint"]
    size = bbox[2] - bbox[0], bbox[3] - bbox[1]
    warnings = []
    if min(size) < 96 or max(size) < 160:
        warnings.append("expression.sticker_warn_small")
    return size, warnings


def _animation(image, data):
    # Passing compliant originals through avoids destroying timing, disposal or transparency.
    if image.format not in {"PNG", "GIF"}:
        raise StickerProcessingError("expression.sticker_animation_format")
    if image.size != (SIDE, SIDE):
        raise StickerProcessingError("expression.sticker_animation_dimensions")
    if len(data) > MAX_BYTES:
        raise StickerProcessingError("expression.sticker_animation_large")
    frames = image.n_frames
    if frames > MAX_ANIMATION_FRAMES or frames * SIDE * SIDE > MAX_ANIMATION_PIXELS:
        raise StickerProcessingError("expression.sticker_animation_complex")
    duration = 0.0
    first = 1 if image.info.get("default_image", False) else 0
    union = None
    preview = None
    for index in range(first, frames):
        image.seek(index)
        frame = image.convert("RGBA")
        bbox = frame.getchannel("A").getbbox()
        if bbox:
            if preview is None:
                preview = _png(frame)
            union = (
                bbox
                if union is None
                else (
                    min(union[0], bbox[0]),
                    min(union[1], bbox[1]),
                    max(union[2], bbox[2]),
                    max(union[3], bbox[3]),
                )
            )
        try:
            delay = float(image.info.get("duration", 0))
        except (TypeError, ValueError) as exc:
            raise StickerProcessingError("expression.sticker_animation_timing") from exc
        if not math.isfinite(delay) or delay <= 0:
            raise StickerProcessingError("expression.sticker_animation_timing")
        duration += delay
        if duration > 5000:
            raise StickerProcessingError("expression.sticker_animation_duration")
    if union is None:
        raise StickerProcessingError("expression.sticker_empty")
    size = union[2] - union[0], union[3] - union[1]
    warnings = ("expression.sticker_warn_small",) if min(size) < 96 or max(size) < 160 else ()
    return PreparedSticker(
        data, ".gif" if image.format == "GIF" else ".png", preview, warnings, size, False, True
    )


def prepare_sticker_attachment(data: bytes) -> PreparedSticker:
    """Fit visible static artwork once; never shrink it repeatedly to satisfy byte limits."""
    if len(data) > MAX_INPUT_BYTES:
        raise StickerProcessingError("expression.input_large")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise StickerProcessingError("expression.image_pixels")
            if image.format not in {"PNG", "JPEG", "GIF", "WEBP"}:
                raise StickerProcessingError("expression.sticker_invalid")
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                return _animation(image, data)
            image = ImageOps.exif_transpose(image).convert("RGBA")
            # Ignore orientation/EXIF/text metadata in the upload. Do not erase nonzero alpha.
            image.info.clear()
            bbox = image.getchannel("A").getbbox()
            if bbox is None:
                raise StickerProcessingError("expression.sticker_empty")
            image = image.crop(bbox)
            scale = SIDE / max(image.size)
            size = tuple(max(1, min(SIDE, round(side * scale))) for side in image.size)
            warnings = []
            if scale > 2:
                warnings.append("expression.sticker_warn_upscale")
            if image.size != size:
                image = image.resize(size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
            # No mask/compositing: preserve RGBA values, including translucent edges.
            canvas.paste(image, ((SIDE - size[0]) // 2, (SIDE - size[1]) // 2))
            visible_size, visibility_warnings = _visibility(canvas)
            warnings.extend(visibility_warnings)
            result = _png(canvas)
            if len(result) > MAX_BYTES:
                raise StickerProcessingError("expression.sticker_static_large")
            return PreparedSticker(result, ".png", result, tuple(warnings), visible_size, result != data)
    except StickerProcessingError:
        raise
    except Image.DecompressionBombError as exc:
        raise StickerProcessingError("expression.image_pixels") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise StickerProcessingError("expression.sticker_invalid") from exc
