import os
import re
import json
import html
import hashlib
import time
from difflib import SequenceMatcher
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

STATE_FILE = "state.json"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TEST_LATEST = os.environ.get("TEST_LATEST", "false").strip().lower() == "true"
WEBAPP_BASE_URL = os.environ.get("WEBAPP_BASE_URL", "").strip()
DISPLAY_TZ = os.environ.get("DISPLAY_TZ", "Asia/Novosibirsk").strip()
ARTICLES_FILE = "docs/articles.json"
MAX_ARTICLES = 150

MAX_RECENT_TITLES = 160
MAX_SENT_IDS = 1800
MAX_ENTRIES_PER_SOURCE = 24
REQUEST_TIMEOUT = 22
USER_AGENT = "Mozilla/5.0 (compatible; MetalNewsAggregator/4.0; +Telegram bot)"

# Darkside напрямую периодически отдаёт 403 автоматическим клиентам.
# Поэтому RSS Darkside читаем через RSS2JSON, который уже проверен на этом боте.
DARKSIDE_RSS2JSON = (
    "https://api.rss2json.com/v1/api.json"
    "?rss_url=http%3A%2F%2Fwww.darkside.ru%2Frss%2F"
)

SOURCES = [
    {"name": "Blabbermouth", "feed": "https://feeds.feedburner.com/blabbermouth", "priority": 100, "mode": "metal"},
    {"name": "Darkside", "feed": DARKSIDE_RSS2JSON, "priority": 95, "mode": "metal", "adapter": "rss2json"},
    {"name": "Metal Injection", "feed": "https://metalinjection.net/feed", "priority": 92, "mode": "metal"},
    {"name": "Decibel", "feed": "https://www.decibelmagazine.com/feed/", "priority": 90, "mode": "metal"},
    {"name": "ThePRP", "feed": "https://www.theprp.com/feed/", "priority": 88, "mode": "metal"},
    {"name": "No Clean Singing", "feed": "https://www.nocleansinging.com/feed/", "priority": 86, "mode": "metal"},
    {"name": "Louder", "feed": "https://www.loudersound.com/feeds/all", "priority": 84, "mode": "filtered"},
    {"name": "Ultimate Classic Rock", "feed": "https://ultimateclassicrock.com/feed/", "priority": 80, "mode": "classic_filtered"},
]

CORE_ARTISTS = [
    # Hard rock / classic hard rock / heavy
    "deep purple", "rainbow", "whitesnake", "led zeppelin", "black sabbath",
    "dio", "ozzy osbourne", "ac/dc", "aerosmith", "van halen", "scorpions",
    "guns n' roses", "guns n roses", "thin lizzy", "ufo", "uriah heep",
    "blue oyster cult", "alice cooper", "kiss", "motley crue", "def leppard",
    "accept", "saxon", "motorhead", "motörhead", "judas priest", "iron maiden",
    "queensryche", "queensrÿche", "manowar", "twisted sister", "skid row",
    "great white", "dokken", "tesla", "w.a.s.p.", "wasp",
    # Thrash / death / black / extreme
    "metallica", "megadeth", "slayer", "anthrax", "testament", "exodus",
    "overkill", "sepultura", "kreator", "sodom", "destruction", "death",
    "morbid angel", "terrorizer", "i am morbid", "deicide", "obituary",
    "cannibal corpse", "suffocation", "immolation", "carcass", "napalm death",
    "entombed", "dismember", "at the gates", "dark tranquility", "dark tranquillity",
    "in flames", "arch enemy", "behemoth", "mayhem", "emperor", "immortal",
    "darkthrone", "gorgoroth", "enslaved", "meshuggah", "gojira", "mastodon",
    # Prog rock / metal
    "dream theater", "opeth", "porcupine tree", "steven wilson", "tool",
    "haken", "leprous", "riverside", "pain of salvation", "fates warning",
    "symphony x", "between the buried and me", "the contortionist", "periphery",
    "devin townsend", "ayreon", "yes", "rush", "king crimson", "genesis",
    "jethro tull", "gentle giant", "marillion", "camel", "pink floyd",
]

