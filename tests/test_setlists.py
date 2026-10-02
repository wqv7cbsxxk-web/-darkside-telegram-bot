import unittest
from refresh_setlists import analyse
class SetlistTests(unittest.TestCase):
    def test_only_reviewed_complete_solo_shows_from_one_tour(self):
        def show(id,day,songs,tour='Tour A'):
            return {'id':id,'eventDate':day,'tour':{'name':tour},'sets':{'set':[{'song':[{'name':s} for s in songs]}]},'venue':{'name':'Hall'},'url':'https://www.setlist.fm/'+id}
        rows=[show('a','01-10-2026',['Same','Variant A']),show('b','02-10-2026',['Same','Variant B']),show('festival','03-10-2026',['Same']),show('old','30-09-2026',['Other'],'Tour B')]
        review={id:{'kind':'solo','complete':True,'source_url':'https://example.org/confirmed'} for id in ['a','b','old']}
        result=analyse(rows,review)
        self.assertEqual(len(result['shows']),2)
        self.assertEqual(result['songs'][0],{'name':'Same','count':2})
        self.assertNotIn('Other',[x['name'] for x in result['songs']])
        self.assertIsNone(analyse(rows,{}))
    def test_taped_songs_are_not_performed_songs(self):
        row={'id':'a','eventDate':'02-10-2026','sets':{'set':[{'song':[{'name':'Intro','tape':True},{'name':'Live'}]}]}}
        result=analyse([row],{'a':{'kind':'solo','complete':True,'source_url':'https://example.org'}})
        self.assertEqual(result['songs'],[{'name':'Live','count':1}])
