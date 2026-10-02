import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from requests import Response, HTTPError

import bot
import runner

FIXTURE = Path(__file__).parent / "fixtures" / "theprp-morello.html"
URL = "https://www.theprp.com/2026/10/01/news/tom-morellos-power-to-the-people-festival-to-be-livestreamed-for-free/"


def page():
    response = Response()
    response.status_code = 200
    response._content = FIXTURE.read_bytes()
    response.encoding = "utf-8"
    return response


class TranslationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name) / "cache.json"
        self.files = patch.object(runner, "TRANSLATION_CACHE_FILE", str(self.cache))
        self.files.start()
        self.addCleanup(self.files.stop)
        runner._translation_cache.clear()
        runner._provider_retry_after.clear()
        runner._page_entities.clear()
        runner._cache_loaded = False
        runner._article_translation_failed = False

    def test_theprp_body_excludes_sidebar_and_instagram_caption(self):
        with patch.object(bot.session, "get", return_value=page()):
            paragraphs = runner.fetch_full_article(URL)
        self.assertEqual(len(paragraphs), 4)
        self.assertTrue(paragraphs[0].startswith("This weekend"))
        self.assertIn("Hugo Weiss", paragraphs[-1])
        text = " ".join(paragraphs)
        self.assertNotIn("A post shared by", text)
        self.assertNotIn("Agriculture Announce", text)
        self.assertNotIn("View this post", text)
        self.assertIn("Bruce Springsteen", runner._page_entities)

    def test_provider_chunks_fit_mymemory_limit(self):
        calls = []
        def provider(text):
            calls.append(text)
            return "Перевод новости о музыкальном фестивале и его участниках."
        with patch.object(bot, "_translate_google", new=provider), patch.object(runner.time, "sleep"):
            runner.translate_to_ru("This festival will feature many performers and a live broadcast. " * 30)
        self.assertGreater(len(calls), 2)
        self.assertTrue(all(len(text) <= 450 for text in calls))

    def test_short_theprp_article_is_used_instead_of_rss_teaser(self):
        response = Response(); response.status_code = 200
        response._content = b'<div class="entry-content"><p>Fans will hear the new song tomorrow.</p></div>'
        with patch.object(bot.session, "get", return_value=response), \
             patch.object(runner, "translate_to_ru", return_value="Фанаты услышат новую песню завтра.") as translate:
            short, paragraphs = runner.prepare_texts({"link": URL, "source": "ThePRP", "rss_body": "Brief teaser."})
        self.assertEqual(paragraphs, ["Фанаты услышат новую песню завтра."])
        translate.assert_called_once_with("Fans will hear the new song tomorrow.")

    def test_mymemory_http_200_error_is_not_a_translation(self):
        response = Response(); response.status_code = 200
        response._content = json.dumps({"responseStatus": "403", "responseDetails": "QUERY LENGTH LIMIT EXCEEDED",
                                       "responseData": {"translatedText": "QUERY LENGTH LIMIT EXCEEDED"}}).encode()
        with patch.object(bot.session, "get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "QUERY LENGTH LIMIT"):
                bot._translate_mymemory("source")

    def test_successful_translation_survives_process_cache_reload(self):
        original = "This event will be broadcast live."
        translated = "Это событие будут транслировать в прямом эфире."
        with patch.object(bot, "_translate_google", new=lambda text: translated), patch.object(runner.time, "sleep"):
            self.assertEqual(runner.translate_to_ru(original), translated)
        runner._translation_cache.clear()
        runner._cache_loaded = False
        with patch.object(bot, "_translate_google", side_effect=AssertionError("Must use persistent cache")):
            self.assertEqual(runner.translate_to_ru(original), translated)

    def test_mangled_entity_placeholders_are_rejected(self):
        self.assertFalse(runner.valid_provider_result("Группа __keep_0__ выпустила альбом.", "Band __KEEP_0__ releases album."))
        self.assertTrue(runner.valid_provider_result("Группа __KEEP_0__ выпустила альбом.", "Band __KEEP_0__ releases album."))

    def test_short_russian_translation_is_valid(self):
        self.assertTrue(runner._translation_is_good("Даты тура"))
        self.assertFalse(runner._translation_is_good("QUERY LENGTH LIMIT EXCEEDED"))

    def test_429_respects_retry_after_and_does_not_repeat_provider_calls(self):
        calls = []
        def blocked(text):
            calls.append(text)
            response = Response(); response.status_code = 429
            response.headers["Retry-After"] = "3600"
            raise HTTPError("quota", response=response)
        blocked.__name__ = "_translate_google"
        def fallback(text):
            return "Резервный перевод музыкальной новости с полным текстом."
        with patch.object(bot, "_translate_google", new=blocked), \
             patch.object(bot, "_translate_lingva", new=fallback), patch.object(runner.time, "sleep"):
            runner.translate_to_ru("First festival announcement will be available tomorrow.")
            runner.translate_to_ru("Second festival announcement will be available today.")
        self.assertEqual(len(calls), 1)
        data = json.loads(self.cache.read_text())
        self.assertGreater(data["provider_retry_after"]["_translate_google"], runner.time.time())

    def test_untranslated_news_is_not_sent_or_marked_seen(self):
        candidate = {"id": "pending", "source": "ThePRP", "title": "Festival will be broadcast live",
                     "category": "Хэви-метал", "link": URL,
                     "rss_body": "This festival will be streamed for free.",
                     "published": bot.parse_datetime("2026-10-01T17:58:55+00:00")}
        state = {"sent_ids": [], "recent_titles": []}
        with patch.object(bot.session, "get", return_value=page()), \
             patch.object(bot, "_translate_google", new=lambda text: ""), \
             patch.object(bot, "_translate_lingva", new=lambda text: ""), \
             patch.object(bot, "_translate_mymemory", new=lambda text: ""), \
             patch.object(bot, "load_state", return_value=state), \
             patch.object(bot, "resolve_chat_id", return_value="test-chat"), \
             patch.object(bot, "collect_candidates", return_value=[candidate]), \
             patch.object(bot, "save_state"), patch.object(bot, "save_article") as save, \
             patch.object(bot, "telegram_api") as api, patch.object(runner.time, "sleep"):
            bot.main()
        api.assert_not_called()
        save.assert_not_called()
        self.assertEqual(state["sent_ids"], [])


if __name__ == "__main__":
    unittest.main()
