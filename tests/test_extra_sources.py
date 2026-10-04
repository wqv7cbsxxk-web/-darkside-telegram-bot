import json, unittest
from refresh_extra_sources import parse_concerts,parse_bandcamp_release,parse_musicbrainz_artist,metal_genres
class ExtraSourcesTests(unittest.TestCase):
 def test_concerts_require_identified_band_and_resolved_metal_genre(self):
  state={'Core':{'region':{'name':'Новосибирск'}},'Venues':{'venue':{'title':'Подземка'}},'Schedule':{'venueEventCollection':{'items':[{'status':'Registered','date':'2026-10-18T19:00:00','announcement':{'title':'Концерт Deafheaven'} ,'widgetUrl':'/novosibirsk/announcements/deafheaven'}]}}}
  html=lambda:'<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':{'initialState':state}}})+'</script>'
  artists=[{'id':'deafheaven','name':'Deafheaven'}]
  ma={'deafheaven':{'name':'Deafheaven','genre':'Black Metal','source_url':'https://www.metal-archives.com/bands/Deafheaven/123'}}
  rows=parse_concerts(html(),artists=artists,ma_profiles=ma,wiki_lookup=lambda _:None)
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['genres'],['Black Metal']);self.assertIn('metal-archives.com',rows[0]['genre_source'])
  ma['deafheaven']['genre']=''
  rows=parse_concerts(html(),artists=artists,ma_profiles=ma,wiki_lookup=lambda _: {'genres':'black metal','genre_source':'https://en.wikipedia.org/wiki/Deafheaven'})
  self.assertEqual(rows[0]['genre_source'],'https://en.wikipedia.org/wiki/Deafheaven')
  rows=parse_concerts(html(),artists=artists,ma_profiles={},wiki_lookup=lambda _: None);self.assertEqual(rows,[])
  state['Core']['region']['name']='Москва'
  with self.assertRaises(ValueError):parse_concerts(html(),artists=artists,ma_profiles=ma,wiki_lookup=lambda _:None)
 def test_bandcamp_preserves_date_without_inventing_studio_type(self):
  data={'@type':'MusicAlbum','name':'Verbolgen','byArtist':{'name':'Hulder'},'datePublished':'07 Aug 2026 00:00:00 GMT','albumReleaseType':'AlbumRelease'}
  html='<script type="application/ld+json">'+json.dumps(data)+'</script>'
  a=parse_bandcamp_release(html,'Hulder','https://hulder.bandcamp.com/album/verbolgen')
  self.assertEqual(a['date'],'2026-08-07');self.assertEqual(a['kind'],'release')
  with self.assertRaises(ValueError):parse_bandcamp_release(html,'Another Band','https://example.org')
 def test_same_name_musicbrainz_ambiguity_is_not_silently_resolved(self):
  row={'name':'Hulder','type':'Group','id':'some-id'};self.assertEqual(parse_musicbrainz_artist({'artists':[row]},'Hulder'),'some-id')
  with self.assertRaises(ValueError):parse_musicbrainz_artist({'artists':[row,row]},'Hulder')
