import json
import os
import re
import sys
import time
from html import unescape
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RSS2JSON_URL = (
    "https://api.rss2json.com/v1/api.json"
    "?rss_url=http%3A%2F%2Fwww.darkside.ru%2Frss%2F"
)
STATE_FILE = Path("state.json")
TG_API = "https://api.telegram.org/bot{}"
MAX_SEEN = 200

# Оставляем запас относительно лимита Rich Message 32768 UTF-8 байт.
MAX_RICH_BYTES = 28000
MAX_ARTICLE_CHARS = 12000


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def telegram(token, method, payload=None, timeout=30):
    url = f"{TG_API.format(token)}/{method}"
    response = requests.post(url, json=payload or {}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]


def discover_chat_id(token):
    telegram(token, "deleteWebhook", {"drop_pending_updates": False})
    updates = telegram(token, "getUpdates", {"timeout": 0, "limit": 100})

    for update in reversed(updates):
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        chat = message.get("chat", {})
        if chat.get("type") == "private":
            return chat.get("id")

    return None


def fetch_items():
    response = requests.get(
        RSS2JSON_URL,
        timeout=30,
        headers={"User-Agent": "darkside-telegram-bot/2.0"},
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "ok":
        raise RuntimeError(f"RSS2JSON error: {data}")

    return data.get("items", [])


def clean_html(value):
    if not value:
        return ""

    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def escape_html(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def text_to_paragraphs(text):
    text = text.strip()
    if not text:
        return "<p>Текст новости отсутствует в RSS.</p>"

    chunks = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    return "".join(
        f"<p>{escape_html(p).replace(chr(10), '<br>')}</p>"
        for p in chunks
    )


def split_article_body(text, max_chars=MAX_ARTICLE_CHARS):
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    parts = []
    remaining = text

    while len(remaining) > max_chars:
        cut = remaining.rfind("\n\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = remaining.rfind("\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = remaining.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars

        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def item_to_details(item):
    title = clean_html(item.get("title", "")).strip() or "Без заголовка"
    body = clean_html(item.get("content") or item.get("description") or "")

    body_parts = split_article_body(body)
    details = []

    for idx, body_part in enumerate(body_parts, start=1):
        suffix = f" ({idx}/{len(body_parts)})" if len(body_parts) > 1 else ""
        summary = escape_html(title + suffix)
        details.append(
            "<details>"
            f"<summary>{summary}</summary>"
            f"{text_to_paragraphs(body_part)}"
            "</details>"
        )

    return details


def rich_message_html(details_blocks):
    return (
        "<h3>📰 Новые новости Darkside</h3>"
        + "".join(details_blocks)
    )


def send_rich_digest(token, chat_id, items):
    # RSS идёт от новых к старым. Пользователю показываем в хронологическом порядке.
    all_details = []
    for item in reversed(items):
        all_details.extend(item_to_details(item))

    batch = []

    for details in all_details:
        candidate = rich_message_html(batch + [details])

        if len(candidate.encode("utf-8")) > MAX_RICH_BYTES and batch:
            telegram(
                token,
                "sendRichMessage",
                {
                    "chat_id": chat_id,
                    "rich_message": {"html": rich_message_html(batch)},
                },
            )
            time.sleep(1)
            batch = [details]
        else:
            batch.append(details)

    if batch:
        telegram(
            token,
            "sendRichMessage",
            {
                "chat_id": chat_id,
                "rich_message": {"html": rich_message_html(batch)},
            },
        )


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Secret TELEGRAM_BOT_TOKEN is missing")

    state = load_state()
    chat_id = state.get("chat_id")

    # Первичная привязка чата
    if not chat_id:
        chat_id = discover_chat_id(token)

        if not chat_id:
            print(
                "Chat ID not found. Send /start to the Telegram bot, "
                "then run this workflow again."
            )
            return

        items = fetch_items()

        state["chat_id"] = chat_id
        state["seen_guids"] = [
            str(item.get("guid") or item.get("link"))
            for item in items
            if item.get("guid") or item.get("link")
        ][:MAX_SEEN]

        save_state(state)

        telegram(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "✅ Darkside-рассылка подключена.\n"
                    "Старые новости отправляться не будут."
                ),
            },
        )

        print(f"Saved chat_id={chat_id} and initialized feed state.")
        return

    items = fetch_items()
    seen = set(state.get("seen_guids", []))

    new_items = []
    for item in items:
        guid = str(item.get("guid") or item.get("link") or "")
        if guid and guid not in seen:
            new_items.append(item)

    if new_items:
        send_rich_digest(token, chat_id, new_items)

    current_guids = [
        str(item.get("guid") or item.get("link"))
        for item in items
        if item.get("guid") or item.get("link")
    ]

    old_guids = state.get("seen_guids", [])
    merged = current_guids + [guid for guid in old_guids if guid not in current_guids]
    state["seen_guids"] = merged[:MAX_SEEN]

    save_state(state)
    print(f"New items sent: {len(new_items)}")


if __name__ == "__main__":
    main()
