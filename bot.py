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
    # Manybot больше не нужен: снимаем его webhook, чтобы получить /start напрямую.
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
        headers={"User-Agent": "darkside-telegram-bot/1.0"},
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
    )


def escape_attr(text):
    return escape_html(text).replace('"', "&quot;")


def send_plain_chunks(token, chat_id, text, chunk_size=3900):
    text = text.strip()
    while text:
        if len(text) <= chunk_size:
            chunk = text
            text = ""
        else:
            cut = text[:chunk_size].rfind("\n")
            if cut < chunk_size // 2:
                cut = text[:chunk_size].rfind(" ")
            if cut < chunk_size // 2:
                cut = chunk_size
            chunk = text[:cut].rstrip()
            text = text[cut:].lstrip()

        telegram(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
        )


def send_item(token, chat_id, item):
    title = clean_html(item.get("title", "")).strip()
    link = item.get("link") or item.get("guid") or ""
    body = clean_html(item.get("content") or item.get("description") or "")
    thumbnail = item.get("thumbnail") or ""

    header_parts = []
    if title:
        header_parts.append(f"<b>{escape_html(title)}</b>")
    if link:
        header_parts.append(f'<a href="{escape_attr(link)}">Открыть на Darkside</a>')
    header = "\n\n".join(header_parts)

    photo_sent = False
    if thumbnail:
        try:
            telegram(
                token,
                "sendPhoto",
                {
                    "chat_id": chat_id,
                    "photo": thumbnail,
                    "caption": header[:1000],
                    "parse_mode": "HTML",
                },
            )
            photo_sent = True
        except Exception as exc:
            print(f"Photo send failed, fallback to text: {exc}", file=sys.stderr)

    if not photo_sent and header:
        telegram(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": header,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
        )

    if body:
        send_plain_chunks(token, chat_id, body)


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

    # RSS идёт от новых к старым. В Telegram отправляем в нормальной хронологии.
    for item in reversed(new_items):
        send_item(token, chat_id, item)
        time.sleep(1)

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
