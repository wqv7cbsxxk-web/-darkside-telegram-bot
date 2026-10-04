import unittest
from bs4 import BeautifulSoup
from article_media import extract_media
class MediaTests(unittest.TestCase):
    def test_owned_images_and_video_without_unsafe_html(self):
        html='<aside><img src="/ad.jpg"></aside><article><img src="/photo.jpg" alt="Band"><img src="/photo.jpg"><iframe src="https://www.youtube.com/embed/abc"></iframe><a href="javascript:alert(1)">bad</a><a href="/notes.pdf">Notes</a></article>'
        rows=extract_media(BeautifulSoup(html,'html.parser'),'https://example.org/news')
        self.assertEqual([x['type'] for x in rows],['image','video','file'])
        self.assertEqual(rows[0]['url'],'https://example.org/photo.jpg')
