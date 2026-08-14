from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Formatter
from typing import Any, Literal

import database as db

Language = Literal["en", "es"]
LanguageMode = Literal["auto", "en", "es"]

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "es"})
SUPPORTED_MODES: frozenset[str] = frozenset({"auto", "en", "es"})
DEFAULT_LANGUAGE: Language = "en"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"

log = logging.getLogger("copy.localization")

_catalogs: dict[str, dict[str, str]] = {}
_guild_modes: dict[int, LanguageMode] = {}
_formatter = Formatter()


def _template_fields(template: str, *, language: str, key: str) -> frozenset[str]:
    try:
        return frozenset(
            field_name for _, field_name, _, _ in _formatter.parse(template) if field_name is not None
        )
    except ValueError as exc:
        raise ValueError(f"Invalid translation template for {language}.{key}: {exc}") from exc


def load_catalogs() -> None:
    """Load and validate translation catalogs once at startup."""
    loaded: dict[str, dict[str, str]] = {}
    for language in sorted(SUPPORTED_LANGUAGES):
        path = LOCALES_DIR / f"{language}.json"
        with path.open("r", encoding="utf-8") as catalog_file:
            catalog = json.load(catalog_file)
        if not isinstance(catalog, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in catalog.items()
        ):
            raise ValueError(f"Invalid translation catalog: {path}")
        loaded[language] = catalog

    reference_keys = set(loaded[DEFAULT_LANGUAGE])
    for language, catalog in loaded.items():
        keys = set(catalog)
        if keys != reference_keys:
            missing = sorted(reference_keys - keys)
            extra = sorted(keys - reference_keys)
            raise ValueError(f"Translation key mismatch for {language}: missing={missing}, extra={extra}")

    for key in sorted(reference_keys):
        expected_fields = _template_fields(
            loaded[DEFAULT_LANGUAGE][key],
            language=DEFAULT_LANGUAGE,
            key=key,
        )
        for language, catalog in loaded.items():
            fields = _template_fields(catalog[key], language=language, key=key)
            if fields != expected_fields:
                raise ValueError(
                    f"Translation placeholder mismatch for {language}.{key}: "
                    f"expected={sorted(expected_fields)}, actual={sorted(fields)}"
                )

    _catalogs.clear()
    _catalogs.update(loaded)


def load_guild_modes() -> None:
    """Warm the small per-guild override cache from the database."""
    _guild_modes.clear()
    for row in db.get_all_guild_languages():
        mode = str(row["language_mode"]).lower()
        if mode in SUPPORTED_MODES:
            _guild_modes[int(row["guild_id"])] = mode  # type: ignore[assignment]


def initialize() -> None:
    load_catalogs()
    load_guild_modes()


def resolve_discord_locale(locale: object | None) -> Language:
    """Spanish Discord locales use Spanish; every other locale uses English."""
    normalized = str(locale or "").strip().lower().replace("_", "-")
    return "es" if normalized == "es" or normalized.startswith("es-") else DEFAULT_LANGUAGE


def _extract_guild(source: Any):
    if source is None:
        return None
    if hasattr(source, "preferred_locale") and hasattr(source, "id"):
        return source
    return getattr(source, "guild", None)


def get_guild_mode(guild_id: int) -> LanguageMode:
    return _guild_modes.get(int(guild_id), "auto")


def get_language(source: Any = None, *, locale: object | None = None) -> Language:
    guild = _extract_guild(source)
    if guild is not None:
        mode = get_guild_mode(int(guild.id))
        if mode in SUPPORTED_LANGUAGES:
            return mode  # type: ignore[return-value]
        return resolve_discord_locale(getattr(guild, "preferred_locale", None))

    if locale is None:
        locale = getattr(source, "locale", None)
    return resolve_discord_locale(locale)


def set_guild_mode(guild_id: int, mode: str) -> LanguageMode:
    normalized = mode.strip().lower()
    if normalized not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported language mode: {mode}")

    validated: LanguageMode = normalized  # type: ignore[assignment]
    db.set_guild_language(int(guild_id), validated)
    _guild_modes[int(guild_id)] = validated
    return validated


def remove_guild_mode(guild_id: int) -> None:
    _guild_modes.pop(int(guild_id), None)


def translate_language(lang: str, key: str, **values: Any) -> str:
    if not _catalogs:
        load_catalogs()

    selected = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    template = _catalogs.get(selected, {}).get(key)
    if template is None:
        template = _catalogs.get(DEFAULT_LANGUAGE, {}).get(key)
    if template is None:
        log.warning("Missing translation key: %s", key)
        return key

    try:
        return template.format(**values)
    except (KeyError, ValueError):
        log.exception("Invalid translation formatting for key %s", key)
        return template


def translate(source: Any, key: str, **values: Any) -> str:
    return translate_language(get_language(source), key, **values)


def catalog_keys(language: str) -> frozenset[str]:
    if not _catalogs:
        load_catalogs()
    return frozenset(_catalogs.get(language, {}))