DESIRED_KEYWORDS = [
    "hard rock", "classic rock", "heavy metal", "metal", "progressive rock",
    "progressive metal", "prog rock", "prog metal", "death metal", "black metal",
    "thrash metal", "doom metal", "power metal", "speed metal", "groove metal",
    "folk metal", "symphonic metal", "industrial metal", "grindcore", "grind",
    "deathcore", "metalcore", "sludge", "stoner metal", "nwobhm",
]

EXTREME_WORDS = [
    "death metal", "black metal", "grind", "grindcore", "deathcore", "extreme metal",
    "brutal death", "technical death", "melodic death", "blackened", "slam",
    "morbid angel", "terrorizer", "i am morbid", "deicide", "cannibal corpse",
    "suffocation", "behemoth", "napalm death", "carcass", "mayhem", "emperor",
    "immortal", "darkthrone", "gorgoroth",
]

PROG_WORDS = [
    "progressive", "prog rock", "prog metal", "dream theater", "opeth",
    "porcupine tree", "steven wilson", "tool", "haken", "leprous", "riverside",
    "fates warning", "symphony x", "the contortionist", "periphery", "ayreon",
    "yes", "rush", "king crimson", "gentle giant", "marillion", "camel",
]

HARD_ROCK_WORDS = [
    "hard rock", "classic rock", "deep purple", "rainbow", "whitesnake",
    "led zeppelin", "ac/dc", "aerosmith", "van halen", "scorpions", "ufo",
    "uriah heep", "thin lizzy", "alice cooper", "kiss", "guns n' roses",
]

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8,ru;q=0.6"})
_translation_cache = {}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "chat_id": None,
            "sent_ids": [],
            "recent_titles": [],
            "initialized_sources": [],
            "state_version": 3,
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    if not isinstance(state, dict):
        state = {}

    # Миграция со старого Darkside-only state.json.
    state.setdefault("chat_id", None)
    state.setdefault("sent_ids", [])
    state.setdefault("recent_titles", [])
    state.setdefault("initialized_sources", [])
    state.setdefault("pending_news", [])
    state["state_version"] = 3

    if not isinstance(state["sent_ids"], list):
        state["sent_ids"] = []
    if not isinstance(state["recent_titles"], list):
        state["recent_titles"] = []
    if not isinstance(state["initialized_sources"], list):
        state["initialized_sources"] = []
    if not isinstance(state["pending_news"], list):
        state["pending_news"] = []
    return state


def save_state(state):
    sent = set(state.get("sent_ids", []))
    state["pending_news"] = [
        item for item in state.get("pending_news", [])
        if isinstance(item, dict) and item.get("id") not in sent
    ]
    state["sent_ids"] = list(dict.fromkeys(state.get("sent_ids", [])))[-MAX_SENT_IDS:]
    state["recent_titles"] = state.get("recent_titles", [])[-MAX_RECENT_TITLES:]
    state["initialized_sources"] = list(dict.fromkeys(state.get("initialized_sources", [])))
    state["state_version"] = 3
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)



def get_webapp_base_url():
    if WEBAPP_BASE_URL:
        return WEBAPP_BASE_URL.rstrip("/") + "/"

    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" not in repo:
        raise RuntimeError(
            "WEBAPP_BASE_URL is not set and GITHUB_REPOSITORY is unavailable"
        )

    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


def load_articles():
    if not os.path.exists(ARTICLES_FILE):
        return {"articles": []}

    try:
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"articles": []}

    if not isinstance(data, dict):
        data = {"articles": []}
    if not isinstance(data.get("articles"), list):
        data["articles"] = []

    return data


