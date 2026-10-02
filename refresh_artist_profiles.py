"""Fetch bounded, attributable reference profiles and public tour schedules."""
import argparse
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, parse_qs, urlsplit

import requests
from bs4 import BeautifulSoup

CATALOG=Path('docs/artists.json')
OUTPUT=Path('docs/artist_profiles.json')
UA='MetalNewsAggregator/1.0 (https://github.com/wqv7cbsxxk-web/-darkside-telegram-bot; music news reader)'
PAGES={'tool':'Tool (band)','death':'Death (metal band)','yes':'Yes (band)','accept':'Accept (band)','ghost':'Ghost (Swedish band)','rainbow':'Rainbow (rock band)','rush':'Rush (band)','emperor':'Emperor (band)','genesis':'Genesis (band)','immortal':'Immortal (band)','ufo':'UFO (band)','kiss':'Kiss (band)','dio':'Dio (band)','the-l-i-f-e-project':'The L.I.F.E. Project','shogun-mojo':'Shogun Mojo','descape':'Descape','wasp':'W.A.S.P.'}
PAGES.update(json.loads(Path('artist_reference_pages.json').read_text()))
TOURS={'deep-purple':'https://deep-purple.com/tour-dates-2/','wolves-in-the-throne-room':'https://wittr.com/','opeth':'https://opeth.com/tour-dates'}


def parse_reference(raw, url):
    soup=BeautifulSoup(raw,'html.parser')
    box=soup.select_one('table.infobox')
    if not box:
        raise ValueError('No music infobox')
    fields={}
    for ref in box.select('sup, .reference'):ref.decompose()
    for row in box.find_all('tr'):
        header=row.find('th');cell=row.find('td')
        if not header or not cell:continue
        key=header.get_text(' ',strip=True).lower()
        fields[key]=cell
    if not any(k in fields for k in ['instruments','members','current members','past members','years active']):
        raise ValueError('Not a musical artist')
    def text(key):return fields[key].get_text(' ',strip=True) if key in fields else ''
    members=[]
    cell=fields.get('members') or fields.get('current members')
    former=False
    if cell is None and 'past members' in fields:
        cell=fields['past members'];former=True
    if cell:
        rows=cell.find_all('li') or [cell]
        for row in rows:
            # Links preserve full names; line-separated text handles unlinked names.
            names=[a.get_text(' ',strip=True) for a in row.find_all('a') if not a.get('href','').startswith('#')]
            if not names:names=[x.strip() for x in row.get_text('\n',strip=True).split('\n') if x.strip()]
            for name in names:
                if name and len(name)<100 and not any(x['name']==name for x in members):members.append({'name':name,'role':''})
    website=''
    if 'website' in fields:
        link=fields['website'].find('a',href=re.compile(r'^https?://'))
        if link:website=link['href']
    return {'origin':text('origin'),'genres':text('genres') or text('genre'),'years_active':text('years active'),
            'instruments':text('instruments'),
            'members':members,'members_note':'Бывшие участники, указанные в справочнике.' if former else 'Состав, указанный в справочнике. Он может отличаться от состава конкретного тура.',
            'website':website,'reference_url':url,'reference_checked_at':datetime.now(timezone.utc).isoformat()}


def event_objects(value):
    if isinstance(value,list):
        for item in value:yield from event_objects(item)
    elif isinstance(value,dict):
        types=value.get('@type',[])
        if isinstance(types,str):types=[types]
        if any(t in ['Event','MusicEvent'] for t in types):yield value
        for key in ['@graph','itemListElement','item','event','events']:
            if key in value:yield from event_objects(value[key])


