"""Optional setlist.fm importer. Only explicitly reviewed solo shows are analysed."""
import json,os,time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import requests

OUTPUT=Path('docs/artist_profiles.json')
REVIEW=Path('setlist_review.json')

def analyse(records,review):
    """Do not classify a missing festival flag as a confirmed solo concert."""
    verified=[]
    for row in records:
        approved=review.get(row.get('id'),{})
        if approved.get('kind')!='solo' or not approved.get('source_url'):continue
        songs=[song['name'] for group in row.get('sets',{}).get('set',[]) for song in group.get('song',[]) if song.get('name') and not song.get('tape')]
        if not songs or approved.get('complete') is not True:continue
        try:date=datetime.strptime(row['eventDate'],'%d-%m-%Y').date().isoformat()
        except (ValueError,KeyError):continue
        verified.append({'id':row['id'],'date':date,'tour':row.get('tour',{}).get('name'),'venue':row.get('venue',{}).get('name',''),'songs':songs,'url':row.get('url'),'review_source':approved['source_url']})
    verified.sort(key=lambda x:x['date'],reverse=True)
    if not verified:return None
    # Different tours and unnamed tours cannot be merged into a generic setlist.
    latest=verified[0];shows=[x for x in verified if x['tour']==latest['tour'] and (latest['tour'] or x['id']==latest['id'])][:10]
    counts=Counter(song for show in shows for song in set(show['songs']))
    return {'tour':latest['tour'],'shows':shows,'songs':[{'name':song,'count':count} for song,count in counts.most_common()],'checked_at':datetime.now(timezone.utc).isoformat()}

def refresh():
    key=os.getenv('SETLIST_FM_API_KEY','').strip()
    if not key:print('setlist.fm not configured; existing data retained');return
    data=json.loads(OUTPUT.read_text());review=json.loads(REVIEW.read_text())
    session=requests.Session();session.headers.update({'x-api-key':key,'Accept':'application/json','User-Agent':'MetalNewsAggregator/2.0 (https://github.com/wqv7cbsxxk-web/-darkside-telegram-bot)'})
    for ident,profile in data['profiles'].items():
        if not profile.get('mbid') or ident not in review.get('artists',[]):continue
        try:
            response=session.get('https://api.setlist.fm/rest/1.0/artist/'+profile['mbid']+'/setlists',timeout=15);response.raise_for_status()
            result=analyse(response.json().get('setlist',[]),review.get('shows',{}))
            if result:profile['setlist_analysis']=result
        except (requests.RequestException,ValueError):print('setlist.fm unavailable:',ident)
        time.sleep(1)
    OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':refresh()
