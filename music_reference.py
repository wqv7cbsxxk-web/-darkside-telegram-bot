"""Extract factual music sections without navigation, galleries or page widgets."""
import re
from urllib.parse import unquote
from bs4 import BeautifulSoup

def document(html):
    soup=BeautifulSoup(html,'html.parser')
    for el in soup.select('sup,.mw-editsection,style,script'):el.decompose()
    return soup

def parse_members(html):
    rows=[];active=False;kind='unclassified'
    for el in document(html).select('h2,h3,h4,ul,p,table'):
        text=el.get_text(' ',strip=True);lower=text.lower()
        if el.name=='h2':
            active=bool(re.fullmatch(r'(band |official |full-time )?members|current members|former members',lower));kind='current' if 'current' in lower else 'former' if 'former' in lower else 'unclassified';continue
        if not active:continue
        if el.name in ('h3','h4','p'):
            if el.name=='p' and not el.find('b'):continue
            kind='current' if re.search(r'^current',lower) else 'former' if re.search(r'^former|^past',lower) else 'unclassified';continue
        if el.find_parent(['ul','table']) or 'gallery' in el.get('class',[]):continue
        if el.name=='table':
            headers=[x.get_text(' ',strip=True).lower() for x in el.select('tr')[0].find_all(['th','td'],recursive=False)] if el.select('tr') else []
            if not all(key in headers for key in ['name','instruments']):continue
            years=next((i for i,h in enumerate(headers) if 'year' in h or 'tenure' in h),None)
            for row in el.select('tr')[1:]:
                cells=row.find_all(['th','td'],recursive=False)
                if len(cells)!=len(headers):continue
                name=cells[headers.index('name')].get_text(' ',strip=True);a=cells[headers.index('name')].find('a',href=True)
                role=cells[headers.index('instruments')].get_text(' ',strip=True);period=cells[years].get_text(' ',strip=True) if years is not None else 'period not specified'
                if name:rows.append(dict(name=name,text=name+' – '+role+' ('+period+')',kind=kind,title=a.get('title',name) if a else name))
            continue
        if el.name!='ul':continue
        for li in el.find_all('li',recursive=False):
            text=li.get_text(' ',strip=True)
            parts=re.split(r'\s+[–—−-]\s+',text,maxsplit=1)
            if len(parts)!=2 or len(text)>600:continue
            name=parts[0].strip();a=li.find('a',href=True)
            if not name:continue
            linked=a and a.get_text(' ',strip=True)==name
            title=(a.get('title') or unquote(a['href'].split('/wiki/')[-1]).replace('_',' ')) if linked else name
            rows.append(dict(name=name,text=text,kind=kind,title=title))
    return rows

def history_title(html):
    for a in document(html).select('.hatnote a[title]'):
        title=a['title']
        if re.match(r'^List of .* members$',title):return title
    return None

def parse_album(html):
    tracks=[];credits=[];section=''
    for el in document(html).select('h2,h3,table,ul'):
        if el.name in ('h2','h3'):
            heading=el.get_text(' ',strip=True).lower()
            if el.name=='h2' or re.search('track listing|tracklist|personnel|credits|musicians|performers',heading):section=heading
            continue
        if re.search('track listing|tracklist',section) and el.name=='table':
            for row in el.select('tr'):
                cells=[c.get_text(' ',strip=True) for c in row.find_all(['th','td'],recursive=False)]
                if len(cells)>1 and re.fullmatch(r'\d+\.?',cells[0]):tracks.append(dict(number=cells[0],title=cells[1].strip('"').strip(),duration=cells[-1] if re.fullmatch(r'\d+:\d{2}',cells[-1]) else ''))
        if re.search('personnel|credits|musicians|performers',section) and el.name=='ul' and not el.find_parent('ul'):
            for li in el.find_all('li',recursive=False):
                a=li.find('a',href=True)
                credits.append(dict(text=li.get_text(' ',strip=True),title=(a.get('title') or unquote(a['href'].split('/wiki/')[-1]).replace('_',' ')) if a else None))
    return dict(tracks=tracks,credits=credits)
