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
METAL_TERMS=re.compile(r"\b(?:heavy|black|death|doom|power|progressive|thrash|speed|folk|symphonic|gothic|industrial|alternative|nu|sludge|post|stoner|glam|groove|technical|melodic|avant-garde|rap|funk|metal) metal\b|\bmetal\b|метал(?:л)?(?:-?кор)?",re.I)
def event_band(row,artists):
    title=row.get('announcement',{}).get('title','').casefold()
    matches=[a for a in artists if a.get('name','').casefold() in title]
    matches.sort(key=lambda a:len(a.get('name','')),reverse=True)
    if not matches or (len(matches)>1 and len(matches[0]['name'])==len(matches[1]['name'])):return None
    return matches[0]
def wikipedia_genre(band):
    # Exact title search first; never accept an arbitrary same-name result.
    r=get('https://en.wikipedia.org/w/api.php',{'action':'query','list':'search','srsearch':'intitle:"'+band['name']+'" band','srlimit':5,'format':'json'})
    rows=r.json().get('query',{}).get('search',[])
    expected=band['name'].casefold()
    exact=[x for x in rows if x.get('title','').casefold() in (expected+' (band)',expected)]
    if len(exact)!=1:return None
    title=exact[0]['title']
    data=get('https://en.wikipedia.org/w/api.php',{'action':'query','prop':'extracts|categories','exintro':1,'explaintext':1,'cllimit':30,'titles':title,'format':'json'}).json()
    page=next(iter(data.get('query',{}).get('pages',{}).values()),{})
    text=' '.join([page.get('extract','')]+[x.get('title','') for x in page.get('categories',[])])
    genre=METAL_TERMS.search(text)
    if not genre:return None
    url='https://en.wikipedia.org/wiki/'+title.replace(' ','_')
    return {'genres':genre.group(0),'genre_source':url}
def metal_genres(row,artists,ma_profiles,wiki_lookup=wikipedia_genre,cache=None):
    band=event_band(row,artists)
    if not band:return None
    cache=cache if cache is not None else {}
    if band['id'] in cache:return {**cache[band['id']],'band_id':band['id'],'band_name':band['name']}
    ma=ma_profiles.get(band['id']) or {}
    genre=(ma.get('genre') or '').strip()
    if genre and METAL_TERMS.search(genre):
        result={'genres':genre,'genre_source':ma.get('source_url') or 'https://www.metal-archives.com/search?searchString='+band['name'].replace(' ','+')+'&type=band_name','genre_checked_at':now()}
    else:
        wiki=wiki_lookup(band) or {}
        result={**wiki,'genre_checked_at':now()} if wiki.get('genres') and wiki.get('genre_source') else None
    if result:cache[band['id']]=result
    return {**result,'band_id':band['id'],'band_name':band['name']} if result else None

def parse_concerts(html,source_url=MTS,artists=None,ma_profiles=None,wiki_lookup=wikipedia_genre,genre_cache=None):
    soup=BeautifulSoup(html,'html.parser')
    script=soup.select_one('#__NEXT_DATA__')
    if not script:raise ValueError('Structured venue schedule missing')
    state=json.loads(script.string)['props']['pageProps']['initialState']
    venue=state['Venues']['venue'];city=state['Core']['region']['name']
    if city!='Новосибирск':raise ValueError('Unexpected city')
    rows=state['Schedule']['venueEventCollection']['items'];events=[];seen=set();artists=artists or [];ma_profiles=ma_profiles or {};genre_cache=genre_cache or {}
    for row in rows:
        if row.get('status')!='Registered':continue
        stamp=row.get('date','')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',stamp):continue
        genre=metal_genres(row,artists,ma_profiles,wiki_lookup,genre_cache)
        if not genre:continue
        title=row.get('announcement',{}).get('title','').strip()
        if not title or not row.get('widgetUrl','').startswith('/novosibirsk/announcements/'):continue
        key=re.sub(r'[^\w]+','',title.casefold())+'|'+stamp
        if key in seen:continue
        seen.add(key);identifier=hashlib.sha256((key+'|'+venue['title']).encode()).hexdigest()[:20]
        events.append({'id':identifier,'genres':[genre['genres']],'genre_source':genre['genre_source'],'genre_checked_at':genre['genre_checked_at'],'band_id':genre['band_id'],'band_name':genre['band_name'],'title':title,'date':stamp[:10],'time':stamp[11:16],'city':city,'venue':venue['title'],'source_url':urljoin(source_url,row['widgetUrl']),'source':'МТС Live','checked_at':now()})
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
        artists=json.loads(Path('docs/artists.json').read_text())['artists']
        ma=json.loads(Path('docs/metal_archives.json').read_text()).get('profiles',{})
        known_ids={a['id'] for a in artists}
        artists.extend({'id':identifier,'name':profile['name']} for identifier,profile in ma.items() if identifier not in known_ids and profile.get('name'))
        previous=json.loads(EVENTS.read_text()) if EVENTS.exists() else {}
        events=parse_concerts(get(MTS).text,artists=artists,ma_profiles=ma,genre_cache=previous.get('genre_cache',{}))
        EVENTS.write_text(json.dumps({'events':events,'genre_cache':{**previous.get('genre_cache',{}),**{e['band_id']:{'genres':e['genres'][0],'genre_source':e['genre_source'],'genre_checked_at':e['genre_checked_at']} for e in events}},'checked_at':now()},ensure_ascii=False,indent=2)+'\n')
        print('Concerts refreshed:',len(events))
    except Exception as e:print('Concert schedule retained:',type(e).__name__)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=4);args=parser.parse_args();refresh(max(0,min(args.limit,6)))
