import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bot


def candidate(index, source="Darkside"):
    return {"id": str(index), "source": source, "priority": 95,
            "title": f"Unique news {index}", "category": "Хэви-метал",
            "link": f"https://example.com/news/{index}", "rss_body": "Новость",
            "published": bot.parse_datetime("2026-10-02T00:00:00+00:00")}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        state_file = patch.object(bot, "STATE_FILE", str(Path(self.directory.name) / "state.json"))
        state_file.start()
        self.addCleanup(state_file.stop)

    def test_pending_news_survives_restart_and_empty_feed(self):
        state = bot.load_state()
        bot.queue_candidates(state, [candidate(1)])
        bot.save_state(state)
        restored = bot.load_state()
        ready = bot.queue_candidates(restored, [])
        self.assertEqual([item["id"] for item in ready], ["1"])
        self.assertEqual(ready[0]["published"], candidate(1)["published"])
        restored["sent_ids"].append("1")
        bot.save_state(restored)
        self.assertEqual(bot.load_state()["pending_news"], [])

    def test_failed_items_do_not_block_the_ninth_candidate(self):
        candidates = [candidate(i) for i in range(9)]
        def send(chat_id, item):
            if item["id"] != "8":
                raise RuntimeError("Translation unavailable")
        with patch.object(bot, "resolve_chat_id", return_value="test"), \
             patch.object(bot, "collect_candidates", return_value=candidates), \
             patch.object(bot, "send_news", side_effect=send), \
             patch.object(bot, "title_similarity", return_value=0), patch.object(bot.time, "sleep"):
            bot.main()
        state = bot.load_state()
        self.assertEqual(state["sent_ids"], ["8"])
        self.assertEqual(len(state["pending_news"]), 8)
        # Refetching the same feed must retain cooldown and avoid a retry storm.
        self.assertEqual(bot.queue_candidates(state, candidates), [])

    def test_success_limit_retains_overflow_for_next_run(self):
        with patch.object(bot, "resolve_chat_id", return_value="test"), \
             patch.object(bot, "collect_candidates", return_value=[candidate(i) for i in range(12)]), \
             patch.object(bot, "send_news") as send, \
             patch.object(bot, "title_similarity", return_value=0), patch.object(bot.time, "sleep"):
            bot.main()
        self.assertEqual(send.call_count, 8)
        state = bot.load_state()
        self.assertEqual(len(state["pending_news"]), 4)
        self.assertEqual(len(bot.queue_candidates(state, [])), 4)


if __name__ == "__main__":
    unittest.main()
