import json
import unittest
from unittest.mock import patch

import bot
from refresh_artist_profiles import parse_reference,parse_events

class ProfileTests(unittest.TestCase):
    def test_music_infobox_is_scoped_and_removes_references(self):
        raw='<nav>archive menu</nav><table class="infobox"><tr><th>Genres</th><td>Metal</td></tr><tr><th>Members</th><td><ul><li><a href="/x">Musician One</a><sup>[1]</sup></li><li>Musician Two</li></ul></td></tr></table><aside>Someone Else</aside>'
        p=parse_reference(raw,'https://example.org/band')
        self.assertEqual([m['name'] for m in p['members']],['Musician One','Musician Two'])
        self.assertNotIn('menu',str(p));self.assertNotIn('Someone Else',str(p))

    def test_non_music_infobox_is_rejected(self):
        with self.assertRaises(ValueError):parse_reference('<table class="infobox"><tr><th>Height</th><td>2m</td></tr></table>','https://example.org')

    def test_album_is_not_an_artist_profile(self):
        with self.assertRaises(ValueError):parse_reference('<table class="infobox"><tr><th>Genres</th><td>Metal</td></tr><tr><th>Released</th><td>1984</td></tr></table>','https://example.org')

    def test_past_members_are_not_labelled_current(self):
        p=parse_reference('<table class="infobox"><tr><th>Genres</th><td>Rock</td></tr><tr><th>Past members</th><td>Former Singer</td></tr></table>','https://example.org')
        self.assertIn('Бывшие',p['members_note'])

    def test_structured_concert_dates_not_page_noise(self):
        events=[{'@type':'MusicEvent','startDate':'2026-10-03T20:00:00+05:30','location':{'name':'Venue','address':{'addressLocality':'Mumbai','addressCountry':'India'}},'performer':{'name':'Opeth'}},
                {'@type':'MusicEvent','startDate':'2026-10-04','eventStatus':'https://schema.org/EventCancelled','location':{'address':{'addressLocality':'Other'}}}]
        raw='<nav>1999-01-01</nav><script type="application/ld+json">'+json.dumps(events)+'</script>'
        result=parse_events(raw,'https://example.org/tour','Opeth')
        self.assertEqual(len(result),1);self.assertEqual(result[0]['date'],'2026-10-03');self.assertEqual(result[0]['city'],'Mumbai')
        self.assertEqual(parse_events(raw,'https://example.org/tour','Another Band'),[])

    def test_menu_is_set_and_verified_without_messages(self):
        expected={'type':'web_app','text':'Открыть','web_app':{'url':'https://example.org/?view=bands&v='+bot.WEBAPP_VERSION}}
        def api(method,payload):
            if method=='getChatMenuButton':return {'type':'commands'} if not hasattr(api,'set') else expected
            if method=='setChatMenuButton':api.set=True;return True
            self.fail('Menu setup must not send messages')
        with patch.object(bot,'get_webapp_base_url',return_value='https://example.org/'),patch.object(bot,'telegram_api',side_effect=api) as mocked:
            bot.configure_open_menu('123')
        mutations=[c for c in mocked.call_args_list if c.args[0]=='setChatMenuButton']
        self.assertEqual(len(mutations),1)
        self.assertEqual(mutations[0].args[1]['menu_button'],expected)

    def test_bandzoogle_requires_reviewed_year_and_matching_weekday(self):
        raw='<div class="event-description"><div class="date-long"><span class="date">Wednesday, October 21</span></div><div class="event-location"><a href="https://www.google.com/maps/search/?query=KYTTARO%2C%20Athina%2C%20Greece">KYTTARO</a></div></div>'
        self.assertEqual(parse_events(raw,'https://wittr.com/'),[])
        events=parse_events(raw,'https://wittr.com/',calendar_year=2026)
        self.assertEqual(events[0]['date'],'2026-10-21')
        self.assertEqual(events[0]['city'],'Athina')
        self.assertEqual(parse_events(raw,'https://wittr.com/',calendar_year=2027),[])

    def test_menu_verification_failure_is_reported(self):
        with patch.object(bot,'time'),patch.object(bot,'get_webapp_base_url',return_value='https://example.org/'),patch.object(bot,'telegram_api',return_value={'type':'commands'}):
            with self.assertRaises(RuntimeError):bot.configure_open_menu()

    def test_menu_readback_can_briefly_return_previous_value(self):
        expected={'type':'web_app','text':'Открыть','web_app':{'url':'https://example.org/?view=bands&v='+bot.WEBAPP_VERSION}}
        with patch.object(bot,'time') as clock,patch.object(bot,'get_webapp_base_url',return_value='https://example.org/'),patch.object(bot,'telegram_api',side_effect=[{'type':'commands'},True,{'type':'commands'},expected]) as api:
            bot.configure_open_menu()
        clock.sleep.assert_called_once_with(5)
        self.assertEqual(api.call_count,4)

    def test_both_published_feed_entry_urls_are_accepted(self):
        current={'type':'web_app','text':'Открыть','web_app':{'url':'https://example.org/?view=all&v='+bot.WEBAPP_VERSION}}
        with patch.object(bot,'get_webapp_base_url',return_value='https://example.org/'),patch.object(bot,'telegram_api',return_value=current) as api:
            bot.configure_open_menu()
        self.assertTrue(all(c.args[0]=='getChatMenuButton' for c in api.call_args_list))
