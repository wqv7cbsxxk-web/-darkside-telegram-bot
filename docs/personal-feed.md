# Personal feeds in the existing Mini App

The home URL opens the archive. Existing ?id= article links still open the full
article directly; “К ленте” opens the archive. No Telegram messages are edited.

Views: all news, favorite artists, artist directory/profile, saved articles.
Event filters show tour/concert news and release news, including songs/videos.
Global event filters classify stories. Artist profiles now also contain sourced
concert dates where available; see group-profiles.md.
No dates, cities, discographies or external listings are invented.

Preferences use localStorage under metal-news.preferences.v1. They persist in
this browser/WebView, not across devices. Blocked storage displays a warning;
preferences still work during the current session. Favorite artists affect only
the Mini App feed. The bot retains its general Telegram notification behavior.
There is no inactive notification toggle pretending to personalize messages.

The shared docs/artists.json catalogue provides stable identifiers, names and
aliases. article_index.py attaches artists and topics to new runner output.
Existing archived articles were indexed without changing title, short, body,
IDs or publication times. Matches include mentions in the full text, not just
the principal subject. Common ambiguous words such as Tool/Yes/Death require
capitalization in the heading. Catalog coverage and alias coverage are finite.
Users can add an artist themselves, matched by its exact name in the text.

Saved articles remain accessible while present in the rolling 150-item archive.
The UI does not imply permanently downloaded or offline copies.

Python tests cover boundaries, multiple artists, Russian aliases, original
English headings and topic classification. Node tests execute the actual inline
Mini App script and verify intact articles, favorite persistence, artist and
event filters. Browser checks cover navigation, favorite selection and
reload, saved stories and the complete six-track Darkside article.
