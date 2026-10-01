# Darkside article completeness regression

Baseline: `693a4fc`. Investigated article: https://www.darkside.ru/news/184168/.

## Reproduced cause

The committed `articles.json` already contained only four paragraphs (intro and
tracks 1–3), while its `short` contained all six tracks. The data was saved by
commit `66f2413` using `python bot.py`, before the workflow switched to `runner.py`.
The old `bot.prepare_texts` takes at most six source paragraphs and then saves
`expanded = translated_paragraphs[:4]`. Passing the complete Russian introduction
and six tracks through that function with identity translation reproduces the
exact four-paragraph cutoff. The Mini App renders every supplied paragraph using
`textContent`; neither JSON serialization nor its renderer removes tracks.
Already-sent IDs prevent later scheduled runs from rebuilding those records.

## Additional verified pipeline failures

At baseline, `runner.fetch_full_article` returns an empty list for the actual
WOLVES page: the text uses `font.tdn` and `br`, not `p`. Its malformed closing
`a`/`font` tags also cause Python's `html.parser` to move the body outside the
expected container. Browser/HTML5 parsing retains it inside `div[align=justify]`.
The page declares Windows-1251; decoding the original response bytes respects it.

When RSS is selected, short English track titles are submitted to translation.
Rejected providers return an empty string, and the paragraph disappears. The
sentence fallback added in `693a4fc` also drops individual failed sentences.

## Fix

* Parse Darkside response bytes with HTML5 rules and extract only its observed
  news-body container. Exclude image widgets and embedded media. Keep all lines,
  short track titles and long quotations; no minimum body-size gate for Darkside.
* Preserve the Russian Darkside edition, including original track/release names.
* Retain original sentences/chunks when translation providers fail.
* Rebuild the six saved Darkside records without changing IDs, ordering or sent
  state, and without sending Telegram messages. The existing UI is unchanged.

## Validation

Frozen raw page fixtures were fetched on 2026-10-02 (Novosibirsk time).
WOLVES: 7 paragraphs, all six numbered tracks and durations. SHOGUN MOJO:
11 paragraphs, all ten tracks. NIGHTWISH: six paragraphs, complete long quotes.
Additional real pages checked: 184165, 184166, 184177 and 184181.
No navigation, band archives, comments, social links, ads or HTML tags were found
in extracted material. Telegram payload was captured locally, not sent; its
short preview and `Читать` URL were checked against the saved full JSON record.
The existing Mini App JavaScript was executed with the actual JSON and a DOM
adapter, verifying all seven WOLVES paragraphs render without truncation.

Run from repository root:

```sh
python -m unittest discover -s tests -v
node tests/test_mini_app.cjs
```

The Python tests run before the aggregator in GitHub Actions. Actual Telegram
client interaction is not automated by these tests. Failed translation can leave
an original-language fragment in an English-source article; it no longer silently
erases the fragment.
