"""Embed the current news snapshot so Telegram WebView can open offline."""
import json
import re
import time
from pathlib import Path


ARTICLES = Path("docs/articles.json")
INDEX = Path("docs/index.html")
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
    INDEX.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    build()
