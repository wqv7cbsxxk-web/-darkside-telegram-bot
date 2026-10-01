import html
import re
import time
from urllib.parse import quote, urlsplit

import bot

# Metal News v5 text layer.
# Telegram receives a short preview; Mini App receives the complete useful article text.

_translation_cache = {}

EXTRA_PROTECTED_NAMES = [
    "Thrice", "Slipknot", "Marilyn Manson", "Set Your Goals",
    "Metal Injection", "Blabbermouth", "Decibel", "ThePRP",
    "No Clean Singing", "Louder", "Ultimate Classic Rock",
]
PROTECTED_NAMES = sorted(set(bot.CORE_ARTISTS + EXTRA_PROTECTED_NAMES), key=len, reverse=True)


def clean_source_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    m = re.search(r"\bthe\s+post\b.*?\bappeared\s+first\s+on\b", text, flags=re.I | re.S)
    if m:
        text = text[:m.start()].rstrip(" .,:;-\n")
    text = re.sub(r"\b(?:continue reading|read more|read the full article)\b.*$", "", text, flags=re.I | re.S).strip()
    text = re.sub(r"\bthis article\b.*?\boriginally appeared (?:on|at)\b.*$", "", text, flags=re.I | re.S).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    while lines and re.fullmatch(r"(?:#[\wА-Яа-яЁё-]+\s*)+", lines[-1]):
        lines.pop()
    text = "\n\n".join(lines)
    return re.sub(r"(?:\s+#[\wА-Яа-яЁё-]+){2,}\s*$", "", text).strip()


