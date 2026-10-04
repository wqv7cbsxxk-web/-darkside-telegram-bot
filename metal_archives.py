"""Optional, bounded reference refresh; never treats site announcements as music news."""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, quote
import requests
from bs4 import BeautifulSoup

OUTPUT=Path('docs/metal_archives.json')
CATALOG=Path('docs/artists.json')
SESSION=requests.Session()
SESSION.headers['User-Agent']='MetalNewsReference/1.0 (+https://github.com/wqv7cbsxxk-web/-darkside-telegram-bot)'

def clean(value):return re.sub(r'\s+',' ',value).strip()

def parse_band(text,expected_name,url):
    soup=BeautifulSoup(text,'html.parser')
    name=soup.select_one('h1.band_name')
    if not name or clean(name.get_text()).casefold()!=expected_name.casefold():
        raise ValueError('Metal Archives band identity did not match')
    stats={}
    for dt in soup.select('#band_stats dt'):
        dd=dt.find_next_sibling('dd')
        if dd:stats[clean(dt.get_text()).rstrip(':')]=clean(dd.get_text(' ',strip=True))
    members=[]
    for row in soup.select('#band_tab_members_current tr.lineupRow'):
        cells=row.find_all('td',recursive=False)
        if len(cells)>=2:
            link=cells[0].find('a',href=True)
            members.append({'name':clean(cells[0].get_text(' ',strip=True)),'role':clean(cells[1].get_text(' ',strip=True)),'url':urljoin(url,link['href']) if link else None})
    discography=soup.select_one('#band_tab_discography a[href*="/tab/main"]')
    return {'name':expected_name,'source_url':url,'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'origin':stats.get('Country of origin'),'location':stats.get('Location'),'genre':stats.get('Genre'),'status':stats.get('Status'),'formed':stats.get('Formed in'),'years_active':stats.get('Years active'),'members':members,'discography_url':urljoin(url,discography['href']) if discography else None}

def resolve_ids(artists):
    qids=[a.get('qid') for a in artists if a.get('qid')]
    result={}
    if qids:
        response=SESSION.get('https://www.wikidata.org/w/api.php',params={'action':'wbgetentities','ids':'|'.join(qids),'props':'claims','format':'json'},timeout=15);response.raise_for_status()
        for qid,entity in response.json().get('entities',{}).items():
            values=[s.get('mainsnak',{}).get('datavalue',{}).get('value') for s in entity.get('claims',{}).get('P1952',[])]
            value=next((str(v) for v in values if re.fullmatch(r'\d+',str(v))),None)
            if value:result[qid]=value
    return result

def refresh(limit=3):
    data=json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {'profiles':{}}
    artists=json.loads(CATALOG.read_text())['artists']
    cache=json.loads(Path('docs/music_cache.json').read_text())
    known={e.get('labels',{}).get('en',{}).get('value','').casefold():qid for response in cache.values() for qid,e in response.get('entities',{}).items() if any(statement.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id')=='Q215380' for statement in e.get('claims',{}).get('P31',[]))}
    for artist in artists:
        artist['qid']=artist.get('qid') or known.get(artist['name'].casefold())
    checked=data.setdefault('checked',{})
    selected=sorted([a for a in artists if a.get('qid')],key=lambda a:checked.get(a['id'],data['profiles'].get(a['id'],{}).get('checked_at','')))[:limit]
    try:ids=resolve_ids(selected)
    except Exception as exc:print('Metal Archives lookup unavailable:',exc);return
    changed=False
    for a in selected:
        identifier=ids.get(a['qid'])
        checked[a['id']]=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());changed=True
        if not identifier:continue
        url='https://www.metal-archives.com/bands/'+quote(a['name'].replace(' ','_'),safe='')+'/'+identifier
        try:
            response=SESSION.get(url,timeout=15);response.raise_for_status()
            profile=parse_band(response.text,a['name'],response.url)
            data['profiles'][a['id']]=profile;changed=True
            print('Metal Archives refreshed:',a['name'])
        except Exception as exc:
            data['profiles'].setdefault(a['id'],{'name':a['name'],'source_url':url,'content_unavailable':True})
            print('Metal Archives retained existing reference:',a['name'],exc)
        time.sleep(1)
    if changed:OUTPUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=3);args=parser.parse_args();refresh(max(1,min(args.limit,10)))
