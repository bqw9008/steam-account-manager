from __future__ import annotations

import re

try:
    from .config import STATUS_OPTIONS, get_translations
except ImportError:
    from config import STATUS_OPTIONS, get_translations


def clean_import_value(value: str) -> str:
    return value.strip().strip("-|:：;,，")


def looks_like_account_start(line: str) -> bool:
    normalized = line.strip()
    return bool(
        re.match(
            r"^(?:[-|,，;；\s]*)?(?:5[eE]账号|5[eE]\s*account|steam账号|Steam账号|steam\s*account)\s*[:：]?",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def looks_like_complete_account_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip()
    has_steam = re.search(r"(?:steam账号|Steam账号|steam\s*account)\s*[:：]?", normalized, re.IGNORECASE)
    has_email = re.search(r"(?:邮箱账号|油箱账号|邮箱|油箱|email\s*account|email)\s*[:：]?", normalized, re.IGNORECASE)
    return bool(has_steam and has_email)


def split_import_blocks(raw_text: str) -> list[str]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        return []

    if len(lines) > 1 and all(looks_like_complete_account_line(line) for line in lines):
        return lines

    if len(lines) > 1:
        blocks: list[str] = []
        current_lines: list[str] = []
        for line in lines:
            if looks_like_account_start(line) and current_lines:
                blocks.append(" ".join(current_lines).strip())
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines:
            blocks.append(" ".join(current_lines).strip())
        return [block for block in blocks if block]

    blocks = re.split(
        r"(?=(?:5[eE]账号|5[eE]\s*account|steam账号|Steam账号|steam\s*account)\s*[:：]?)",
        normalized,
        flags=re.IGNORECASE,
    )
    return [block.strip() for block in blocks if block.strip()]


def parse_account_block(block: str, language_code: str = "zh_CN") -> dict:
    normalized_block = re.sub(r"\s+", " ", block).strip()
    messages = get_translations(language_code)

    five_e_label = r"(?:5[eE]账号|5[eE]\s*account)"
    password_label = r"(?:(?:5[eE]|steam|Steam)\s*)?(?:密码|password)"
    steam_label = r"(?:steam账号|Steam账号|steam\s*account)"
    email_account_label = r"(?:邮箱账号|油箱账号|email\s*account)"
    email_address_label = r"(?:邮箱地址|油箱地址)"
    email_label = rf"(?:{email_account_label}|{email_address_label}|邮箱|油箱|email)"
    phone_label = r"(?:手机号|手机|phone)"
    nickname_label = r"(?:昵称|nickname)"
    field_boundary_labels = (
        five_e_label,
        steam_label,
        email_account_label,
        email_address_label,
        phone_label,
        nickname_label,
    )

    def find_next_field_boundary(text: str, start_index: int, ignored_pattern: str) -> int:
        boundary_index = len(text)
        for label_pattern in field_boundary_labels:
            if label_pattern == ignored_pattern:
                continue
            match = re.search(label_pattern, text[start_index:], flags=re.IGNORECASE)
            if match:
                boundary_index = min(boundary_index, start_index + match.start())
        return boundary_index

    def search_pair(patterns: tuple[str, ...]) -> tuple[str, str]:
        for pattern in patterns:
            label_match = re.search(pattern, normalized_block, flags=re.IGNORECASE)
            if not label_match:
                continue

            value_start = label_match.end()
            value_end = find_next_field_boundary(normalized_block, value_start, pattern)
            section = normalized_block[value_start:value_end].strip()
            match = re.search(password_label, section, flags=re.IGNORECASE)
            if match:
                return (
                    clean_import_value(section[:match.start()]),
                    clean_import_value(section[match.end():]),
                )
        return "", ""

    def search_single(patterns: tuple[str, ...]) -> str:
        for pattern in patterns:
            match = re.search(pattern, normalized_block, flags=re.IGNORECASE)
            if match:
                return clean_import_value(match.group("value"))
        return ""

    five_e_account, five_e_password = search_pair(
        (
            rf"{five_e_label}\s*[:：]?",
        )
    )
    steam_account, steam_password = search_pair(
        (
            rf"{steam_label}\s*[:：]?",
        )
    )
    email_account, email_password = search_pair(
        (
            rf"{email_account_label}\s*[:：]?",
            rf"{email_label}\s*[:：]?",
        )
    )
    nickname = search_single(
        (
            rf"{nickname_label}\s*[:：]?\s*(?P<value>.*?)(?=(?:----|{five_e_label}|{steam_label}|{email_label}|{phone_label}|$))",
        )
    )

    note_parts = []
    if five_e_account:
        note_parts.append(f"{messages['note_5e_account_label']}: {five_e_account}")
    if five_e_password:
        note_parts.append(f"{messages['note_5e_password_label']}: {five_e_password}")
    if email_password:
        note_parts.append(f"{messages['note_email_password_label']}: {email_password}")

    return {
        "profile_name": nickname or steam_account or email_account or five_e_account,
        "login_name": steam_account,
        "password": steam_password,
        "email": email_account,
        "phone": five_e_account,
        "status": STATUS_OPTIONS[0],
        "last_login": "",
        "note": "\n".join(note_parts),
    }