def fetch_full_article(url):
    """Extract all meaningful paragraphs. No artificial paragraph/character truncation."""
    if not url:
        return []
    try:
        r = bot.session.get(url, timeout=bot.REQUEST_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        is_darkside = (urlsplit(url).hostname or "").lower() in {"darkside.ru", "www.darkside.ru"}
        # Darkside has unbalanced font/a tags. Parse its bytes with HTML5 rules
        # (including the declared Windows-1251 encoding), as the browser does.
        soup = bot.BeautifulSoup(r.content, "html5lib") if is_darkside else bot.BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button", "svg"]):
            tag.decompose()
        if is_darkside:
            container = soup.select_one('div[align="justify"]')
            if container is None:
                return []  # Fall back to RSS, never scan menus or band archives.
            for tag in container.select(".newsimg, iframe, script, style"):
                tag.decompose()
            for tag in container.find_all("br"):
                tag.replace_with("\n")
            for tag in container.find_all("p"):
                tag.insert_before("\n")
                tag.insert_after("\n")
            return full_rss_paragraphs(container.get_text(" ", strip=False))
        candidates = [soup.find("article"), soup.find("main"), soup.select_one(".entry-content"), soup.select_one(".post-content"), soup.select_one(".article-content"), soup.select_one(".td-post-content")]
        container = next((x for x in candidates if x is not None), soup)
        paragraphs, seen = [], set()
        bad_phrases = ("subscribe to", "sign up", "cookie", "privacy policy", "advertisement", "follow us", "related:", "newsletter", "all rights reserved", "share this", "recommended for you", "you may also like")
        for p in container.find_all("p"):
            text = clean_source_text(re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip())
            if len(text) < 45:
                continue
            low = text.lower()
            if any(x in low for x in bad_phrases):
                continue
            key = re.sub(r"\W+", "", low)[:180]
            if not key or key in seen:
                continue
            seen.add(key)
            paragraphs.append(text)
        return paragraphs
    except Exception as exc:
        print("article fetch failed:", url, exc)
        return []


def _looks_like_release_title(value):
    value = value.strip(" ,.;:!?")
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", value)
    if not 1 <= len(words) <= 8 or len(value) > 90:
        return False
    title_like = sum(1 for word in words if word[:1].isupper() or word.isupper())
    return title_like >= max(1, (len(words) + 1) // 2)


def _protect_entities(text):
    kept = {}
    def hold(value):
        token = f"__KEEP_{len(kept)}__"
        kept[token] = value
        return token
    text = re.sub(r"https?://\S+", lambda m: hold(m.group(0)), text)
    for name in PROTECTED_NAMES:
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", lambda m: hold(m.group(0)), text, flags=re.I)
    for pattern in [r"“([^”]{1,90})”", r"«([^»]{1,90})»", r'"([^"\n]{1,90})"', r"‘([^’]{1,90})’"]:
        def repl(match):
            return hold(match.group(0)) if _looks_like_release_title(match.group(1)) else match.group(0)
        text = re.sub(pattern, repl, text)
    return text, kept


def _restore_entities(text, kept):
    for token, value in kept.items():
        text = text.replace(token, value)
    return text


def _translation_is_good(text):
    if not text:
        return False
    check = re.sub(r"__KEEP_\d+__", "", text)
    cyr = len(re.findall(r"[А-Яа-яЁё]", check))
    lat = len(re.findall(r"[A-Za-z]", check))
    return (cyr >= 12 and cyr >= lat * 0.55) or cyr >= 30


def _translate_chunk(chunk):
    errors = []
    providers = (bot._translate_google, bot._translate_lingva, bot._translate_mymemory)
    for provider in providers:
        try:
            result = provider(chunk)
            if _translation_is_good(result):
                return result
            errors.append(f"{provider.__name__}: validation failed")
        except Exception as exc:
            errors.append(f"{provider.__name__}: {exc}")

    # Important fallback: a provider can reject a whole chunk while translating
    # its individual sentences correctly. Without this, list items disappear.
    parts = bot.split_sentences(chunk)
    if len(parts) > 1:
        translated = []
        for part in parts:
            piece = None
            for provider in providers:
                try:
                    candidate = provider(part)
                    if _translation_is_good(candidate):
                        piece = candidate
                        break
                except Exception:
                    pass
            # A failed sentence must not erase factual material or list items.
            translated.append(piece or part)
            time.sleep(0.08)
        combined = " ".join(translated).strip()
        if combined:
            return combined

    print("translation failed:", " | ".join(errors))
    return chunk


def translate_to_ru(text):
    text = clean_source_text(text)
    if not text:
        return ""
    if text in _translation_cache:
        return _translation_cache[text]
    if bot._looks_russian(text):
        _translation_cache[text] = text
        return text
    protected, kept = _protect_entities(text)
    sentences = bot.split_sentences(protected) or [protected]
    chunks, current = [], ""
    for sentence in sentences:
        candidate = (current + " " + sentence).strip()
        if current and len(candidate) > 720:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    normalized = []
    for chunk in chunks:
        while len(chunk) > 760:
            cut = chunk.rfind(" ", 0, 760)
            if cut < 420:
                cut = 760
            normalized.append(chunk[:cut].strip())
            chunk = chunk[cut:].strip()
        if chunk:
            normalized.append(chunk)
    translated = []
    for chunk in normalized:
        result = _translate_chunk(chunk)
        if result:
            translated.append(result)
        time.sleep(0.06)
    out = clean_source_text(_restore_entities(" ".join(translated).strip(), kept))
    _translation_cache[text] = out
    return out


def full_rss_paragraphs(text):
    text = clean_source_text(text)
    if not text:
        return []
    natural = [clean_source_text(p) for p in re.split(r"\n{2,}", text) if clean_source_text(p)]
    if len(natural) >= 2:
        return natural
    sentences = bot.split_sentences(text)
    if not sentences:
        return [text]
    paragraphs, current = [], []
    chars = 0
    for sentence in sentences:
        current.append(sentence)
        chars += len(sentence)
        if chars >= 500:
            paragraphs.append(" ".join(current))
            current, chars = [], 0
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def prepare_texts(cand):
    article_paragraphs = fetch_full_article(cand["link"])
    rss_text = clean_source_text(cand.get("rss_body", ""))
    rss_paragraphs = full_rss_paragraphs(rss_text)
    article_size = sum(map(len, article_paragraphs))
    rss_size = sum(map(len, rss_paragraphs))
    if (cand["source"] == "Darkside" and article_paragraphs) or (article_size >= 500 and article_size >= rss_size * 0.75):
        source_paragraphs = article_paragraphs
        chosen = "page"
    else:
        source_paragraphs = rss_paragraphs
        chosen = "rss"
    if not source_paragraphs and rss_text:
        source_paragraphs = [rss_text]
    translated = []
    for paragraph in source_paragraphs:
        # Darkside's Russian edition already provides the translation. Keep
        # original release/track titles, including short English list items.
        result = paragraph if cand["source"] == "Darkside" else translate_to_ru(paragraph)
        if result:
            translated.append(re.sub(r"\s+", " ", result).strip())
    preview_source = " ".join(translated[:2]).strip() or translate_to_ru(rss_text)
    short = bot.make_short_excerpt(preview_source, min_chars=220, max_chars=380) if preview_source else ""
    print(f"ARTICLE {cand['source']}: page={article_size} chars; rss={rss_size} chars; chosen={chosen}; saved={sum(map(len, translated))} chars/{len(translated)} paragraphs")
    return short, translated


bot.remove_hashtag_tail = clean_source_text
bot.fetch_article_paragraphs = fetch_full_article
bot.translate_to_ru = translate_to_ru
bot.prepare_texts = prepare_texts

if __name__ == "__main__":
    bot.main()
