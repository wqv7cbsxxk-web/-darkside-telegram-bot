import html
import re
import time

import bot

# Text-processing layer for the Metal News bot.
# Improves RSS cleanup and Russian translation without rewriting bot.py.

_translation_cache = {}

EXTRA_PROTECTED_NAMES = [
    "Thrice", "Slipknot", "Marilyn Manson", "Set Your Goals",
    "Metal Injection", "Blabbermouth", "Decibel", "ThePRP",
    "No Clean Singing", "Louder", "Ultimate Classic Rock",
]

PROTECTED_NAMES = sorted(
    set(bot.CORE_ARTISTS + EXTRA_PROTECTED_NAMES),
    key=len,
    reverse=True,
)


def clean_source_text(text):
    """Remove RSS/WordPress boilerplate while preserving useful text."""
    if not text:
        return ""

    text = html.unescape(str(text))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # WordPress RSS tail:
    # "The post ... appeared first on ThePRP.com."
    m = re.search(
        r"\bthe\s+post\b.*?\bappeared\s+first\s+on\b",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        text = text[:m.start()].rstrip(" .,:;-\n")

    # Other common service tails.
    text = re.sub(
        r"\b(?:continue reading|read more|read the full article)\b.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    text = re.sub(
        r"\bthis article\b.*?\boriginally appeared (?:on|at)\b.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()

    # Darkside duplicate hashtag blocks.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    while lines and re.fullmatch(r"(?:#[\wА-Яа-яЁё-]+\s*)+", lines[-1]):
        lines.pop()

    text = "\n\n".join(lines)
    text = re.sub(r"(?:\s+#[\wА-Яа-яЁё-]+){2,}\s*$", "", text).strip()
    return text


def _looks_like_release_title(value):
    value = value.strip(" ,.;:!?")
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", value)

    if not 1 <= len(words) <= 8:
        return False
    if len(value) > 90:
        return False

    title_like = sum(
        1 for word in words
        if word[:1].isupper() or word.isupper()
    )
    return title_like >= max(1, (len(words) + 1) // 2)


def _protect_entities(text):
    kept = {}

    def hold(value):
        token = f"__KEEP_{len(kept)}__"
        kept[token] = value
        return token

    # URLs.
    text = re.sub(r"https?://\S+", lambda m: hold(m.group(0)), text)

    # Known bands/artists. Prevents things like:
    # Deep Purple -> "темно-фиолетовый"
    # Thrice -> "трижды"
    # Tool -> "инструмент"
    for name in PROTECTED_NAMES:
        pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
        text = re.sub(
            pattern,
            lambda m: hold(m.group(0)),
            text,
            flags=re.IGNORECASE,
        )

    # Preserve short quoted album/song titles.
    # Long spoken quotes are NOT protected and should be translated.
    quote_patterns = [
        r"“([^”]{1,90})”",
        r"«([^»]{1,90})»",
        r'"([^"\n]{1,90})"',
        r"‘([^’]{1,90})’",
        r"'([^'\n]{1,90})'",
    ]

    for pattern in quote_patterns:
        def repl(match):
            inner = match.group(1)
            if _looks_like_release_title(inner):
                return hold(match.group(0))
            return match.group(0)

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

    if cyr >= 12 and cyr >= lat * 0.55:
        return True
    return cyr >= 30


def _translate_chunk(chunk):
    errors = []

    for provider in (
        bot._translate_google,
        bot._translate_lingva,
        bot._translate_mymemory,
    ):
        try:
            result = provider(chunk)
            if _translation_is_good(result):
                return result
            errors.append(f"{provider.__name__}: validation failed")
        except Exception as exc:
            errors.append(f"{provider.__name__}: {exc}")

    # If a large paragraph failed, retry sentence by sentence.
    parts = bot.split_sentences(chunk)
    if len(parts) > 1:
        translated = []

        for part in parts:
            piece = None

            for provider in (
                bot._translate_google,
                bot._translate_lingva,
                bot._translate_mymemory,
            ):
                try:
                    candidate = provider(part)
                    if _translation_is_good(candidate):
                        piece = candidate
                        break
                except Exception:
                    pass

            if piece:
                translated.append(piece)

            time.sleep(0.08)

        combined = " ".join(translated).strip()
        if combined and _translation_is_good(combined):
            return combined

    print("translation v2 failed:", " | ".join(errors))
    return ""


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

    # Build chunks mainly on sentence boundaries.
    sentences = bot.split_sentences(protected)
    chunks = []
    current = ""

    for sentence in sentences or [protected]:
        candidate = (current + " " + sentence).strip()

        if current and len(candidate) > 720:
            chunks.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        chunks.append(current)

    # Handle a rare single very long sentence.
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

    for chunk in normalized[:12]:
        result = _translate_chunk(chunk)

        if result:
            translated.append(result)

        time.sleep(0.08)

    out = " ".join(translated).strip()
    out = _restore_entities(out, kept)
    out = clean_source_text(out)

    # Do not show a full untranslated English paragraph as if it were translated.
    if out and not bot._looks_russian(out) and len(out) > 80:
        out = ""

    _translation_cache[text] = out
    return out


def prepare_texts(cand):
    # Article text.
    article_paragraphs = [
        clean_source_text(p)
        for p in bot.fetch_article_paragraphs(cand["link"])
    ]
    article_paragraphs = [p for p in article_paragraphs if p]

    # RSS text as fallback.
    rss_text = clean_source_text(cand.get("rss_body", ""))
    rss_paragraphs = bot.paragraphs_from_text(
        rss_text,
        target_count=4,
    )
    rss_paragraphs = [
        clean_source_text(p)
        for p in rss_paragraphs
        if clean_source_text(p)
    ]

    article_size = sum(len(p) for p in article_paragraphs)
    rss_size = sum(len(p) for p in rss_paragraphs)

    # Prefer the actual article when it contains useful text.
    if article_size >= 500 and article_size >= rss_size * 0.75:
        source_paragraphs = article_paragraphs[:8]
    else:
        source_paragraphs = rss_paragraphs[:8]

    if not source_paragraphs and rss_text:
        source_paragraphs = [rss_text]

    translated_paragraphs = []
    total_chars = 0

    for paragraph in source_paragraphs:
        translated = translate_to_ru(paragraph)

        if not translated:
            continue

        translated = re.sub(r"\s+", " ", translated).strip()

        if not translated:
            continue

        translated_paragraphs.append(translated)
        total_chars += len(translated)

        if total_chars >= 6500:
            break

    # Telegram gets only a compact preview.
    # Mini App gets only the full paragraphs.
    preview_source = " ".join(translated_paragraphs[:2]).strip()

    if not preview_source:
        preview_source = translate_to_ru(rss_text)

    short = (
        bot.make_short_excerpt(
            preview_source,
            min_chars=220,
            max_chars=380,
        )
        if preview_source
        else ""
    )

    return short, translated_paragraphs[:8]


# Replace only the text-processing functions used by bot.main().
bot.remove_hashtag_tail = clean_source_text
bot.translate_to_ru = translate_to_ru
bot.prepare_texts = prepare_texts


if __name__ == "__main__":
    bot.main()
