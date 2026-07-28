import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import database as db


class DatabaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "copydc-test.db")
        self.db_file_patch = mock.patch.object(db, "DB_FILE", self.db_path)
        self.db_file_patch.start()
        db.setup_database()
        db.setup_vanity_table()
        db.setup_clantag_table()

    def tearDown(self):
        self.db_file_patch.stop()
        self.temp_dir.cleanup()

    def test_counting_high_score_survives_reset_and_reconfiguration(self):
        db.set_counting_channel(100, 10)
        db.update_count(100, 7, 42)
        db.reset_count(100)

        row = db.get_counting_channel(100)
        self.assertEqual(row["current_number"], 0)
        self.assertEqual(row["high_score"], 7)

        db.set_counting_channel(100, 10)
        row = db.get_counting_channel(100)
        self.assertEqual(row["high_score"], 7)

        db.remove_counting_channel(100)
        self.assertIsNone(db.get_counting_channel(100))

    def test_remove_guild_clears_all_owned_configuration(self):
        guild = SimpleNamespace(id=10, name="Test Guild")
        db.add_guild(guild)
        db.add_thread_config(10, 101, "all")
        db.set_counting_channel(102, 10)
        db.add_auto_reaction(10, "hola", ["👋"])
        db.add_boost_role(10, 103, True)
        db.set_boost_log_channel(10, 104)
        db.set_vanity_settings(10, channel_id=105)
        db.add_vanity_code(10, "discord.gg/test", 106)
        db.set_clantag_settings(10, role_id=107)
        db.set_support_settings(10, 108, 109, 110, 30)
        db.create_support_case(10, 111, 42, "Ayuda", "2026-07-28T12:00:00+00:00")
        db.set_lfg_settings(10, 112)
        game = db.upsert_lfg_game(10, "Test Game", "Test Game", 113)
        db.enroll_lfg_user(10, 42, "2026-07-28T12:00:00+00:00")
        db.set_lfg_assignment(
            10,
            42,
            game["game_id"],
            game["role_id"],
            "2026-07-28T12:00:00+00:00",
        )

        db.remove_guild(guild)

        conn = db.get_db_connection()
        try:
            for table_name in (
                "guilds",
                "thread_configs",
                "counting_channels",
                "auto_reactions",
                "boost_roles",
                "boost_logs",
                "vanity_codes",
                "vanity_settings",
                "clantag_settings",
                "support_cases",
                "support_settings",
                "lfg_assignments",
                "lfg_enrollments",
                "lfg_games",
                "lfg_settings",
            ):
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE guild_id = ?",
                    (guild.id,),
                ).fetchone()[0]
                self.assertEqual(count, 0, table_name)
        finally:
            conn.close()

    def test_dynamic_setting_columns_are_restricted(self):
        with self.assertRaises(ValueError):
            db.set_vanity_settings(10, malicious_column="x")
        with self.assertRaises(ValueError):
            db.set_clantag_settings(10, malicious_column="x")

    def test_support_archive_retention_is_per_guild(self):
        db.set_support_settings(10, 100, 101, 102, 30)
        case_id = db.create_support_case(10, 103, 42, "Caso", "2026-06-01T00:00:00+00:00")
        self.assertTrue(db.close_support_case(case_id, 100, 104, "2026-06-15T00:00:00+00:00"))

        self.assertEqual(
            db.get_expired_support_archives("2026-07-14T23:59:59+00:00"),
            [],
        )
        expired = db.get_expired_support_archives("2026-07-15T00:00:00+00:00")
        self.assertEqual([row["case_id"] for row in expired], [case_id])

    def test_user_can_only_have_one_open_support_case(self):
        db.create_support_case(10, 100, 42, "Primero", "2026-07-28T12:00:00+00:00")

        with self.assertRaises(sqlite3.IntegrityError):
            db.create_support_case(10, 101, 42, "Segundo", "2026-07-28T12:01:00+00:00")

    def test_lfg_assignment_is_current_state_only(self):
        db.set_lfg_settings(10, 100)
        game = db.upsert_lfg_game(10, "Example Game", "Example", 101)
        db.enroll_lfg_user(10, 42, "2026-07-28T12:00:00+00:00")
        db.set_lfg_assignment(10, 42, game["game_id"], 101, "2026-07-28T12:01:00+00:00")

        assignment = db.get_lfg_assignment(10, 42)
        self.assertEqual(assignment["game_id"], game["game_id"])

        removed = db.unenroll_lfg_user(10, 42)
        self.assertEqual(removed["role_id"], 101)
        self.assertIsNone(db.get_lfg_assignment(10, 42))
        self.assertFalse(db.is_lfg_enrolled(10, 42))


if __name__ == "__main__":
    unittest.main()
