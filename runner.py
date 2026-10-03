import html
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import bot
from article_index import index_article

# Metal News v5 text layer.
# Telegram receives a short preview; Mini App receives the complete useful article text.

_translation_cache = {}
TRANSLATION_CACHE_FILE = "translation_cache.json"
_provider_retry_after = {}
_cache_loaded = False
_article_translation_failed = False
_prepared_article_text = {}


class TranslationUnavailable(RuntimeError):
    """Keep a news item eligible for a later run instead of sending English."""


def load_translation_cache():
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    try:
        data = json.loads(Path(TRANSLATION_CACHE_FILE).read_text(encoding="utf-8"))
        _translation_cache.update(data.get("translations", {}))
        _provider_retry_after.update(data.get("provider_retry_after", {}))
    except (OSError, ValueError, TypeError):
        pass


def save_translation_cache():
    path = Path(TRANSLATION_CACHE_FILE)
    temporary = path.with_suffix(".tmp")
    data = {"translations": dict(list(_translation_cache.items())[-4000:]),
            "provider_retry_after": _provider_retry_after}
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def call_translation_provider(provider, text):
    name = provider.__name__
    if time.time() < _provider_retry_after.get(name, 0):
        raise TranslationUnavailable(f"{name}: waiting after provider failure")
    try:
        return provider(text)
    except bot.requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            delay = exc.response.headers.get("Retry-After", "1800")
            try:
                delay = max(60, int(delay))
            except ValueError:
                delay = 1800
            _provider_retry_after[name] = time.time() + delay
            save_translation_cache()
        raise
    except bot.requests.RequestException:
        _provider_retry_after[name] = time.time() + 60
        raise
    except RuntimeError:
        if name == "_translate_lingva":
            _provider_retry_after[name] = time.time() + 300
        elif name == "_translate_mymemory":
            _provider_retry_after[name] = time.time() + 300
        raise

EXTRA_PROTECTED_NAMES = [
    "Thrice", "Slipknot", "Marilyn Manson", "Set Your Goals",
    "Metal Injection", "Blabbermouth", "Decibel", "ThePRP",
    "No Clean Singing", "Louder", "Ultimate Classic Rock",
]
PROTECTED_NAMES = sorted(set(bot.CORE_ARTISTS + EXTRA_PROTECTED_NAMES), key=len, reverse=True)
_page_entities = set()


def clean_source_text(text):
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    m = re.search(r"\b(?:the|korea)\s+post\b.*?\bappeared\s+first\s+on\b", text, flags=re.I | re.S)
    if m:
        text = text[:m.start()].rstrip()
    text = re.sub(r"\b(?:continue reading|read more|read the full article)\b.*$", "", text, flags=re.I | re.S).strip()
    text = re.sub(r"\bthis article\b.*?\boriginally appeared (?:on|at)\b.*$", "", text, flags=re.I | re.S).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    while lines and re.fullmatch(r"(?:#[\wА-Яа-яЁё-]+\s*)+", lines[-1]):
        lines.pop()
    text = "\n\n".join(lines)
    return re.sub(r"(?:\s+#[\wА-Яа-яЁё-]+){2,}\s*$", "", text).strip()


