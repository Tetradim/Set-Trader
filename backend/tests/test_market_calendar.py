"""Unit checks for exchange calendar-backed market status."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from market_calendar import CALENDAR_BY_MARKET, _load_calendar, get_calendar_status
from markets import MARKETS


class MarketCalendarTest(unittest.TestCase):
    def test_all_configured_exchange_calendars_load(self):
        for code, calendar_name in CALENDAR_BY_MARKET.items():
            with self.subTest(market=code, calendar=calendar_name):
                self.assertIsNotNone(_load_calendar(calendar_name))

    def test_us_holiday_uses_exchange_calendar(self):
        market = MARKETS["US"]
        now = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))

        self.assertFalse(market.is_open_now(now))
        self.assertEqual("closed", market.status(now))
        calendar = get_calendar_status("US", now)
        self.assertIsNotNone(calendar)
        self.assertTrue(calendar.is_holiday)
        self.assertEqual("exchange_closed", calendar.reason)

    def test_hong_kong_lunch_break_uses_calendar_break(self):
        market = MARKETS["HK"]
        now = datetime(2026, 5, 26, 12, 30, tzinfo=ZoneInfo("Asia/Hong_Kong"))

        self.assertFalse(market.is_open_now(now))
        self.assertEqual("lunch", market.status(now))
        data = market.to_dict()
        self.assertIn("calendar_source", data)

    def test_regular_session_reports_open(self):
        market = MARKETS["UK"]
        now = datetime(2026, 5, 26, 10, 0, tzinfo=ZoneInfo("Europe/London"))

        self.assertTrue(market.is_open_now(now))
        self.assertEqual("open", market.status(now))


if __name__ == "__main__":
    unittest.main()
