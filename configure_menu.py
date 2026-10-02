"""One-shot, verifiable menu setup. Does not fetch news or send messages."""
import bot

if __name__ == '__main__':
    bot.configure_open_menu(bot.resolve_chat_id(bot.load_state()))