def clean_article_paragraphs(paragraphs):
    """Clean boilerplate that a publisher splits across separate HTML blocks."""
    joined = clean_source_text("\n\n".join(str(p).strip() for p in paragraphs if p and str(p).strip()))
    if not joined:
        return []
    bad_phrases = (
        "subscribe to", "sign up", "cookie", "privacy policy", "advertisement",
        "follow us", "related:", "newsletter", "all rights reserved", "share this",
        "recommended for you", "you may also like",
        "the latest news, features and interviews direct to your inbox",
        "you must confirm your public display name before commenting",
        "please logout and then login again",
    )
    result = []
    for paragraph in re.split(r"\n{2,}", joined):
        paragraph = clean_source_text(paragraph)
        if paragraph and not any(phrase in paragraph.lower() for phrase in bad_phrases):
            result.append(paragraph)
    return result


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
            return clean_article_paragraphs(full_rss_paragraphs(container.get_text(" ", strip=False)))
        if (urlsplit(url).hostname or "").lower() in {"theprp.com", "www.theprp.com"}:
            container = soup.select_one(".entry-content")
            if container is None:
                return []
            for tag in container.select(".instagram-media, .twitter-tweet, iframe, script, style"):
                tag.decompose()
            for tag in container.find_all("strong"):
                for name in tag.get_text("\n", strip=True).splitlines():
                    if _looks_like_release_title(name) or name == "grandson":
                        _page_entities.add(name)
            paragraphs = []
            for tag in container.find_all(["p", "li"]):
                if tag.name == "p" and tag.find("li"):
                    continue
                text = clean_source_text(tag.get_text(" ", strip=True))
                if text and not re.match(r"(?:A post shared by|View this post on Instagram)\b", text, re.I):
                    paragraphs.append(text)
            return clean_article_paragraphs(paragraphs)
        candidates = [soup.find("article"), soup.find("main"), soup.select_one(".entry-content"), soup.select_one(".post-content"), soup.select_one(".article-content"), soup.select_one(".td-post-content")]
        container = next((x for x in candidates if x is not None), soup)
        paragraphs, seen = [], set()
        bad_phrases = ("subscribe to", "sign up", "cookie", "privacy policy", "advertisement", "follow us", "related:", "newsletter", "all rights reserved", "share this", "recommended for you", "you may also like", "the latest news, features and interviews direct to your inbox", "you must confirm your public display name before commenting", "please logout and then login again")
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
        return clean_article_paragraphs(paragraphs)
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
    for name in sorted(set(PROTECTED_NAMES) | _page_entities, key=len, reverse=True):
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
    return (cyr >= 2 and cyr >= lat * 0.55) or cyr >= 30


def valid_provider_result(result, source):
    return _translation_is_good(result) and all(
        token in result for token in re.findall(r"__KEEP_\d+__", source)
    )


def _translate_chunk(chunk):
    global _article_translation_failed
    errors = []
    providers = (bot._translate_google, bot._translate_lingva, bot._translate_mymemory)
    for provider in providers:
        try:
            result = call_translation_provider(provider, chunk)
            if valid_provider_result(result, chunk):
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
                    candidate = call_translation_provider(provider, part)
                    if valid_provider_result(candidate, part):
                        piece = candidate
                        break
                except Exception:
                    pass
            # A failed sentence must not erase factual material or list items.
            translated.append(piece or part)
            if piece is None:
                _article_translation_failed = True
            time.sleep(0.08)
        combined = " ".join(translated).strip()
        if combined:
            return combined

    print("translation failed:", " | ".join(errors))
    _article_translation_failed = True
    return chunk


def translate_to_ru(text):
    text = clean_source_text(text)
    if not text:
        return ""
    load_translation_cache()
    if text in _translation_cache:
        return _translation_cache[text]
    if bot._looks_russian(text):
        _translation_cache[text] = text
        return text
    protected, kept = _protect_entities(text)
    if not re.search(r"[A-Za-zА-Яа-яЁё]", re.sub(r"__KEEP_\d+__", "", protected)):
        return text
    # MyMemory rejects requests over 500 characters even with HTTP 200.
    # Use a common safe limit for every provider, including sentence fallback.
    sentences = bot.split_sentences(protected) or [protected]
    chunks, current = [], ""
    for sentence in sentences:
        candidate = (current + " " + sentence).strip()
        if current and len(candidate) > 450:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    normalized = []
    for chunk in chunks:
        while len(chunk) > 450:
            cut = chunk.rfind(" ", 0, 450)
            if cut < 200:
                cut = 450
            normalized.append(chunk[:cut].strip())
            chunk = chunk[cut:].strip()
        if chunk:
            normalized.append(chunk)
    translated = []
    global _article_translation_failed
    previous_failure = _article_translation_failed
    _article_translation_failed = False
    for chunk in normalized:
        result = _translate_chunk(chunk)
        if result:
            translated.append(result)
        time.sleep(0.06)
    out = clean_source_text(_restore_entities(" ".join(translated).strip(), kept))
    failed = _article_translation_failed
    _article_translation_failed = previous_failure or failed
    if not failed and out:
        _translation_cache[text] = out
        save_translation_cache()
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
    if (cand["source"] in {"Darkside", "ThePRP"} and article_paragraphs) or (article_size >= 500 and article_size >= rss_size * 0.75):
        source_paragraphs = article_paragraphs
        chosen = "page"
    else:
        source_paragraphs = rss_paragraphs
        chosen = "rss"
    if not source_paragraphs and rss_text:
        source_paragraphs = [rss_text]
    source_paragraphs = clean_article_paragraphs(source_paragraphs)
    translated = []
    for paragraph in source_paragraphs:
        # Darkside's Russian edition already provides the translation. Keep
        # original release/track titles, including short English list items.
        result = paragraph if cand["source"] == "Darkside" else translate_to_ru(paragraph)
        if result:
            translated.append(re.sub(r"\s+", " ", result).strip())
    translated = clean_article_paragraphs(translated)
    preview_source = " ".join(translated[:2]).strip() or translate_to_ru(rss_text)
    short = bot.make_short_excerpt(preview_source, min_chars=220, max_chars=380) if preview_source else ""
    if cand.get("id"):
        _prepared_article_text[cand["id"]] = {
            "original": [re.sub(r"\s+", " ", p).strip() for p in source_paragraphs if p.strip()],
            "translated": translated,
        }
    print(f"ARTICLE {cand['source']}: page={article_size} chars; rss={rss_size} chars; chosen={chosen}; saved={sum(map(len, translated))} chars/{len(translated)} paragraphs")
    return short, translated


