"""Bounded, identity-checked public reference and city concert refresh."""
import argparse, json, re, time, hashlib
from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
SESSION=requests.Session()
SESSION.headers['User-Agent']='MetalNews/1.1 (https://github.com/wqv7cbsxxk-web/-darkside-telegram-bot)'
REF=Path('docs/reference_sources.json')
EVENTS=Path('docs/concerts.json')
MTS='https://live.mts.ru/novosibirsk/venues/concert-hall/loft-park-podzemka'
REVIEWED={'hulder':{'name':'Hulder','website':'https://hulder-official.com/','bandcamp_url':'https://hulder.bandcamp.com/music'}}
def now():return datetime.now(timezone.utc).isoformat()
def get(url,params=None):
    r=SESSION.get(url,params=params,timeout=14);r.raise_for_status();return r
def parse_concerts(html,source_url=MTS):
    soup=BeautifulSoup(html,'html.parser')
    script=soup.select_one('#__NEXT_DATA__')
    if not script:raise ValueError('Structured venue schedule missing')
    state=json.loads(script.string)['props']['pageProps']['initialState']
    venue=state['Venues']['venue'];city=state['Core']['region']['name']
    if city!='Новосибирск':raise ValueError('Unexpected city')
    rows=state['Schedule']['venueEventCollection']['items'];events=[];seen=set()
    for row in rows:
        if row.get('status')!='Registered':continue
        stamp=row.get('date','')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',stamp):continue
        title=row.get('announcement',{}).get('title','').strip()
        if not title or not row.get('widgetUrl','').startswith('/novosibirsk/announcements/'):continue
        key=re.sub(r'[^\w]+','',title.casefold())+'|'+stamp
        if key in seen:continue
        seen.add(key);identifier=hashlib.sha256((key+'|'+venue['title']).encode()).hexdigest()[:20]
        events.append({'id':identifier,'title':title,'date':stamp[:10],'time':stamp[11:16],'city':city,'venue':venue['title'],'source_url':urljoin(source_url,row['widgetUrl']),'source':'МТС Live','checked_at':now()})
    return events
def parse_bandcamp_release(html,expected,url):
    soup=BeautifulSoup(html,'html.parser')
    for script in soup.select('script[type="application/ld+json"]'):
        d=json.loads(script.string)
        if d.get('@type')!='MusicAlbum':continue
        if d.get('byArtist',{}).get('name','').casefold()!=expected.casefold():raise ValueError('Bandcamp identity mismatch')
        if not d.get('name'):raise ValueError('Release title missing')
        date=parsedate_to_datetime(d['datePublished']).date().isoformat()
        return {'name':d['name'],'date':date,'kind':'release','source_url':url}
    raise ValueError('Album metadata missing')
def bandcamp(profile,limit=5):
    base=profile['bandcamp_url'];soup=BeautifulSoup(get(base).text,'html.parser')
    links=[urljoin(base,a['href']) for a in soup.select('li.music-grid-item a[href^="/album/"]')]
    albums=[]
    for url in links[:limit]:
        try:albums.append(parse_bandcamp_release(get(url).text,profile['name'],url))
        except Exception as e:print('Bandcamp release retained:',type(e).__name__)
        time.sleep(1.1)
    return albums
def parse_musicbrainz_artist(data,expected):
    exact=[x for x in data.get('artists',[]) if x.get('name','').casefold()==expected.casefold() and x.get('type') in ('Group','Person','Orchestra','Choir')]
    if len(exact)!=1:raise ValueError('MusicBrainz artist ambiguous or absent')
    return exact[0]['id']
def musicbrainz(artist):
    # Resolve exact musical identities, never silently select a same-name entity.
    search=get('https://musicbrainz.org/ws/2/artist/',{'query':'artist:"'+artist['name'].replace('"','')+'"','fmt':'json','limit':10}).json()
    identifier=parse_musicbrainz_artist(search,artist['name']);time.sleep(1.1)
    entity=get('https://musicbrainz.org/ws/2/artist/'+identifier,{'inc':'artist-rels+url-rels+genres','fmt':'json'}).json();time.sleep(1.1)
    groups=get('https://musicbrainz.org/ws/2/release-group/',{'artist':identifier,'limit':100,'fmt':'json'}).json()
    result={'name':artist['name'],'musicbrainz_url':'https://musicbrainz.org/artist/'+identifier,'reference_checked_at':now(),'genres':', '.join(x['name'] for x in entity.get('genres',[]))}
    members=[]
    for r in entity.get('relations',[]):
        if r.get('type')=='member of band' and r.get('direction')=='backward' and not r.get('ended'):
            members.append({'name':r['artist']['name'],'role':', '.join(r.get('attributes',[])),'begin':r.get('begin')})
        if r.get('type')=='official homepage':result['website']=r.get('url',{}).get('resource')
        if r.get('type')=='bandcamp':result['bandcamp_url']=r.get('url',{}).get('resource')
    result['members']=members;result['members_source']=result['musicbrainz_url']
    albums=[]
    for g in groups.get('release-groups',[]):
        secondary=g.get('secondary-types',[])
        kind='live' if 'Live' in secondary else 'compilation' if 'Compilation' in secondary else 'studio' if g.get('primary-type')=='Album' else 'ep'
        albums.append({'name':g['title'],'date':g.get('first-release-date',''),'kind':kind,'source_url':'https://musicbrainz.org/release-group/'+g['id']})
    result['albums']=albums
    return result
def refresh(limit=4):
    data=json.loads(REF.read_text()) if REF.exists() else {'profiles':{},'checked':{}}
    artists=json.loads(Path('docs/artists.json').read_text())['artists']
    selected=sorted(artists,key=lambda a:data.get('checked',{}).get(a['id'],''))[:limit]
    data.setdefault('checked',{})
    for a in selected:
        try:
            profile=musicbrainz(a)
            data['profiles'][a['id']]={**data['profiles'].get(a['id'],{}),**profile}
        except Exception as e:print('Reference retained:',a['name'],type(e).__name__)
        data['checked'][a['id']]=now()
        time.sleep(1.1)
    # Reviewed artist-owned sources fill known gaps without waiting for rotation.
    for identifier,p in REVIEWED.items():
        previous=data['profiles'].get(identifier,{})
        if previous.get('bandcamp_checked_at') and (datetime.now(timezone.utc)-datetime.fromisoformat(previous['bandcamp_checked_at'])).total_seconds()<86400:continue
        try:
            albums=bandcamp(p)
            if albums:data['profiles'][identifier]={**previous,**p,'albums':albums,'bandcamp_checked_at':now()}
        except Exception as e:print('Official release cache retained:',type(e).__name__)
    REF.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    try:
        events=parse_concerts(get(MTS).text)
        if not events:raise ValueError('Empty schedule retained for inspection')
        EVENTS.write_text(json.dumps({'events':events,'checked_at':now()},ensure_ascii=False,indent=2)+'\n')
        print('Concerts refreshed:',len(events))
    except Exception as e:print('Concert schedule retained:',type(e).__name__)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=4);args=parser.parse_args();refresh(max(0,min(args.limit,6)))
