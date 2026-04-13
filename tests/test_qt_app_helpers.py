import unittest
from datetime import datetime
from types import SimpleNamespace

from config import FIVE_E_UNRANKED, normalize_five_e_rank
from qt_app import (
    account_last_used_at,
    account_sort_timestamp,
    five_e_rank_sort_value,
    format_five_e_rank,
    is_account_banned_or_frozen,
    reset_account_five_e_rank_to_unranked,
)


MESSAGES = {
    "five_e_rank_unranked": "未定级",
    "previous_five_e_rank_note": "上赛季5E分段：{rank}（记录于 {date}）",
}


class QtAppHelperTests(unittest.TestCase):
    def test_account_last_used_falls_back_to_updated_at(self):
        account = SimpleNamespace(last_login="", updated_at="2026-04-13 09:30:00")

        self.assertEqual(account_last_used_at(account), datetime(2026, 4, 13, 9, 30))

    def test_account_sort_timestamp_handles_empty_dates(self):
        account = SimpleNamespace(last_login="", updated_at="")

        self.assertIsInstance(account_sort_timestamp(account), int)

    def test_banned_or_frozen_detection(self):
        now = datetime(2026, 4, 13, 10, 0)

        self.assertTrue(is_account_banned_or_frozen(SimpleNamespace(status="frozen", frozen_until=""), now=now))
        self.assertTrue(is_account_banned_or_frozen(SimpleNamespace(status="active", frozen_until="2026-04-14 10:00"), now=now))
        self.assertFalse(is_account_banned_or_frozen(SimpleNamespace(status="active", frozen_until="2026-04-12 10:00"), now=now))

    def test_five_e_rank_order(self):
        self.assertLess(five_e_rank_sort_value("S"), five_e_rank_sort_value("A++"))
        self.assertLess(five_e_rank_sort_value("A++"), five_e_rank_sort_value("A+"))
        self.assertLess(five_e_rank_sort_value("A+"), five_e_rank_sort_value("A"))
        self.assertLess(five_e_rank_sort_value("C"), five_e_rank_sort_value("D"))
        self.assertGreater(five_e_rank_sort_value(""), five_e_rank_sort_value("D"))

    def test_blank_five_e_rank_normalizes_to_unranked(self):
        self.assertEqual(normalize_five_e_rank(""), FIVE_E_UNRANKED)
        self.assertEqual(format_five_e_rank("", MESSAGES), "未定级")

    def test_reset_rank_archives_ranked_account(self):
        account = SimpleNamespace(five_e_rank="A++", note="old note")

        archived = reset_account_five_e_rank_to_unranked(account, MESSAGES, "2026-04-13")

        self.assertTrue(archived)
        self.assertEqual(account.five_e_rank, FIVE_E_UNRANKED)
        self.assertIn("old note", account.note)
        self.assertIn("上赛季5E分段：A++（记录于 2026-04-13）", account.note)

    def test_reset_rank_does_not_archive_unranked_account(self):
        account = SimpleNamespace(five_e_rank=FIVE_E_UNRANKED, note="")

        archived = reset_account_five_e_rank_to_unranked(account, MESSAGES, "2026-04-13")

        self.assertFalse(archived)
        self.assertEqual(account.five_e_rank, FIVE_E_UNRANKED)
        self.assertEqual(account.note, "")

    def test_reset_rank_replaces_existing_previous_rank_note(self):
        account = SimpleNamespace(
            five_e_rank="S",
            note="first line\n上赛季5E分段：A++（记录于 2026-01-01）\nlast line",
        )

        archived = reset_account_five_e_rank_to_unranked(account, MESSAGES, "2026-04-13")

        self.assertTrue(archived)
        self.assertEqual(account.five_e_rank, FIVE_E_UNRANKED)
        self.assertIn("first line", account.note)
        self.assertIn("上赛季5E分段：S（记录于 2026-04-13）", account.note)
        self.assertIn("last line", account.note)
        self.assertNotIn("A++（记录于 2026-01-01）", account.note)


if __name__ == "__main__":
    unittest.main()