bot.remove_hashtag_tail = clean_source_text
bot.fetch_article_paragraphs = fetch_full_article
bot.translate_to_ru = translate_to_ru
bot.prepare_texts = prepare_texts

_base_prepare_article = bot.prepare_article


def prepare_article(cand):
    global _article_translation_failed
    _article_translation_failed = False
    article = _base_prepare_article(cand)
    prepared = _prepared_article_text.pop(cand["id"], {})
    if _article_translation_failed:
        # Keep the complete cleaned source available while public translation
        # providers are unavailable. The item remains marked for later retry.
        original = prepared.get("original") or [clean_source_text(cand.get("rss_body", ""))]
        original = [p for p in original if p]
        article.update({
            "title": cand["title"],
            "short": bot.make_short_excerpt(" ".join(original[:2]), min_chars=220, max_chars=380),
            "paragraphs": original,
            "translation_pending": True,
        })
    elif prepared.get("translated"):
        # The base bot has a legacy four-paragraph limit; retain the full
        # cleaned article that this pipeline has already extracted.
        article["paragraphs"] = prepared["translated"]
    return index_article(article, cand['title'])


bot.prepare_article = prepare_article


def retry_saved_translations(limit=2):
    """Repair previously sent English prose without sending messages again."""
    load_translation_cache()
    translated_values = set(_translation_cache.values())
    data = bot.load_articles()
    attempts = 0
    changed = False
    for article in data["articles"]:
        if article.get("source") == "Darkside":
            continue
        texts = [article.get("title", "")] + article.get("paragraphs", [])
        pending = article.get("translation_pending") or any(
            text not in translated_values and not bot._looks_russian(text) and re.search(
                r"\b(?:will|this|that|their|announces?|released?|says?|with|was|been)\b", text, re.I
            ) for text in texts
        )
        if not pending:
            continue
        article["translation_pending"] = True
        changed = True
        if attempts >= limit or time.time() < article.get("translation_retry_after", 0):
            continue
        attempts += 1
        cand = {"id": article["id"], "title": article.get("original_title", article["title"]), "source": article["source"],
                "category": article["category"], "link": article["original_url"],
                "published": bot.parse_datetime(article["published"]),
                "rss_body": "\n\n".join(article["paragraphs"])}
        try:
            result = prepare_article(cand)
        except TranslationUnavailable as exc:
            print("Saved article translation pending:", article["id"], exc)
            article["translation_retry_after"] = int(time.time()) + 3600
            continue
        if result.get("translation_pending"):
            print("Saved article translation still pending:", article["id"])
            article["translation_retry_after"] = int(time.time()) + 3600
            continue
        article.update({key: result[key] for key in ("title", "short", "paragraphs", "artists", "topics", "original_title")})
        article.pop("translation_pending", None)
        article.pop("translation_retry_after", None)
        article.pop("translation_retry_after", None)
    if changed:
        Path(bot.ARTICLES_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    retry_saved_translations()
    bot.main()
