# News delivery frequency

Checked on 2026-10-02. The workflow was scheduled at minutes 7 and 37,
including the older version at commit 13c166e. GitHub's run history nevertheless
shows scheduled runs at 01:29, 07:42, 15:22, 20:27 UTC on October 1 and 00:07
on October 2. Manual runs finish normally. This demonstrates multi-hour gaps
in scheduler invocation, independently of article extraction or Telegram.

GitHub documents scheduled events as subject to delays and dropped jobs:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

The user chose to retain GitHub-only hosting. The workflow now requests a run
every five minutes, offset from the top of the hour. This is a requested cadence,
not a delivery guarantee. The source's own RSS publication delay, RSS2JSON's
Darkside feed caching, translation quotas and Pages deployment also add latency.
A continuously running service would be needed for predictable minute-level
polling; no such service or external scheduler was provisioned.

Previously only the first eight candidates were attempted. Now the limit is
eight successful sends, with an eight-minute processing budget. Failed items
do not prevent attempts on other news in that run. Discovered candidates are
persisted in state.json as pending_news before sending, with the full RSS body,
original URL and publication timestamp. Failed attempts wait at least five
minutes; refreshing the feed retains that cooldown. Sent and duplicate items
leave the queue. Overflow and failures survive feed rotation and restarts.
News which leaves a source feed before any bot run discovers it can still be
missed; the queue cannot recover an article it never fetched.

Serialized runs check out the latest main branch, including the preceding run's
state, rather than an older commit captured when a queued run was triggered.
State saving is attempted even when an earlier workflow step fails. A hard
runner termination or a failed git push still prevents persistence.

Regression tests cover queue reload after feed rotation, eight failing articles
followed by successful delivery, retained retry cooldowns, and overflow beyond
eight successful cards. Existing extraction, translation and Mini App tests
remain required. No UI changes or manual Telegram messages are part of this fix.
