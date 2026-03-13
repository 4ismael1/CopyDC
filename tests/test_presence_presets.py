import tempfile
import unittest
from pathlib import Path
from unittest import mock

import discord

import database as db
from command_utils import (
    build_presence_activity,
    looks_like_custom_emoji_reference,
    resolve_presence_status,
    split_custom_status_input,
)


class PresencePresetDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_bot_database.db")
        self.db_file_patch = mock.patch.object(db, "DB_FILE", self.db_path)
        self.db_file_patch.start()
        db.setup_database()

    def tearDown(self):
        self.db_file_patch.stop()
        self.temp_dir.cleanup()

    def test_presence_upsert_is_case_insensitive(self):
        db.upsert_bot_presence_preset("Demo", "custom", "idle", "Estado inicial", "🔥")
        db.upsert_bot_presence_preset("demo", "watching", "online", "Estado actualizado")

        rows = db.list_bot_presence_presets()
        self.assertEqual(len(rows), 1)

        preset = db.get_bot_presence_preset("DEMO")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["name"], "Demo")
        self.assertEqual(preset["activity_type"], "watching")
        self.assertEqual(preset["status"], "online")
        self.assertEqual(preset["activity_text"], "Estado actualizado")
        self.assertIsNone(preset["activity_emoji"])

    def test_set_and_delete_active_presence_preset(self):
        db.upsert_bot_presence_preset("uno", "custom", "idle", "Uno", "✨")
        db.upsert_bot_presence_preset("dos", "playing", "dnd", "Dos")

        self.assertTrue(db.set_active_bot_presence_preset("DOS"))

        active = db.get_active_bot_presence_preset()
        self.assertIsNotNone(active)
        self.assertEqual(active["name"], "dos")
        self.assertEqual(active["status"], "dnd")
        self.assertIsNone(active["activity_emoji"])

        self.assertTrue(db.delete_bot_presence_preset("dos"))
        self.assertIsNone(db.get_active_bot_presence_preset())


class PresenceUtilityTests(unittest.TestCase):
    def test_resolve_presence_status_maps_supported_values(self):
        self.assertIs(resolve_presence_status("online"), discord.Status.online)
        self.assertIs(resolve_presence_status("idle"), discord.Status.idle)
        self.assertIs(resolve_presence_status("dnd"), discord.Status.dnd)
        self.assertIs(resolve_presence_status("offline"), discord.Status.invisible)
        self.assertIs(resolve_presence_status("unknown"), discord.Status.online)

    def test_build_presence_activity_creates_expected_activity_objects(self):
        custom = build_presence_activity("custom", "Estado custom", "🔗")
        playing = build_presence_activity("playing", "Un juego")
        watching = build_presence_activity("watching", "el servidor")

        self.assertIsInstance(custom, discord.CustomActivity)
        self.assertEqual(custom.type, discord.ActivityType.custom)
        self.assertEqual(custom.name, "🔗 Estado custom")
        self.assertEqual(custom.state, "🔗 Estado custom")
        self.assertIsNone(custom.emoji)

        self.assertIsInstance(playing, discord.Game)
        self.assertEqual(playing.name, "Un juego")

        self.assertIsInstance(watching, discord.Activity)
        self.assertEqual(watching.name, "el servidor")
        self.assertIs(watching.type, discord.ActivityType.watching)

    def test_custom_emoji_reference_detection_matches_explicit_custom_formats(self):
        self.assertTrue(looks_like_custom_emoji_reference(":amonitobailando~1:"))
        self.assertTrue(looks_like_custom_emoji_reference("<a:amonitobailando:123456789012345678>"))
        self.assertFalse(looks_like_custom_emoji_reference("🔥"))
        self.assertFalse(looks_like_custom_emoji_reference("texto"))

    def test_split_custom_status_input_only_uses_pipe_as_emoji_separator_for_single_token_prefix(self):
        emoji, text = split_custom_status_input("🔗 | c!help | c!copy")
        self.assertEqual(emoji, "🔗")
        self.assertEqual(text, "c!help | c!copy")

        emoji, text = split_custom_status_input("🔗 c!help | c!copy")
        self.assertIsNone(emoji)
        self.assertEqual(text, "🔗 c!help | c!copy")


if __name__ == "__main__":
    unittest.main()
