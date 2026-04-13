from __future__ import annotations

import re

try:
    from .config import STATUS_OPTIONS, get_translations
except ImportError:
    from config import STATUS_OPTIONS, get_translations


FIELD_LABEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("five_e_account", r"5[eE]\s*账号|5[eE]\s*account"),
    ("steam_account", r"steam\s*账号|Steam\s*账号|steam\s*account"),
    ("email_account", r"邮箱账号|油箱账号|email\s*account"),
    ("email_address", r"邮箱地址|油箱地址|email\s*address"),
    ("phone", r"手机号|手机|(?<![A-Za-z0-9_])phone(?![A-Za-z0-9_])"),
    ("nickname", r"昵称|(?<![A-Za-z0-9_])nickname(?![A-Za-z0-9_])"),
    ("email_account", r"邮箱|油箱|(?<![A-Za-z0-9_])email(?![A-Za-z0-9_])"),
    ("password", r"密码|(?<![A-Za-z0-9_])password(?![A-Za-z0-9_])"),
)

FIELD_LABEL_REGEX = re.compile(
    "|".join(
        f"(?P<{field_name}_{index}>{pattern})"
        for index, (field_name, pattern) in enumerate(FIELD_LABEL_PATTERNS)
    ),
    flags=re.IGNORECASE,
)


def clean_import_value(value: str) -> str:
    return value.strip().strip("-|:：;,，").strip()


def get_field_name(match: re.Match[str]) -> str:
    for group_name, value in match.groupdict().items():
        if value is not None:
            return group_name.rsplit("_", 1)[0]
    return ""


def is_eleven_digit_phone(value: str) -> bool:
    return bool(re.fullmatch(r"\d{11}", value.strip()))


def looks_like_account_start(line: str) -> bool:
    normalized = line.strip()
    return bool(
        re.match(
            r"^(?:[-|,，;；\s]*)?(?:5[eE]\s*账号|5[eE]\s*account|steam\s*账号|Steam\s*账号|steam\s*account)\s*[:：]?",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def looks_like_complete_account_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip()
    has_steam = re.search(
        r"(?:steam\s*账号|Steam\s*账号|steam\s*account)\s*[:：]?",
        normalized,
        re.IGNORECASE,
    )
    has_password = re.search(r"(?:密码|password)\s*[:：]?", normalized, re.IGNORECASE)
    return bool(has_steam and has_password)


def block_has_steam_credentials(block: str) -> bool:
    parsed = parse_account_block(block)
    return bool(parsed["login_name"] and parsed["password"])


def split_import_blocks(raw_text: str) -> list[str]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    paragraphs = [
        " ".join(line.strip() for line in paragraph.split("\n") if line.strip())
        for paragraph in re.split(r"\n\s*\n+", normalized)
        if paragraph.strip()
    ]
    if len(paragraphs) > 1:
        return paragraphs

    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if len(lines) == 1 and looks_like_complete_account_line(lines[0]):
        return lines

    if len(lines) > 1:
        blocks: list[str] = []
        current_lines: list[str] = []
        for line in lines:
            current_block = " ".join(current_lines).strip()
            if (
                looks_like_account_start(line)
                and current_lines
                and block_has_steam_credentials(current_block)
            ):
                blocks.append(current_block)
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines:
            blocks.append(" ".join(current_lines).strip())
        return [block for block in blocks if block]

    blocks = re.split(
        r"(?=(?:steam\s*账号|Steam\s*账号|steam\s*account)\s*[:：]?)",
        normalized,
        flags=re.IGNORECASE,
    )
    return [block.strip() for block in blocks if block.strip()]


def parse_account_block(block: str, language_code: str = "zh_CN") -> dict:
    normalized_block = re.sub(r"\s+", " ", block).strip()
    messages = get_translations(language_code)
    fields = {
        "five_e_account": "",
        "five_e_password": "",
        "steam_account": "",
        "steam_password": "",
        "email_account": "",
        "email_password": "",
        "email_address": "",
        "phone": "",
        "nickname": "",
    }
    password_target = ""
    matches = list(FIELD_LABEL_REGEX.finditer(normalized_block))

    for index, match in enumerate(matches):
        field_name = get_field_name(match)
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized_block)
        value = clean_import_value(normalized_block[match.end():value_end])

        if field_name == "password":
            if password_target == "five_e_account" and value and not fields["five_e_password"]:
                fields["five_e_password"] = value
            elif password_target == "steam_account" and value and not fields["steam_password"]:
                fields["steam_password"] = value
            elif password_target in {"email_account", "email_address"} and value and not fields["email_password"]:
                fields["email_password"] = value
            elif value and fields["steam_account"] and not fields["steam_password"]:
                fields["steam_password"] = value
            continue

        if field_name in {
            "five_e_account",
            "steam_account",
            "email_account",
            "email_address",
            "phone",
            "nickname",
        }:
            if value and not fields[field_name]:
                fields[field_name] = value
            if field_name in {"five_e_account", "steam_account", "email_account", "email_address"}:
                password_target = field_name

    email_account = fields["email_account"] or fields["email_address"]
    five_e_account = fields["five_e_account"]
    five_e_nicknames: list[str] = []
    if fields["nickname"]:
        five_e_nicknames.append(fields["nickname"])
    if five_e_account:
        if is_eleven_digit_phone(five_e_account):
            if not fields["phone"]:
                fields["phone"] = five_e_account
        else:
            if five_e_account not in five_e_nicknames:
                five_e_nicknames.append(five_e_account)
            five_e_account = ""

    note_parts = []
    for five_e_nickname in five_e_nicknames:
        note_parts.append(f"{messages['note_5e_nickname_label']}: {five_e_nickname}")
    if five_e_account:
        note_parts.append(f"{messages['note_5e_account_label']}: {five_e_account}")
    if fields["five_e_password"]:
        note_parts.append(f"{messages['note_5e_password_label']}: {fields['five_e_password']}")
    if fields["email_address"] and fields["email_address"] != email_account:
        note_parts.append(f"{messages['note_email_address_label']}: {fields['email_address']}")
    if fields["email_password"]:
        note_parts.append(f"{messages['note_email_password_label']}: {fields['email_password']}")

    return {
        "profile_name": fields["steam_account"],
        "login_name": fields["steam_account"],
        "password": fields["steam_password"],
        "email": email_account,
        "phone": fields["phone"],
        "status": STATUS_OPTIONS[0],
        "last_login": "",
        "note": "\n".join(note_parts),
    }