def parse_events(raw, source_url, artist_name=None, calendar_year=None):
    soup=BeautifulSoup(raw,'html.parser');events=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(script.get_text())
        except (ValueError,TypeError):continue
        for item in event_objects(data):
            if artist_name:
                performer=item.get('performer',item.get('performers',{}))
                performers=performer if isinstance(performer,list) else [performer]
                if not any(isinstance(p,dict) and str(p.get('name','')).casefold()==artist_name.casefold() for p in performers):continue
            start=str(item.get('startDate',''))[:10]
            try:date.fromisoformat(start)
            except ValueError:continue
            if item.get('eventStatus','').endswith('EventCancelled'):continue
            location=item.get('location',{})
            if not isinstance(location,dict):continue
            address=location.get('address',{})
            if not isinstance(address,dict):continue
            city=address.get('addressLocality','');country=address.get('addressCountry','')
            if isinstance(country,dict):country=country.get('name','')
            if not city:continue
            event={'date':start,'city':city,'country':country,'venue':location.get('name',''),'source_url':source_url}
            if event not in events:events.append(event)
    # Bandzoogle omits years in its event cards. Only use an explicitly
    # reviewed tour year, and validate each printed weekday against it.
    if calendar_year:
        for card in soup.select('.event-description'):
            printed=card.select_one('.date-long .date')
            place=card.select_one('.event-location a')
            if not printed or not place:continue
            label=printed.get_text(' ',strip=True)
            try:dt=datetime.strptime(label+' '+str(calendar_year),'%A, %B %d %Y')
            except ValueError:continue
            if dt.strftime('%A')!=label.split(',')[0]:continue
            query=parse_qs(urlsplit(place.get('href','')).query).get('query',[''])[0]
            parts=[v.strip() for v in query.split(',')]
            if len(parts)<3:continue
            event={'date':dt.date().isoformat(),'city':parts[-2],'country':parts[-1],
                   'venue':', '.join(parts[:-2]),'source_url':source_url}
            if event not in events:events.append(event)
    return sorted(events,key=lambda e:(e['date'],e['city']))


def load():
    try:return json.loads(OUTPUT.read_text())
    except (OSError,ValueError):return {'profiles':{}}


def refresh(limit=6,budget=40):
    data=load();profiles=data.setdefault('profiles',{});catalog=json.loads(CATALOG.read_text())['artists'];started=time.monotonic()
    session=requests.Session();session.headers['User-Agent']=UA
    # Retain reviewed facts even when reference sites carry old or conflicting lineups.
    due = [a for a in catalog if profiles.get(a['id'],{}).get('reference_retry_after',0)<=time.time()]
    for artist in sorted(due,key=lambda a:profiles.get(a['id'],{}).get('reference_attempted_at',profiles.get(a['id'],{}).get('reference_checked_at','')))[:limit]:
        if time.monotonic()-started>budget:break
        existing=profiles.get(artist['id'],{})
        checked=existing.get('reference_checked_at','')
        if checked and (datetime.now(timezone.utc)-datetime.fromisoformat(checked)).total_seconds()<7*86400:continue
        title=PAGES.get(artist['id'],artist['name']);url='https://en.wikipedia.org/wiki/'+quote(title.replace(' ','_'))
        try:
            response=session.get(url,timeout=12);response.raise_for_status()
            profile=parse_reference(response.text,url)
            profiles[artist['id']]=dict(existing,**profile)
        except (requests.RequestException,ValueError):
            print('Reference unavailable:',artist['id'])
            profiles.setdefault(artist['id'],{})['reference_retry_after']=int(time.time())+86400
        profiles.setdefault(artist['id'],{})['reference_attempted_at']=datetime.now(timezone.utc).isoformat()
    tours=dict(TOURS)
    tours.update({ident:p['website'] for ident,p in profiles.items() if ident not in tours and p.get('website','').startswith(('https://','http://'))})
    tour_due=[(ident,url) for ident,url in tours.items() if not profiles.get(ident,{}).get('tour_checked_at') or (datetime.now(timezone.utc)-datetime.fromisoformat(profiles[ident]['tour_checked_at'])).total_seconds()>=6*3600]
    tour_due=sorted(tour_due,key=lambda pair:profiles.get(pair[0],{}).get('tour_attempted_at',''))
    for ident,url in tour_due[:4]:
        if time.monotonic()-started>budget:break
        profile=profiles.setdefault(ident,{})
        checked=profile.get('tour_checked_at','')
        if checked and (datetime.now(timezone.utc)-datetime.fromisoformat(checked)).total_seconds()<6*3600:continue
        try:
            response=session.get(url,timeout=12);response.raise_for_status()
            name=None if ident in TOURS else next((a['name'] for a in catalog if a['id']==ident),'')
            events=parse_events(response.text,url,name,profile.get('tour_calendar_year') if ident in TOURS else None)
            # A JS-only widget is not evidence that all announced events were removed.
            if events:
                profile['events']=events;profile['tour_checked_at']=datetime.now(timezone.utc).isoformat()
                profile['tour_source']=url
        except requests.RequestException:print('Tour unavailable:',ident)
        profile['tour_attempted_at']=datetime.now(timezone.utc).isoformat()
    OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=6);parser.add_argument('--budget',type=int,default=40)
    args=parser.parse_args();refresh(args.limit,args.budget)
