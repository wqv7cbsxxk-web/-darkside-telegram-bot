import unittest
from article_index import index_article

class ArtistIndexTests(unittest.TestCase):
    def test_multiple_artists_and_boundaries(self):
        article={'title':'Новость', 'paragraphs':['I Am Morbid and Terrorizer. toolbox accepted yesterday.']}
        index_article(article,'I AM MORBID and TERRORIZER announce dates')
        names=[a['name'] for a in article['artists']]
        self.assertIn('I Am Morbid',names)
        self.assertIn('Terrorizer',names)
        self.assertNotIn('Tool',names)
        self.assertNotIn('Accept',names)
        self.assertEqual(article['paragraphs'],['I Am Morbid and Terrorizer. toolbox accepted yesterday.'])

    def test_russian_alias_and_release(self):
        a=index_article({'title':'Дип Пёрпл представили альбом','paragraphs':[]})
        self.assertEqual(a['artists'][0]['name'],'Deep Purple')
        self.assertEqual(a['topics'],['releases'])

    def test_original_heading_survives_translation_for_matching(self):
        a=index_article({'title':'Новая песня','paragraphs':[]},'New OPETH single')
        self.assertEqual(a['artists'][0]['id'],'opeth')
        self.assertEqual(a['original_title'],'New OPETH single')

    def test_tours_without_inventing_dates(self):
        a=index_article({'title':'Iron Maiden announce tour','paragraphs':[]})
        self.assertIn('live',a['topics'])
        self.assertNotIn('concert_dates',a)

    def test_game_title_is_not_a_concert_tour(self):
        a=index_article({'title':'В Stage Tour, наследника Guitar Hero, добавлены песни Dream Theater','paragraphs':[]})
        self.assertNotIn('live',a['topics'])
