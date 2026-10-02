# Open button and artist information

configure_menu.py sets a real Telegram MenuButtonWebApp labelled “Открыть”,
pointing to the existing Mini App at ?view=bands (a legacy menu URL now routed to the news feed). It checks the current default
menu and the configured private-chat override, updates only differences and
reads them back for verification. It sends no messages. A dedicated push-triggered
workflow activates it using the existing Telegram secrets; normal bot runs also
keep the menu configured. Negative group/channel IDs do not receive a private
chat menu override.

Artist pages have Overview, News, Tour, Where now, Members, Albums and Setlists sections. Direct
?band= links open the appropriate artist. Existing ?id= links keep the complete
article reader. Preferences are still local to the user's device.

The initial data covers all 128 catalogue entries with sources and checked dates:
Wikipedia music infoboxes for most reference facts; existing news for the three
new projects without a suitable encyclopedia entry. No scraped menus, navigation,
comments, image captions or biographies are copied into the profile.
References are attributed in each profile. These are factual catalogue fields,
not copies of encyclopedia articles. Common names use explicitly matched music
pages, avoiding disambiguation pages such as Emperor and Wasp.

Current official lineup pages were reviewed for Deep Purple and Opeth. Reviewed
I Am Morbid/Terrorizer notes include Sandoval's September 30 departure and
Vincent's departure, and clearly identify incomplete or last-known lineups.
After 30 days those manual lineup overrides expire in the UI in favor of the
attributed reference, with a notice that the manual verification has expired.
Former members are labelled former when the source provides only that list.

Seed schedules include 42 Deep Purple dates from the official structured feed,
four Opeth dates from the official public widget, two I Am Morbid Italian dates
from the published promoter announcement, and 19 Wolves dates from their
current official website. Wolves' year 2026 was explicitly checked against the
European tour poster; the parser requires the reviewed year and validates every
printed weekday rather than assuming a year from today's date.

"Where now" shows the next date in our available schedule or the dated
performance listed for today, without claiming it is the band's physical
location. Missing future events means coverage is unavailable, not that the
artist is inactive or has no tour. A schedule is partial and can change.

refresh_artist_profiles.py runs after delivery/state persistence. It uses a
40-second budget and up to six reference entries and four eligible tour sources,
so it does not prevent news messages being sent first. Reference data refreshes
at seven-day intervals, structured schedules at six-hour intervals. The actual
refresh cadence depends on GitHub's scheduler. Failures retain known data and
back off; JS-only event widgets are not mistaken for an empty schedule. Public
artist websites can provide MusicEvent/Event JSON-LD, but generic event data must
name the expected performer. No private API keys or location tracking are used.

Python tests cover source scoping, disambiguation rejection, former members,
JSON-LD concerts, cancellation, performer matching, explicit calendar year and
menu verification. The actual Mini App JavaScript is tested for profile tabs,
future dates and all existing full-text/favorite behavior. Live browser checks
verify the artist menu, roster and tour screens after publication.
