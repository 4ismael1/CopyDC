import ast
import json
import tempfile
import unittest
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
from unittest import mock

import database as db
import localization


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "copydc-localization-test.db")
        self.db_file_patch = mock.patch.object(db, "DB_FILE", self.db_path)
        self.db_file_patch.start()
        db.setup_database()
        localization.initialize()

    def tearDown(self):
        self.db_file_patch.stop()
        self.temp_dir.cleanup()

    def test_spanish_variants_and_other_languages(self):
        self.assertEqual(localization.resolve_discord_locale("es-ES"), "es")
        self.assertEqual(localization.resolve_discord_locale("es-419"), "es")
        self.assertEqual(localization.resolve_discord_locale("en-US"), "en")
        self.assertEqual(localization.resolve_discord_locale("fr"), "en")
        self.assertEqual(localization.resolve_discord_locale(None), "en")

    def test_manual_override_wins_over_guild_locale(self):
        guild = SimpleNamespace(id=10, preferred_locale="es-ES")
        self.assertEqual(localization.get_language(guild), "es")

        localization.set_guild_mode(guild.id, "en")
        self.assertEqual(localization.get_language(guild), "en")

        localization.set_guild_mode(guild.id, "auto")
        self.assertEqual(localization.get_language(guild), "es")

    def test_manual_override_survives_cache_reload(self):
        guild = SimpleNamespace(id=11, preferred_locale="en-US")
        localization.set_guild_mode(guild.id, "es")

        localization.load_guild_modes()

        self.assertEqual(localization.get_language(guild), "es")

    def test_catalogs_have_the_same_keys(self):
        self.assertEqual(
            localization.catalog_keys("en"),
            localization.catalog_keys("es"),
        )

    def test_catalogs_do_not_expose_literal_escape_sequences(self):
        for language in ("en", "es"):
            catalog_path = localization.LOCALES_DIR / f"{language}.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            invalid = {
                key: value
                for key, value in catalog.items()
                if any(sequence in value for sequence in (r"\n", r"\r", r"\t"))
            }
            self.assertEqual(invalid, {})

    def test_translation_formats_values(self):
        translated = localization.translate_language(
            "en",
            "language.saved",
            mode="English",
            language="English",
        )
        self.assertIn("English", translated)

    def test_editor_help_preserves_documented_variables(self):
        for language in ("en", "es"):
            vanity = localization.translate_language(language, "vanity.editor_description")
            clantag = localization.translate_language(language, "clantag.editor_description")
            for variable in ("{user}", "{role}", "{server}"):
                self.assertIn(variable, vanity)
                self.assertIn(variable, clantag)
            self.assertIn("{vanity}", vanity)
            self.assertIn("{tag}", clantag)

    def test_all_literal_translation_keys_used_by_the_bot_exist(self):
        project_root = Path(__file__).resolve().parents[1]
        source_files = [
            project_root / "main.py",
            project_root / "command_utils.py",
            *sorted((project_root / "modules").glob("*.py")),
        ]
        catalog = json.loads((localization.LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
        formatter = Formatter()
        used_keys: set[str] = set()
        incomplete_calls: list[str] = []

        for source_file in source_files:
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                function_name = (
                    function.id
                    if isinstance(function, ast.Name)
                    else function.attr
                    if isinstance(function, ast.Attribute)
                    else ""
                )
                if function_name not in {"translate", "translate_language"}:
                    continue
                if len(node.args) < 2:
                    continue
                key = node.args[1]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    used_keys.add(key.value)
                    template = catalog.get(key.value)
                    if template is None or any(keyword.arg is None for keyword in node.keywords):
                        continue
                    required = {
                        field_name
                        for _, field_name, _, _ in formatter.parse(template)
                        if field_name is not None
                    }
                    supplied = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
                    missing_values = required - supplied
                    if missing_values:
                        incomplete_calls.append(
                            f"{source_file.name}:{node.lineno} {key.value} missing={sorted(missing_values)}"
                        )

        missing = used_keys - localization.catalog_keys("en")
        self.assertEqual(missing, set())
        self.assertEqual(incomplete_calls, [])


if __name__ == "__main__":
    unittest.main()
