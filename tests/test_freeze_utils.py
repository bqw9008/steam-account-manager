import unittest
from datetime import datetime

from freeze_utils import format_frozen_remaining, parse_frozen_until


MESSAGES = {
    "frozen_remaining_not_set": "Not set",
    "frozen_remaining_expired": "Ended",
    "frozen_remaining_days_hours": "About {days}d {hours}h",
    "frozen_remaining_hours_minutes": "About {hours}h {minutes}m",
    "frozen_remaining_minutes": "About {minutes}m",
}


class FreezeUtilsTests(unittest.TestCase):
    def test_parse_date_only_uses_end_of_day(self):
        parsed = parse_frozen_until("2026-04-30")

        self.assertEqual(parsed, datetime(2026, 4, 30, 23, 59, 59))

    def test_format_days_hours(self):
        remaining = format_frozen_remaining(
            "2026-04-15 14:00",
            MESSAGES,
            now=datetime(2026, 4, 13, 10, 30),
        )

        self.assertEqual(remaining, "About 2d 3h")

    def test_format_hours_minutes(self):
        remaining = format_frozen_remaining(
            "2026-04-13 12:10",
            MESSAGES,
            now=datetime(2026, 4, 13, 10, 30),
        )

        self.assertEqual(remaining, "About 1h 40m")

    def test_expired_or_invalid(self):
        self.assertEqual(
            format_frozen_remaining("2026-04-12 10:30", MESSAGES, now=datetime(2026, 4, 13, 10, 30)),
            "Ended",
        )
        self.assertEqual(format_frozen_remaining("bad date", MESSAGES), "Not set")


if __name__ == "__main__":
    unittest.main()
