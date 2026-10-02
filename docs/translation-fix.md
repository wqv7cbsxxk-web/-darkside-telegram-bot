# ThePRP translation recovery

Reported article: Tom Morello's Power To The People festival (stored ID
`a2eca72dfedde75b3fb4e85cbf20243bb7ac00bd`). Baseline: `424bcfd`.

## Evidence

GitHub Actions run `36944377614`, job `110642956789`, shows Google returning
HTTP 429, unavailable Lingva instances, and MyMemory subsequently returning
HTTP 429. The preservation fallback saved the English original, including its
title, instead of deleting the article. This is a shared translation-provider
failure, not a ThePRP language setting.

An independent MyMemory request over 500 characters returned HTTP 200 with
`responseStatus: "403"` and `QUERY LENGTH LIMIT EXCEEDED. MAX ALLOWED QUERY : 500
CHARS`. The old 760-character chunks could therefore fail even when the service
was available. Short translations and artist-only lists also failed the previous
minimum-Cyrillic validation.

The actual ThePRP page has an `.entry-content` news body and unrelated sidebar
`article` elements. Its Instagram embed contains the unwanted `A post shared by`
paragraph. Extraction now selects the news body directly and excludes embeds.

## Changes and verification

* Limit provider requests to 450 characters, check MyMemory's response status,
  accept short Russian translations, and reject damaged entity placeholders.
* Cache successful translations across Actions runs; cache failures only as
  provider cooldowns. Respect HTTP 429 / Retry-After rather than repeatedly
  exhausting the same provider for every sentence.
* Protect artist and release names emphasized in the source news body.
* Defer new news items with incomplete translations. They are not sent to
  Telegram or marked seen and remain eligible for the next feed run.
* Retry already saved untranslated articles without sending duplicate messages.
  Failed repairs have a one-hour retry delay so they cannot starve other repairs.
* Re-extract and supply reviewed Russian translations for all ten existing
  ThePRP articles. Retain complete quotations, dates, lineups and tracklists.
  Include these reviewed translations in the cache for subsequent runs.

A live MyMemory fallback test translated the real Morello introductory paragraph
using requests of 438 and 66 characters, with the primary provider deliberately
unavailable. No source fragments were lost. Automated tests cover parser scope,
Instagram exclusion, request sizes, JSON-level errors, persisted cache, HTTP 429,
short translations, placeholder integrity and deferral without marking seen.
The unchanged Mini App script renders the full Russian Morello article and still
renders all six WOLVES IN THE THRONE ROOM tracks.

These changes do not remove third-party quotas. If every provider is unavailable,
new English-source news waits for a later successful translation instead of being
sent as an untranslated card. Feed retention still limits how long an unseen
item can be retried.
