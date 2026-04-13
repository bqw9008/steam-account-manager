import unittest

from qt_app import compact_import_accounts
from text_importer import parse_account_block, split_import_blocks


class TextImporterTests(unittest.TestCase):
    def test_compact_steam_first_line(self):
        account = parse_account_block(
            "steam账号steam_login密码steam_pass邮箱账号mail@example.com "
            "密码mail_pass邮箱地址mail.example.com手机号13800000000"
            "5E账号five_login密码：five_pass"
        )

        self.assertEqual(account["profile_name"], "steam_login")
        self.assertEqual(account["login_name"], "steam_login")
        self.assertEqual(account["password"], "steam_pass")
        self.assertEqual(account["email"], "mail@example.com")
        self.assertEqual(account["phone"], "13800000000")
        self.assertIn("5E昵称: five_login", account["note"])
        self.assertNotIn("5E账号: five_login", account["note"])
        self.assertIn("5E密码: five_pass", account["note"])
        self.assertIn("邮箱地址: mail.example.com", account["note"])
        self.assertIn("邮箱密码: mail_pass", account["note"])

    def test_compact_five_e_first_line_keeps_steam_as_unique_name(self):
        account = parse_account_block(
            "5e账号：five_login 密码：five_pass 昵称：visible_name "
            "steam账号steam_login密码steam_pass油箱账号mail@example.com密码mail_pass"
        )

        self.assertEqual(account["profile_name"], "steam_login")
        self.assertEqual(account["login_name"], "steam_login")
        self.assertEqual(account["password"], "steam_pass")
        self.assertEqual(account["email"], "mail@example.com")
        self.assertIn("5E昵称: visible_name", account["note"])
        self.assertIn("5E昵称: five_login", account["note"])
        self.assertNotIn("5E账号: five_login", account["note"])
        self.assertIn("5E密码: five_pass", account["note"])

    def test_eleven_digit_five_e_account_is_account_and_phone_fallback(self):
        account = parse_account_block(
            "5e账号：13800000000 密码：five_pass steam账号steam_login密码steam_pass"
        )

        self.assertEqual(account["profile_name"], "steam_login")
        self.assertEqual(account["login_name"], "steam_login")
        self.assertEqual(account["phone"], "13800000000")
        self.assertIn("5E账号: 13800000000", account["note"])
        self.assertNotIn("5E昵称: 13800000000", account["note"])

    def test_colon_values_are_trimmed(self):
        account = parse_account_block(
            "steam账号: steam_login 密码: steam_pass 邮箱账号: email_user@example.com 密码: mail_pass"
        )

        self.assertEqual(account["login_name"], "steam_login")
        self.assertEqual(account["password"], "steam_pass")
        self.assertEqual(account["email"], "email_user@example.com")
        self.assertIn("邮箱密码: mail_pass", account["note"])

    def test_blank_lines_split_accounts(self):
        blocks = split_import_blocks(
            "steam账号one密码one_pass\n\n\n"
            "5e账号：five 密码：five_pass 昵称：nick steam账号two密码two_pass"
        )

        self.assertEqual(len(blocks), 2)
        self.assertEqual(parse_account_block(blocks[0])["login_name"], "one")
        self.assertEqual(parse_account_block(blocks[1])["login_name"], "two")

    def test_duplicate_import_accounts_keep_last_for_preview_and_save(self):
        first = parse_account_block("steam账号same密码first_pass邮箱账号first@example.com密码mail_pass")
        second = parse_account_block("steam账号same密码second_pass邮箱账号second@example.com密码mail_pass")
        other = parse_account_block("steam账号other密码other_pass")

        compacted, duplicate_login_names = compact_import_accounts([first, second, other])

        self.assertEqual(duplicate_login_names, ["same"])
        self.assertEqual(len(compacted), 2)
        self.assertEqual(compacted[0]["login_name"], "same")
        self.assertEqual(compacted[0]["password"], "second_pass")
        self.assertEqual(compacted[0]["email"], "second@example.com")
        self.assertEqual(compacted[1]["login_name"], "other")


if __name__ == "__main__":
    unittest.main()
