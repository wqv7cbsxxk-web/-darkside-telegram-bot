"""Extract article-owned media without retaining arbitrary executable HTML."""
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
import json, time
from pathlib import Path

def safe_url(value, base):
    if not str(value or '').strip():return None
    url=urljoin(base,str(value or '').strip())
    p=urlsplit(url)
    return url if p.scheme in ('http','https') and p.hostname and not p.username else None

def extract_media(soup, base):
    container=soup.select_one('.entry-content, .post-content, .article-content, [itemprop="articleBody"], div[align="justify"], article, main')
    media=[];seen=set()
    def add(kind,value,caption=''):
        url=safe_url(value,base)
        if not url or url in seen or len(media)>=20:return
        seen.add(url);media.append({'type':kind,'url':url,'caption':str(caption or '')[:240]})
    if container:
        for img in container.select('img'):
            if any(x in str(img.get('class','')).lower() for x in ('avatar','emoji','icon','logo')):continue
            if str(img.get('width','')).isdigit() and int(img['width'])<100:continue
            add('image',img.get('data-src') or img.get('data-lazy-src') or img.get('src'),img.get('alt',''))
        for el in container.select('iframe, video, audio, a[href]'):
            value=el.get('src') or el.get('href') or (el.select_one('source') or {}).get('src')
            url=safe_url(value,base)
            if not url:continue
            host=(urlsplit(url).hostname or '').lower();path=urlsplit(url).path.lower()
            if el.name=='video' or host in ('youtu.be','youtube.com','www.youtube.com','www.youtube-nocookie.com','player.vimeo.com','vimeo.com') or path.endswith(('.mp4','.webm')):add('video',url,el.get_text(' ',strip=True))
            elif el.name=='audio' or path.endswith(('.mp3','.wav','.ogg')):add('audio',url,el.get_text(' ',strip=True))
            elif path.endswith(('.pdf','.zip')):add('file',url,el.get_text(' ',strip=True))
            elif host in ('instagram.com','www.instagram.com','twitter.com','x.com','www.facebook.com','bandcamp.com') or host.endswith('.bandcamp.com'):add('link',url,el.get_text(' ',strip=True))
    cover=soup.select_one('meta[property="og:image"]')
    if cover:
        url=safe_url(cover.get('content'),base)
        if url and url not in seen:media.insert(0,{'type':'image','url':url,'caption':''})
    return media[:20]

def refresh(limit=8):
    import requests
    path=Path('docs/articles.json');data=json.loads(path.read_text());count=0
    for a in sorted(data['articles'],key=lambda a:a.get('media_checked_at',0)):
        if count>=limit:break
        if a.get('media_checked_at',0)>time.time()-86400:continue
        count+=1
        try:
            r=requests.get(a['original_url'],timeout=12,headers={'User-Agent':'MetalNews/1.1'});r.raise_for_status()
            a['media']=extract_media(BeautifulSoup(r.content,'html.parser'),r.url);a['media_checked_at']=int(time.time())
        except Exception:pass
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':refresh()
