"""Embed the current news snapshot so Telegram WebView can open offline."""
import json
import re
import time
from pathlib import Path


ARTICLES = Path("docs/articles.json")
INDEX = Path("docs/index.html")
MUSIC = Path("docs/music-data.js")
APP = Path("docs/app.js")
STYLES = Path("docs/app.css")
PROFILES = Path("docs/artist_profiles.json")
ARTISTS = Path("docs/artists.json")
MUSIC_CACHE = Path("docs/music_cache.json")
PATTERN = re.compile(
    r'(<script id="articlesSeed" type="application/json">).*?(</script>)',
    re.DOTALL,
)


def build():
    articles = json.loads(ARTICLES.read_text(encoding="utf-8")).get("articles", [])
    payload = json.dumps({"articles": articles, "generated_at": int(time.time() * 1000)}, ensure_ascii=False, separators=(",", ":"))
    # Prevent article text from closing the raw-text script element.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = INDEX.read_text(encoding="utf-8")
    updated, count = PATTERN.subn(lambda m: m.group(1) + payload + m.group(2), html, count=1)
    if count != 1:
        raise RuntimeError("articlesSeed element is missing from docs/index.html")
    music = MUSIC.read_text(encoding="utf-8").replace("</script", "<\\/script")
    updated, count = re.subn(
        r'(<script id="musicData">).*?(</script>)',
        lambda m: m.group(1) + music + m.group(2), updated, count=1, flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("musicData element is missing from docs/index.html")
    json_seeds = {"profilesSeed", "artistsSeed", "musicSeed"}
    for element, source, script in [("appCode", APP, True), ("appStyles", STYLES, False), ("profilesSeed", PROFILES, True), ("artistsSeed", ARTISTS, True), ("musicSeed", MUSIC_CACHE, True)]:
        text = source.read_text(encoding="utf-8")
        if element in json_seeds:
            text = json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))
            text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        tag = "script" if script else "style"
        if script:
            text = text.replace("</script", "<\\/script")
        updated, count = re.subn(
            rf'(<{tag} id="{element}"[^>]*>).*?(</{tag}>)',
            lambda m: m.group(1) + text + m.group(2), updated, count=1, flags=re.DOTALL,
        )
        if count != 1:
            raise RuntimeError(f"{element} element is missing from docs/index.html")
    INDEX.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    build()
