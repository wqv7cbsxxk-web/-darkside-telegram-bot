import unittest
from music_reference import parse_members,parse_album
class ReferenceTests(unittest.TestCase):
 def test_members_are_scoped_and_keep_multiple_periods(self):
  raw='<nav>archive</nav><h2>Band members</h2><h3>Current members</h3><ul><li><a href="/wiki/John">John</a> – drums (1985–2010, 2023–present)<sup>[1]</sup></li></ul><h3>Former members</h3><ul><li><a href="/wiki/Paul">Paul</a> – vocals (1986)</li></ul><h2>References</h2><ul><li><a href="/wiki/Noise">Noise</a> - menu</li></ul>'
  rows=parse_members(raw);self.assertEqual(len(rows),2);self.assertEqual(rows[1]['kind'],'former');self.assertIn('1985–2010, 2023–present',rows[0]['text']);self.assertNotIn('[1]',rows[0]['text'])
 def test_tracks_and_actual_recording_credits(self):
  raw='<h2>Track listing</h2><h3>Disc one</h3><table><tr><th>No.</th><th>Title</th><th>Length</th></tr><tr><th>1.</th><td>Song</td><td>3:45</td></tr></table><h2>Personnel</h2><h3>The band</h3><ul><li><a href="/wiki/John">John</a> – guitar</li></ul><h2>References</h2><ul><li>Noise</li></ul>'
  data=parse_album(raw);self.assertEqual(data['tracks'][0]['title'],'Song');self.assertEqual(data['credits'],[{'text':'John – guitar','title':'John'}])