def save_article(article):
    os.makedirs(os.path.dirname(ARTICLES_FILE), exist_ok=True)

    data = load_articles()
    items = [
        x for x in data.get("articles", [])
        if isinstance(x, dict) and x.get("id") != article.get("id")
    ]
    items.insert(0, article)
    data["articles"] = items[:MAX_ARTICLES]

    with open(ARTICLES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def article_webapp_url(article_id):
    return get_webapp_base_url() + "?id=" + quote(str(article_id), safe="")


def display_time(dt):
    try:
        tz = ZoneInfo(DISPLAY_TZ)
        return dt.astimezone(tz).strftime("%H:%M")
    except Exception:
        return dt.astimezone(timezone.utc).strftime("%H:%M")


def telegram_api(method, payload=None):
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = session.post(url, json=payload or {}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data.get("result")


def configure_open_menu(chat_id=None):
    """Configure a real Telegram menu entry, without sending a message."""
    expected = {"type": "web_app", "text": "Открыть", "web_app": {"url": get_webapp_base_url() + "?view=bands"}}
    # Both published entry routes open the main feed, including existing buttons.
    accepted = (expected, dict(expected, web_app={"url": get_webapp_base_url() + "?view=all"}))
    scopes = [{}]
    if chat_id and str(chat_id).isdigit():
        scopes.append({"chat_id": int(chat_id)})
    for scope in scopes:
        if telegram_api("getChatMenuButton", scope) not in accepted:
            telegram_api("setChatMenuButton", dict(scope, menu_button=expected))
        # Telegram can briefly return the previous menu after a successful set.
        for attempt in range(3):
            if telegram_api("getChatMenuButton", scope) in accepted:
                break
            if attempt == 2:
                raise RuntimeError("Telegram menu verification failed")
            time.sleep(1)
    print("Telegram menu verified: Открыть -> Mini App home")


def resolve_chat_id(state):
    if TELEGRAM_CHAT_ID:
        return TELEGRAM_CHAT_ID
    if state.get("chat_id"):
        return str(state["chat_id"])

    try:
        telegram_api("deleteWebhook", {"drop_pending_updates": False})
    except Exception as e:
        print("deleteWebhook warning:", e)

    updates = telegram_api("getUpdates", {"timeout": 0, "limit": 100}) or []
    for upd in reversed(updates):
        msg = upd.get("message") or upd.get("channel_post") or upd.get("edited_message")
        if msg and msg.get("chat", {}).get("id") is not None:
            state["chat_id"] = msg["chat"]["id"]
            return str(msg["chat"]["id"])
    raise RuntimeError("Chat ID not found. Send /start to the bot once, then run workflow again.")


def strip_html(raw):
    if not raw:
        return ""
    soup = BeautifulSoup(str(raw), "html.parser")
    text = soup.get_text("\n", strip=True)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_title(value):
    return re.sub(r"\s+", " ", strip_html(value)).strip()


def remove_hashtag_tail(text):
    if not text:
        return ""
    # Darkside часто завершает RSS набором дублирующих хэштегов.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    while lines and re.fullmatch(r"(?:#[\wА-Яа-яЁё-]+\s*)+", lines[-1]):
        lines.pop()
    result = "\n\n".join(lines)
    result = re.sub(r"(?:\s+#[\wА-Яа-яЁё-]+){2,}\s*$", "", result).strip()
    return result


def normalize_title(title):
    t = title.lower().replace("ё", "е")
    t = re.sub(r"[^a-zа-я0-9]+", " ", t)
    stop = {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "и", "в", "на", "с", "для", "о", "об", "из", "что", "как", "по",
        "new", "новый", "новая", "новое", "video", "видео", "song", "песня",
        "album", "альбом", "announce", "announces", "представили", "выпустили",
    }
    return " ".join(w for w in t.split() if w not in stop and len(w) > 1)


def title_similarity(a, b):
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    sa, sb = set(na.split()), set(nb.split())
    jac = len(sa & sb) / max(1, len(sa | sb))
    containment = len(sa & sb) / max(1, min(len(sa), len(sb)))
    return max(seq, jac, containment * 0.92)


def entry_id(source_name, entry):
    raw = str(entry.get("id") or entry.get("guid") or entry.get("link") or "")
    if not raw:
        raw = source_name + "|" + clean_title(entry.get("title", ""))
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = parsedate_to_datetime(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(str(value), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for key in ("published", "updated", "created", "pubDate"):
        dt = parse_datetime(entry.get(key))
        if dt:
            return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def entry_tags(entry):
    out = []
    for tag in entry.get("tags", []) or []:
        if isinstance(tag, dict):
            term = tag.get("term")
            if term:
                out.append(str(term))
        elif tag:
            out.append(str(tag))
    categories = entry.get("categories") or []
    if isinstance(categories, list):
        out.extend(str(x) for x in categories if x)
    return " ".join(out)


def entry_body(entry):
    values = []
    for content in entry.get("content", []) or []:
        if isinstance(content, dict) and content.get("value"):
            values.append(strip_html(content["value"]))
    for key in ("summary", "description"):
        if entry.get(key):
            values.append(strip_html(entry.get(key)))
    values = [remove_hashtag_tail(v) for v in values if v]
    return max(values, key=len, default="")


def relevant_for_source(source, title, body, tags):
    mode = source.get("mode")
    if mode == "metal":
        return True
    hay = f"{title} {body} {tags}".lower()
    artist_hit = any(a in hay for a in CORE_ARTISTS)
    keyword_hit = any(k in hay for k in DESIRED_KEYWORDS)
    if mode in {"classic_filtered", "filtered"}:
        return artist_hit or keyword_hit
    return True


def infer_category(title, body, tags):
    hay = f"{title} {body} {tags}".lower()
    if any(x in hay for x in PROG_WORDS):
        return "Прогрессив"
    if any(x in hay for x in EXTREME_WORDS):
        return "Экстремальный метал"
    if any(x in hay for x in HARD_ROCK_WORDS):
        return "Хард-рок"
    return "Хэви-метал"


def fetch_rss2json_entries(source):
    r = session.get(source["feed"], timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"RSS2JSON returned {data.get('status')}: {data}")
    entries = []
    for item in (data.get("items") or [])[:MAX_ENTRIES_PER_SOURCE]:
        content = item.get("content") or item.get("description") or ""
        entries.append({
            "id": item.get("guid") or item.get("link"),
            "guid": item.get("guid"),
            "link": item.get("link"),
            "title": item.get("title", ""),
            "summary": content,
            "description": item.get("description", ""),
            "published": item.get("pubDate"),
            "categories": item.get("categories") or [],
        })
    return entries


def fetch_standard_feed_entries(source):
    r = session.get(source["feed"], timeout=REQUEST_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    parsed = feedparser.parse(r.content)
    if getattr(parsed, "bozo", False):
        print(f"Feed warning {source['name']}:", getattr(parsed, "bozo_exception", "unknown"))
    return list(parsed.entries[:MAX_ENTRIES_PER_SOURCE])


def fetch_source_entries(source):
    if source.get("adapter") == "rss2json":
        return fetch_rss2json_entries(source)
    return fetch_standard_feed_entries(source)


def build_candidate(source, entry):
    title = clean_title(entry.get("title", ""))
    link = (entry.get("link") or "").strip()
    body = entry_body(entry)
    tags = entry_tags(entry)
    if not title or not link:
        return None
    if not relevant_for_source(source, title, body, tags):
        return None
    return {
        "source": source["name"],
        "priority": source["priority"],
        "title": title,
        "link": link,
        "rss_body": body,
        "tags": tags,
        "category": infer_category(title, body, tags),
        "published": entry_time(entry),
        "id": entry_id(source["name"], entry),
    }


def collect_candidates(state, include_seen=False):
    sent = set(state.get("sent_ids", []))
    initialized = set(state.get("initialized_sources", []))
    candidates = []

    for source in SOURCES:
        try:
            print(f"Reading {source['name']}: {source['feed']}")
            entries = fetch_source_entries(source)
            current = []
            for entry in entries:
                cand = build_candidate(source, entry)
                if cand:
                    current.append(cand)
            print(f"Feed {source['name']}: {len(entries)} entries; {len(current)} relevant.")

            # Первый успешный запуск каждого нового источника: только запоминаем текущую ленту.
            # Это защищает от пачки старых новостей после обновления бота.
            if source["name"] not in initialized and not TEST_LATEST:
                state["sent_ids"].extend(c["id"] for c in current)
                state["initialized_sources"].append(source["name"])
                print(f"Initialized {source['name']} with {len(current)} existing item(s), no send.")
                continue

            for cand in current:
                if include_seen or cand["id"] not in sent:
                    candidates.append(cand)
        except Exception as e:
            print(f"Source failed {source['name']}:", e)

    candidates.sort(key=lambda x: (x["published"], x["priority"]), reverse=True)

    # Дедупликация одинакового события между разными сайтами.
    deduped = []
    for cand in candidates:
        duplicate_index = None
        for i, kept in enumerate(deduped):
            # Далёкие по времени публикации с похожими заголовками не считаем дублем.
            age_hours = abs((cand["published"] - kept["published"]).total_seconds()) / 3600
            if age_hours <= 96 and title_similarity(cand["title"], kept["title"]) >= 0.78:
                duplicate_index = i
                break
        if duplicate_index is None:
            deduped.append(cand)
        else:
            kept = deduped[duplicate_index]
            if cand["priority"] > kept["priority"]:
                cand["duplicate_ids"] = kept.get("duplicate_ids", []) + [kept["id"]]
                deduped[duplicate_index] = cand
            else:
                kept.setdefault("duplicate_ids", []).append(cand["id"])
    return deduped


def queue_candidates(state, fresh):
    """Keep discovered news across runs, even after it leaves the RSS feed."""
    sent = set(state.get("sent_ids", []))
    pending = {
        item["id"]: dict(item) for item in state.get("pending_news", [])
        if isinstance(item, dict) and item.get("id") and item["id"] not in sent
    }
    for cand in fresh:
        if cand["id"] in sent:
            continue
        previous = pending.get(cand["id"], {})
        pending[cand["id"]] = dict(cand, published=cand["published"].isoformat(),
                                   retry_after=previous.get("retry_after", 0))
    state["pending_news"] = list(pending.values())
    ready = [dict(item, published=parse_datetime(item["published"]))
             for item in pending.values() if item.get("retry_after", 0) <= time.time()]
    ready.sort(key=lambda item: (item["published"], item.get("priority", 0)), reverse=True)
    return ready


def fetch_article_paragraphs(url):
    if not url:
        return []
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        container = soup.find("article") or soup.find("main") or soup

        paragraphs = []
        seen = set()
        for p in container.find_all("p"):
            text = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
            if len(text) < 55:
                continue
            low = text.lower()
            if any(bad in low for bad in [
                "subscribe to", "sign up", "cookie", "privacy policy", "advertisement",
                "follow us", "related:", "read more", "newsletter", "all rights reserved",
            ]):
                continue
            key = re.sub(r"\W+", "", low)[:140]
            if key in seen:
                continue
            seen.add(key)
            paragraphs.append(remove_hashtag_tail(text))
            if len(paragraphs) >= 8 or sum(len(x) for x in paragraphs) > 4200:
                break
        return [p for p in paragraphs if p]
    except Exception as e:
        print("article fetch failed:", url, e)
        return []


def split_sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9«\"])", text) if s.strip()]


def paragraphs_from_text(text, target_count=4):
    text = remove_hashtag_tail(text)
    natural = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(natural) >= 2:
        return natural[:6]

    sentences = split_sentences(text)
    if not sentences:
        return [text] if text else []
    if len(sentences) <= 2:
        return [" ".join(sentences)]

    target_count = min(target_count, len(sentences), 6)
    groups = [[] for _ in range(target_count)]
    for i, sentence in enumerate(sentences):
        idx = min(i * target_count // len(sentences), target_count - 1)
        groups[idx].append(sentence)
    return [" ".join(g).strip() for g in groups if g]


def _looks_russian(text):
    if not text:
        return False
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyr >= 8 and cyr >= latin * 0.35:
        return True
    return cyr >= 20


def _translate_google(chunk):
    r = session.get(
        "https://translate.googleapis.com/translate_a/single",
        params={
            "client": "gtx",
            "sl": "auto",
            "tl": "ru",
            "dt": "t",
            "q": chunk,
        },
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    result = "".join(part[0] for part in data[0] if part and part[0]).strip()
    if not result:
        raise RuntimeError("Google returned empty translation")
    return result


LINGVA_INSTANCES = [
    "https://translate.dr460nf1r3.org",
    "https://lingva.garudalinux.org",
    "https://translate.jae.fi",
]


def _translate_lingva(chunk):
    last_error = None
    encoded = quote(chunk, safe="")
    for base in LINGVA_INSTANCES:
        try:
            r = session.get(
                f"{base}/api/v1/auto/ru/{encoded}",
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            result = (data.get("translation") or "").strip()
            if result:
                return result
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Lingva failed: {last_error}")


def _translate_mymemory(chunk):
    # Резервный вариант. Для наших источников исходный язык практически всегда английский.
    r = session.get(
        "https://api.mymemory.translated.net/get",
        params={"q": chunk, "langpair": "en|ru"},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if str(data.get("responseStatus", "200")) != "200" or data.get("quotaFinished"):
        raise RuntimeError("MyMemory translation rejected: " + str(data.get("responseDetails") or data.get("responseStatus")))
    result = ((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not result:
        raise RuntimeError("MyMemory returned empty translation")
    return html.unescape(result)


def translate_to_ru(text):
    text = (text or "").strip()
    if not text:
        return ""
    if text in _translation_cache:
        return _translation_cache[text]

    if _looks_russian(text):
        _translation_cache[text] = text
        return text

    # Короткие части снижают риск отказов публичных переводчиков и длинных URL.
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= 850:
            chunks.append(remaining)
            break
        cut = remaining.rfind(" ", 0, 850)
        if cut < 450:
            cut = 850
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    translated = []
    for chunk in chunks[:8]:
        result = None
        errors = []

        for provider in (_translate_google, _translate_lingva, _translate_mymemory):
            try:
                candidate = provider(chunk)
                if candidate and (_looks_russian(candidate) or len(candidate) < 40):
                    result = candidate
                    break
                errors.append(f"{provider.__name__}: translation validation failed")
            except Exception as e:
                errors.append(f"{provider.__name__}: {e}")

        if result is None:
            print("translation failed for chunk:", " | ".join(errors))
            result = chunk

        translated.append(result)
        time.sleep(0.10)

    out = " ".join(x.strip() for x in translated if x.strip()).strip()
    _translation_cache[text] = out
    return out


def make_short_excerpt(text, min_chars=220, max_chars=380):
    text = re.sub(r"\s+", " ", remove_hashtag_tail(text)).strip()
    if len(text) <= max_chars:
        return text
    sentences = split_sentences(text)
    result = ""
    for sentence in sentences:
        candidate = (result + " " + sentence).strip()
        if len(candidate) > max_chars:
            break
        result = candidate
        if len(result) >= min_chars:
            break
    if len(result) >= min_chars:
        return result
    cut = text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def limit_paragraph(paragraph, limit=480):
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if len(paragraph) <= limit:
        return paragraph
    cut = paragraph[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def prepare_texts(cand):
    article_paragraphs = fetch_article_paragraphs(cand["link"])
    rss_paragraphs = paragraphs_from_text(cand.get("rss_body", ""), target_count=4)

    # Предпочитаем статью, только если реально получили содержательный материал.
    if sum(len(p) for p in article_paragraphs) >= max(500, sum(len(p) for p in rss_paragraphs)):
        source_paragraphs = article_paragraphs[:6]
    else:
        source_paragraphs = rss_paragraphs[:6]

    if not source_paragraphs:
        source_paragraphs = [cand.get("rss_body", "")] if cand.get("rss_body") else []

    translated_paragraphs = []
    for paragraph in source_paragraphs[:6]:
        translated = translate_to_ru(paragraph)
        if translated:
            translated_paragraphs.append(limit_paragraph(translated))

    expanded = translated_paragraphs[:4]
    excerpt_source = translate_to_ru(cand.get("rss_body", "")) or " ".join(expanded)
    short = make_short_excerpt(excerpt_source)

    # Если RSS-анонс слишком короткий, строим компактный анонс из расширенного текста.
    if len(short) < 140 and expanded:
        short = make_short_excerpt(" ".join(expanded))

    return short, expanded


def prepare_article(cand):
    short, expanded = prepare_texts(cand)
    if not short:
        short = "Краткое описание в источнике отсутствует."

    title_ru = translate_to_ru(cand["title"]) or cand["title"]

    return {
        "id": cand["id"],
        "title": title_ru,
        "short": short,
        "paragraphs": expanded if expanded else [short],
        "category": cand["category"],
        "source": cand["source"],
        "published": cand["published"].isoformat(),
        "original_url": cand["link"],
        "saved_at": int(time.time()),
    }


def send_news(chat_id, cand):
    article = prepare_article(cand)

    # Сначала сохраняем статью локально.
    # GitHub Actions закоммитит docs/articles.json после выполнения бота.
    save_article(article)

    title_e = html.escape(article["title"])
    short_e = html.escape(article["short"])
    meta_e = html.escape(
        f'{article["category"]} · {article["source"]} · {display_time(cand["published"])}'
    )

    text = (
        f"<b>{title_e}</b>\n\n"
        f"{short_e}\n\n"
        f"<i>{meta_e}</i>"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "Читать",
                    "web_app": {
                        "url": article_webapp_url(article["id"])
                    }
                }
            ]]
        },
    }
    return telegram_api("sendMessage", payload)


def send_test_latest(chat_id, state):
    candidates = collect_candidates(state, include_seen=True)
    if not candidates:
        print("TEST_LATEST: no candidate available")
        return
    cand = candidates[0]
    send_news(chat_id, cand)
    print(f"TEST_LATEST sent: {cand['source']} — {cand['title']}")


def main():
    state = load_state()
    chat_id = resolve_chat_id(state)
    try:
        configure_open_menu(chat_id)
    except Exception as e:
        print("Telegram menu warning:", type(e).__name__)

    if TEST_LATEST:
        send_test_latest(chat_id, state)
        save_state(state)
        return

    candidates = queue_candidates(state, collect_candidates(state, include_seen=False))
    save_state(state)
    recent_titles = [
        x.get("title", "") if isinstance(x, dict) else str(x)
        for x in state.get("recent_titles", [])
    ]
    sent_count = 0
    started = time.monotonic()

    # Limit successful cards, so failed translations don't block other sources.
    for cand in candidates:
        if sent_count >= 8 or time.monotonic() - started >= 480:
            break
        if any(title_similarity(cand["title"], old) >= 0.80 for old in recent_titles[-100:]):
            state["sent_ids"].append(cand["id"])
            state["sent_ids"].extend(cand.get("duplicate_ids", []))
            continue

        try:
            send_news(chat_id, cand)
            sent_count += 1
            state["sent_ids"].append(cand["id"])
            state["sent_ids"].extend(cand.get("duplicate_ids", []))
            state["recent_titles"].append({
                "title": cand["title"],
                "source": cand["source"],
                "ts": int(time.time()),
            })
            recent_titles.append(cand["title"])
            save_state(state)
            time.sleep(0.8)
        except Exception as e:
            print("send failed:", cand["source"], cand["title"], e)
            for item in state["pending_news"]:
                if item["id"] == cand["id"]:
                    item["retry_after"] = int(time.time()) + 300
                    break
            save_state(state)

    save_state(state)
    print(f"Done. Sent {sent_count} news item(s).")
    print(f"Pending news: {len(state.get('pending_news', []))} item(s).")


if __name__ == "__main__":
    main()
