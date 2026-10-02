"""Conservative artist and event metadata; never modify the article text."""
import json
import re
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / 'docs/artists.json').read_text(encoding='utf-8'))['artists']
AMBIGUOUS = {'death', 'tool', 'yes', 'kiss', 'rush', 'genesis', 'accept', 'ghost', 'rainbow', 'death', 'emperor'}


def normalized(text):
    return re.sub(r'\s+', ' ', text.replace('’', "'").replace('ё', 'е')).casefold()


def mentions(text, alias):
    return re.search(r'(?<!\w)' + re.escape(normalized(alias)) + r'(?!\w)', normalized(text)) is not None


def index_article(article, original_title=''):
    title = original_title or article.get('original_title') or article.get('title', '')
    body = ' '.join(article.get('paragraphs', []))
    artists = []
    for artist in CATALOG:
        for alias in artist['aliases']:
            if normalized(alias) in AMBIGUOUS:
                # Common words must be deliberately capitalized in a heading.
                found = re.search(r'(?<!\w)' + re.escape(alias.upper()) + r'(?!\w)', title) or re.search(
                    r'(?<!\w)' + re.escape(artist['name']) + r'(?!\w)', title)
            else:
                found = mentions(title + ' ' + body, alias)
            if found:
                artists.append({'id': artist['id'], 'name': artist['name']})
                break
    article['artists'] = artists
    if original_title:
        article['original_title'] = original_title
    heading = normalized(title + ' ' + article.get('title', ''))
    topics = []
    event_heading = heading.replace('stage tour', '')
    if re.search(r'\b(?:tour\w*|festival\w*|concert\w*|live\w*|тур\w*|концерт\w*|фестивал\w*|выступлен\w*|гастрол\w*)\b', event_heading):
        topics.append('live')
    if re.search(r'\b(?:album\w*|single\w*|song\w*|release\w*|video\w*|альбом\w*|сингл\w*|песн\w*|видео\w*|релиз\w*|бокс\w*|клип\w*)\b', heading):
        topics.append('releases')
    article['topics'] = topics
    return article
