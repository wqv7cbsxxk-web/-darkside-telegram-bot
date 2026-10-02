"""Refresh a small public reference cache; live search remains available for other artists."""
import json,time,requests
from pathlib import Path
from urllib.parse import urlencode
from datetime import datetime,timezone
from music_reference import parse_members,parse_album,history_title,parse_discography,discography_title
BASE='https://www.wikidata.org/w/api.php';WIKI='https://en.wikipedia.org/w/api.php'
s=requests.Session();s.headers['User-Agent']='MetalNewsAggregator/2.0 (https://github.com/wqv7cbsxxk-web/-darkside-telegram-bot; non-commercial reference reader)'
cache={};stamp=datetime.now(timezone.utc).isoformat();last=0
props={'P527','P463','P1303','P569','P570','P577','P175','P31','P434','P571','P576','P136','P740','P495','P856'}
def request(url):
 global last
 if url in cache:return cache[url]
 time.sleep(max(0,1.1-(time.monotonic()-last)));last=time.monotonic()
 r=s.get(url,timeout=25);r.raise_for_status();d=r.json()
 if 'error'in d:raise ValueError(d['error'])
 for e in d.get('entities',{}).values():
  e['claims']={k:v for k,v in e.get('claims',{}).items() if k in props}
  e['sitelinks']={k:v for k,v in e.get('sitelinks',{}).items() if k in ['enwiki','ruwiki']}
  e['_retrieved_at']=stamp
 d['_retrieved_at']=stamp;cache[url]=d;return d
def api(base,p):return base+'?'+urlencode(dict(p,format='json',origin='*'))
def entities(ids):
 result={}
 for i in range(0,len(ids),40):
  batch=ids[i:i+40]
  if batch:result.update(request(api(BASE,{'action':'wbgetentities','ids':'|'.join(batch),'props':'labels|descriptions|claims|sitelinks','languages':'ru|en'}))['entities'])
 return result
def val(x):return x.get('mainsnak',{}).get('datavalue',{}).get('value')
profiles=json.loads(Path('docs/artist_profiles.json').read_text())
for ident in ['dream-theater','deep-purple','opeth','wolves-in-the-throne-room']:
 try:
  p=profiles['profiles'][ident];title=p['reference_url'].split('/wiki/')[1].replace('_',' ')
  from urllib.parse import unquote
  title=unquote(title)
  d=request(api(WIKI,{'action':'query','prop':'pageprops','titles':title,'redirects':1}));qid=next(iter(d['query']['pages'].values()))['pageprops']['wikibase_item']
  e=entities([qid])[qid];ids=list(dict.fromkeys(val(x)['id'] for x in e.get('claims',{}).get('P527',[]) if val(x) and x.get('rank')!='deprecated'))
  people=entities(ids);inst=list(dict.fromkeys([val(x)['id'] for person in people.values() for x in person.get('claims',{}).get('P1303',[]) if val(x)]+[x['datavalue']['value']['id'] for member in e.get('claims',{}).get('P527',[]) for x in member.get('qualifiers',{}).get('P1303',[]) if x.get('datavalue')]))
  entities(inst)
  facts=list(dict.fromkeys(val(x)['id'] for prop in ['P136','P740','P495'] for x in e.get('claims',{}).get(prop,[]) if isinstance(val(x),dict) and val(x).get('id')))
  entities(facts)
  q=f'SELECT ?album ?albumLabel (MIN(?released) AS ?date) WHERE {{ ?album wdt:P175 wd:{qid}; wdt:P31/wdt:P279* wd:Q482994. OPTIONAL {{ ?album wdt:P577 ?released }} SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ru". }} }} GROUP BY ?album ?albumLabel ORDER BY ?date LIMIT 200'
  albums=request('https://query.wikidata.org/sparql?'+urlencode({'query':q,'format':'json'}))['results']['bindings']
  parsed=request(api(WIKI,{'action':'parse','page':e['sitelinks']['enwiki']['title'],'prop':'text','redirects':1}))
  raw=parsed['parse']['text']['*'];parsed['_parsed_members']=parse_members(raw);parsed['_parsed_discography']=parse_discography(raw);disco=discography_title(raw);parsed['_discography_title']=disco;history=history_title(raw);parsed['_history_title']=history;parsed['parse'].pop('text',None)
  if history:
   extra=request(api(WIKI,{'action':'parse','page':history,'prop':'text','redirects':1}));extra['_parsed_members']=parse_members(extra['parse']['text']['*']);extra['parse'].pop('text',None)
  if disco:
   details=request(api(WIKI,{'action':'parse','page':disco,'prop':'text','redirects':1}));details['_parsed_discography']=parse_discography(details['parse']['text']['*']);details['parse'].pop('text',None)
  if ident=='dream-theater':
   entry=next((a for a in albums if a['albumLabel']['value']=='Images and Words'),None)
   if entry:
    albumid=entry['album']['value'].split('/')[-1];album=entities([albumid])[albumid]
    title=album['sitelinks']['enwiki']['title'];request(api(WIKI,{'action':'query','prop':'pageprops','titles':title,'redirects':1}));detail=request(api(WIKI,{'action':'parse','page':title,'prop':'text','redirects':1}))
    detail['_parsed_album']=parse_album(detail['parse']['text']['*']);detail['parse'].pop('text',None)
  p['qid']=qid
  if e.get('claims',{}).get('P434'):p['mbid']=val(e['claims']['P434'][0])
  print(ident,len(ids),'members',len(albums),'albums',flush=True)
 except Exception as ex:print(ident,type(ex).__name__,str(ex)[:100],flush=True)
Path('docs/music_cache.json').write_text(json.dumps(cache,ensure_ascii=False,separators=(',',':'))+'\n')
Path('docs/artist_profiles.json').write_text(json.dumps(profiles,ensure_ascii=False,indent=2)+'\n')
print('cache',len(cache),flush=True)
