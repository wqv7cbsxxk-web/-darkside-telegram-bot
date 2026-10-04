import json, unittest
from refresh_extra_sources import parse_concerts,parse_bandcamp_release,parse_musicbrainz_artist
class ExtraSourcesTests(unittest.TestCase):
    def test_concerts_deduplicate_and_reject_wrong_city(self):
        state={'Core':{'region':{'name':'Новосибирск'}},'Venues':{'venue':{'title':'Подземка'}},'Schedule':{'venueEventCollection':{'items':[{'status':'Registered','date':'2026-10-18T19:00:00','announcement':{'title':'Концерт Lumen'},'widgetUrl':'/novosibirsk/announcements/lumen'}]*2}}}
        def html():return '<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':{'initialState':state}}})+'</script>'
        rows=parse_concerts(html());self.assertEqual(len(rows),1);self.assertEqual(rows[0]['time'],'19:00')
        state['Core']['region']['name']='Москва'
        with self.assertRaises(ValueError):parse_concerts(html())
    def test_bandcamp_preserves_date_without_inventing_studio_type(self):
        data={'@type':'MusicAlbum','name':'Verbolgen','byArtist':{'name':'Hulder'},'datePublished':'07 Aug 2026 00:00:00 GMT','albumReleaseType':'AlbumRelease'}
        html='<script type="application/ld+json">'+json.dumps(data)+'</script>'
        a=parse_bandcamp_release(html,'Hulder','https://hulder.bandcamp.com/album/verbolgen')
        self.assertEqual(a['date'],'2026-08-07');self.assertEqual(a['kind'],'release')
        with self.assertRaises(ValueError):parse_bandcamp_release(html,'Another Band','https://example.org')
    def test_same_name_musicbrainz_ambiguity_is_not_silently_resolved(self):
        row={'name':'Hulder','type':'Group','id':'some-id'}
        self.assertEqual(parse_musicbrainz_artist({'artists':[row]},'Hulder'),'some-id')
        with self.assertRaises(ValueError):parse_musicbrainz_artist({'artists':[row,row]},'Hulder')
