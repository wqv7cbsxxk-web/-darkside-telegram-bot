import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from requests import Response

import bot
import runner

FIXTURES = Path(__file__).parent / "fixtures"


def response_for(news_id):
    response = Response()
    response.status_code = 200
    response._content = (FIXTURES / f"darkside-{news_id}.html").read_bytes()
    return response


def candidate(news_id):
    return {
        "id": str(news_id), "source": "Darkside", "category": "Хэви-метал",
        "title": "Новое видео WOLVES IN THE THRONE ROOM",
        "link": f"https://www.darkside.ru/news/{news_id}/",
        "rss_body": "Краткий RSS-анонс.",
        "published": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }


class PipelineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        cache_path = patch.object(runner, "TRANSLATION_CACHE_FILE", str(Path(directory.name) / "cache.json"))
        cache_path.start()
        self.addCleanup(cache_path.stop)
        runner._translation_cache.clear()
        runner._provider_retry_after.clear()
        runner._page_entities.clear()
        runner._cache_loaded = False
        runner._article_translation_failed = False

    def extract(self, news_id):
        with patch.object(bot.session, "get", return_value=response_for(news_id)):
            return runner.fetch_full_article(candidate(news_id)["link"])

    def test_wolves_entire_tracklist_and_exact_titles(self):
        self.assertEqual(self.extract(184168)[1:], [
            "1. Estuary 07:07", "2. Knights of Tiamat 08:37",
            "3. Foretold in Reflections 09:54", "4. The Orca Cliffs 07:53",
            "5. Ghosts Among the Obelisks 08:40",
            "6. Wretched Spirits, Land of the Light 06:14",
        ])

    def test_shogun_all_ten_tracks(self):
        paragraphs = self.extract(184167)
        self.assertEqual(len(paragraphs), 11)
        self.assertEqual([int(re.match(r"(\d+)\.", p)[1]) for p in paragraphs[1:]], list(range(1, 11)))
        self.assertEqual(paragraphs[-1], "10. Funk Party")

    def test_nightwish_long_quotes_and_final_paragraph(self):
        paragraphs = self.extract(183479)
        self.assertEqual(len(paragraphs), 6)
        self.assertGreater(len(paragraphs[1]), 480)
        self.assertTrue(paragraphs[-1].endswith("вместе со всей группой»."))
        self.assertNotIn("…", paragraphs[1])

    def test_no_page_chrome_comments_links_or_html(self):
        for news_id in (184168, 184167, 183479):
            with self.subTest(news_id=news_id):
                text = " ".join(self.extract(news_id))
                for noise in ("http://", "https://", "<", ">", "все новости группы",
                              "Комментарии", "Сообщений нет", "просмотров:",
                              "TOP5", "LOGIN", "Myspace:", "Facebook:", "Like!", "Yandex"):
                    self.assertNotIn(noise, text)

    def test_missing_darkside_container_uses_rss_not_page_text(self):
        response = Response(); response.status_code = 200
        response._content = b"<html><p>Archive navigation and unrelated long news headlines here</p></html>"
        cand = candidate(184168)
        cand["rss_body"] = "Русский анонс новости.\n\n1. Estuary\n\n2. Knights of Tiamat"
        with patch.object(bot.session, "get", return_value=response):
            short, paragraphs = runner.prepare_texts(cand)
        self.assertEqual(paragraphs, runner.full_rss_paragraphs(cand["rss_body"]))

    def test_json_and_telegram_payload_preserve_full_article_separately(self):
        cand = candidate(184168)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(bot, "ARTICLES_FILE", str(Path(directory) / "articles.json")), \
             patch.object(bot, "WEBAPP_BASE_URL", "https://example.com/"), \
             patch.object(bot.session, "get", return_value=response_for(184168)), \
             patch.object(bot, "telegram_api", return_value={}) as api, \
             patch.object(runner, "_translate_chunk", side_effect=AssertionError("Russian article must not be translated")):
            bot.send_news("test-chat", cand)
            article = json.loads(Path(bot.ARTICLES_FILE).read_text())["articles"][0]
            self.assertEqual(len(article["paragraphs"]), 7)
            self.assertTrue(article["paragraphs"][-1].startswith("6. Wretched Spirits"))
            self.assertLessEqual(len(article["short"]), 381)
            method, payload = api.call_args.args
            self.assertEqual(method, "sendMessage")
            self.assertNotIn("6. Wretched Spirits", payload["text"])
            self.assertTrue(payload["disable_web_page_preview"])
            self.assertEqual(payload["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"], "https://example.com/?id=184168&v=20261003-5")

    def test_failed_translation_preserves_original_list_item(self):
        original = "6. Wretched Spirits, Land of the Light 06:14"
        with patch.object(bot, "_translate_google", new=lambda text: ""), \
             patch.object(bot, "_translate_lingva", new=lambda text: ""), \
             patch.object(bot, "_translate_mymemory", new=lambda text: ""), \
             patch.object(runner.time, "sleep"):
            self.assertEqual(runner.translate_to_ru(original), original)

    def test_sentence_fallback_does_not_drop_failed_sentence(self):
        original = "Successful introduction. Missing final fragment."
        def provider(text):
            return "Успешно переведённое вступление." if text == "Successful introduction." else ""
        with patch.object(bot, "_translate_google", new=provider), \
             patch.object(bot, "_translate_lingva", new=lambda text: ""), \
             patch.object(bot, "_translate_mymemory", new=lambda text: ""), \
             patch.object(runner.time, "sleep"):
            result = runner.translate_to_ru(original)
            self.assertIn("Успешно переведённое вступление.", result)
            self.assertIn("Missing final fragment.", result)


if __name__ == "__main__":
    unittest.main()
