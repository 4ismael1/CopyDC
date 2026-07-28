import unittest
from types import SimpleNamespace

import discord

from modules.live_lfg_cog import matching_lfg_game, playing_activity_names
from modules.support_cases_cog import (
    build_transcript_html,
    package_transcript,
    safe_channel_slug,
    safe_external_url,
)


class SupportTranscriptTests(unittest.TestCase):
    def test_transcript_escapes_user_controlled_html_and_is_deterministic(self):
        records = [
            {
                "id": 1,
                "author_id": 2,
                "author_name": "user<script>",
                "author_display_name": "<b>name</b>",
                "author_avatar": 'https://example.test/avatar.png?x="bad"',
                "content": "<script>alert(1)</script>\nhello",
                "created_at": "2026-07-28T12:00:00+00:00",
                "edited_at": None,
                "attachments": [
                    {
                        "filename": "<unsafe>.txt",
                        "url": 'https://example.test/file?x="bad"',
                        "size": 12,
                        "content_type": "text/plain",
                    }
                ],
                "embeds": [],
            }
        ]

        first, first_hash = build_transcript_html(
            guild_name="<Guild>",
            channel_name="case-test",
            case_id=7,
            subject="<Subject>",
            opener_id=2,
            closed_by="<Closer>",
            close_reason="<Resolved>",
            records=records,
        )
        second, second_hash = build_transcript_html(
            guild_name="<Guild>",
            channel_name="case-test",
            case_id=7,
            subject="<Subject>",
            opener_id=2,
            closed_by="<Closer>",
            close_reason="<Resolved>",
            records=records,
        )
        document = first.decode()

        self.assertEqual(first, second)
        self.assertEqual(first_hash, second_hash)
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertIn("&lt;Subject&gt;", document)
        self.assertIn("&quot;bad&quot;", document)

    def test_channel_slug_is_bounded_and_safe(self):
        slug = safe_channel_slug("José / Support @ Everyone!" * 5)
        self.assertLessEqual(len(slug), 45)
        self.assertRegex(slug, r"^[a-z0-9-]+$")

    def test_large_text_transcript_is_compressed(self):
        packaged = package_transcript(
            b"repeated transcript content\n" * 10_000,
            html_filename="case-1-transcript.html",
            max_bytes=20_000,
        )

        self.assertIsNotNone(packaged)
        payload, filename = packaged
        self.assertEqual(filename, "case-1-transcript.zip")
        self.assertLessEqual(len(payload), 20_000)

    def test_transcript_urls_reject_active_schemes(self):
        self.assertEqual(safe_external_url("javascript:alert(1)"), "#")
        self.assertEqual(
            safe_external_url('https://example.test/file?x="bad"'),
            "https://example.test/file?x=&quot;bad&quot;",
        )


class LiveLFGHelperTests(unittest.TestCase):
    def test_only_playing_activities_are_considered(self):
        member = SimpleNamespace(
            activities=(
                discord.Game("League of Legends"),
                discord.Activity(type=discord.ActivityType.watching, name="League of Legends"),
                discord.CustomActivity(name="League of Legends"),
            )
        )

        self.assertEqual(playing_activity_names(member), {"league of legends"})

    def test_game_matching_is_exact_and_case_insensitive(self):
        member = SimpleNamespace(activities=(discord.Game("VALORANT"),))
        games = [
            {"game_id": 1, "activity_name": "Valor", "display_name": "Wrong"},
            {"game_id": 2, "activity_name": "valorant", "display_name": "VALORANT"},
        ]

        self.assertEqual(matching_lfg_game(member, games)["game_id"], 2)


if __name__ == "__main__":
    unittest.main()
