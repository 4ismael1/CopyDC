import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from command_utils import RestrictedView
from modules.clantag_cog import ClanTagCog
from modules.expression_cog import (
    MAX_INPUT_BYTES,
    MAX_INPUT_PIXELS,
    ExpressionCog,
    compress_static_image_for_discord,
)


class RestrictedViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_a_different_user(self):
        view = RestrictedView(author_id=10, timeout=1)
        response = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=11),
            guild=None,
            response=response,
        )

        self.assertFalse(await view.interaction_check(interaction))
        response.send_message.assert_awaited_once()

    async def test_rechecks_required_permissions(self):
        view = RestrictedView(
            author_id=10,
            timeout=1,
            required_permissions=("administrator",),
        )
        response = SimpleNamespace(send_message=AsyncMock())
        interaction = SimpleNamespace(
            user=SimpleNamespace(
                id=10,
                guild_permissions=SimpleNamespace(administrator=False),
            ),
            guild=SimpleNamespace(id=1),
            response=response,
        )

        self.assertFalse(await view.interaction_check(interaction))
        response.send_message.assert_awaited_once()


class ClanTagHelperTests(unittest.TestCase):
    def test_extracts_enabled_primary_guild(self):
        user = SimpleNamespace(
            primary_guild=SimpleNamespace(
                id=123,
                identity_enabled=True,
                tag="COPY",
                badge="badge-hash",
            )
        )

        self.assertEqual(
            ClanTagCog._extract_primary_guild(user),
            {"guild_id": 123, "tag": "COPY", "badge": "badge-hash"},
        )

    def test_ignores_disabled_primary_guild(self):
        user = SimpleNamespace(
            primary_guild=SimpleNamespace(
                id=123,
                identity_enabled=False,
                tag="COPY",
                badge=None,
            )
        )
        self.assertIsNone(ClanTagCog._extract_primary_guild(user))


class ExpressionSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_large_attachment_before_reading(self):
        attachment = SimpleNamespace(
            size=MAX_INPUT_BYTES + 1,
            read=AsyncMock(),
        )

        with self.assertRaises(ValueError):
            await ExpressionCog._read_attachment(attachment)
        attachment.read.assert_not_awaited()

    def test_rejects_small_compressed_image_with_excessive_pixel_count(self):
        probe = MagicMock()
        probe.width = MAX_INPUT_PIXELS + 1
        probe.height = 1
        opened = MagicMock()
        opened.__enter__.return_value = probe

        with (
            patch("modules.expression_cog.Image.open", return_value=opened),
            self.assertRaisesRegex(ValueError, "demasiados píxeles"),
        ):
            compress_static_image_for_discord(
                b"small-compressed-payload",
                max_bytes=1024,
                max_side=128,
            )


if __name__ == "__main__":
    unittest.main()
