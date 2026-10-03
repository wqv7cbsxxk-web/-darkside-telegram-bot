"""Real CPU model smoke test; enabled by the CI model installation step."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from requests import Response
import bot
import runner


@unittest.skipUnless(os.environ.get('LOCAL_TRANSLATION_MODEL'), 'Offline model not configured')
class OfflineTranslationIntegration(unittest.TestCase):
    def test_full_article_names_and_preview_with_public_services_disabled(self):
        response = Response()
        response.status_code = 200
        response._content = (Path(__file__).parent / 'fixtures/theprp-morello.html').read_bytes()
        response.encoding = 'utf-8'
        candidate = {'id': 'offline-smoke', 'source': 'ThePRP',
                     'title': 'Tom Morello festival will be streamed live',
                     'link': 'https://www.theprp.com/offline-smoke', 'rss_body': '',
                     'category': 'Хэви-метал', 'published': bot.parse_datetime('2026-10-01T17:58:55+00:00')}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(runner, 'TRANSLATION_CACHE_FILE', str(Path(directory) / 'cache.json')), \
             patch.object(runner, '_translation_cache', {}), \
             patch.object(runner, '_cache_loaded', True), \
             patch.object(bot.session, 'get', return_value=response), \
             patch.object(bot, '_translate_google', side_effect=AssertionError('Public API called')), \
             patch.object(bot, '_translate_lingva', side_effect=AssertionError('Public API called')), \
             patch.object(bot, '_translate_mymemory', side_effect=AssertionError('Public API called')):
            article = runner.prepare_article(candidate)
        self.assertFalse(article.get('translation_pending'))
        self.assertEqual(len(article['paragraphs']), 4)
        self.assertLessEqual(len(article['short']), 381)
        text = ' '.join(article['paragraphs'])
        for name in ('Foo Fighters', 'Tom Morello', 'Hugo Weiss', 'Bruce Springsteen'):
            self.assertIn(name, text)
        for noise in ('A post shared by', 'Instagram', '__KEEP_'):
            self.assertNotIn(noise, text)

    def test_headline_preserves_every_protected_name(self):
        text = '__KEEP_1__ & __KEEP_2__ Members Unite In New Doom Metal Project __KEEP_0__'
        result = runner.local_translation.translate(text)
        self.assertTrue(runner.valid_provider_result(result, text), result)
