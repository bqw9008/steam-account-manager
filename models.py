from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

try:
    from .config import STATUS_OPTIONS, normalize_five_e_rank, normalize_status_value
except ImportError:
    from config import STATUS_OPTIONS, normalize_five_e_rank, normalize_status_value


@dataclass
class SteamAccount:
    account_id: str
    profile_name: str
    login_name: str
    password: str
    email: str
    phone: str
    group_name: str
    five_e_nickname: str
    five_e_rank: str
    status: str
    last_login: str
    frozen_until: str
    note: str
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        profile_name: str,
        login_name: str,
        password: str,
        email: str,
        phone: str,
        status: str,
        last_login: str,
        note: str,
        group_name: str = "",
        five_e_nickname: str = "",
        frozen_until: str = "",
        five_e_rank: str = "",
    ) -> "SteamAccount":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return cls(
            account_id=str(uuid4()),
            profile_name=profile_name.strip(),
            login_name=login_name.strip(),
            password=password,
            email=email.strip(),
            phone=phone.strip(),
            group_name=group_name.strip(),
            five_e_nickname=five_e_nickname.strip(),
            five_e_rank=normalize_five_e_rank(five_e_rank),
            status=normalize_status_value(status),
            last_login=last_login.strip(),
            frozen_until=frozen_until.strip(),
            note=note.strip(),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def from_dict(cls, payload: dict) -> "SteamAccount":
        return cls(
            account_id=payload.get("account_id", str(uuid4())),
            profile_name=payload.get("profile_name", ""),
            login_name=payload.get("login_name", ""),
            password=payload.get("password", ""),
            email=payload.get("email", ""),
            phone=payload.get("phone", ""),
            group_name=payload.get("group_name", ""),
            five_e_nickname=payload.get("five_e_nickname", ""),
            five_e_rank=normalize_five_e_rank(payload.get("five_e_rank", "")),
            status=normalize_status_value(payload.get("status", STATUS_OPTIONS[0])),
            last_login=payload.get("last_login", ""),
            frozen_until=payload.get("frozen_until", ""),
            note=payload.get("note", ""),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
        )
