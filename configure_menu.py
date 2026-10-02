"""One-shot, verifiable menu setup. Does not fetch news or send messages."""
import bot

if __name__ == '__main__':
    # Only public button configuration is logged, never tokens or chat IDs.
    current = bot.telegram_api('getChatMenuButton', {}) or {}
    print('Default menu:', {k: current.get(k) for k in ('type', 'text', 'web_app')}, flush=True)
    bot.configure_open_menu(bot.resolve_chat_id(bot.load_state()))
