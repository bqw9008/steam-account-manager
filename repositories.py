from __future__ import annotations

import json
import os
from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

try:
    from .models import SteamAccount
except ImportError:
    from models import SteamAccount


@dataclass
class LoadIssue:
    file_path: Path
    backup_path: Path | None
    error: str


class InvalidDataFileError(ValueError):
    pass


def write_text_atomically(file_path: Path, content: str) -> None:
    temp_path = file_path.with_name(f"{file_path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, file_path)
    except OSError:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def describe_json_type(value: object) -> str:
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return "number"
    return type(value).__name__


class AccountRepository:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.last_load_issue: LoadIssue | None = None
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            write_text_atomically(self.file_path, "[]")

    def backup_invalid_file(self) -> Path | None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.file_path.with_name(
            f"{self.file_path.stem}.invalid-{timestamp}{self.file_path.suffix}"
        )
        try:
            backup_path.write_text(self.file_path.read_text(encoding="utf-8"), encoding="utf-8")
            return backup_path
        except OSError:
            return None

    def load_accounts(self) -> list[SteamAccount]:
        self.last_load_issue = None
        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, list):
                raise InvalidDataFileError(
                    f"Expected accounts data to be a list, got {describe_json_type(raw_data)}."
                )
            invalid_indexes = [
                str(index + 1)
                for index, item in enumerate(raw_data)
                if not isinstance(item, dict)
            ]
            if invalid_indexes:
                raise InvalidDataFileError(
                    "Expected every account entry to be an object. "
                    f"Invalid item positions: {', '.join(invalid_indexes[:10])}."
                )
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, InvalidDataFileError) as error:
            backup_path = self.backup_invalid_file()
            self.last_load_issue = LoadIssue(
                file_path=self.file_path,
                backup_path=backup_path,
                error=str(error),
            )
            raw_data = []
        return [SteamAccount.from_dict(item) for item in raw_data]

    def save_accounts(self, accounts: list[SteamAccount]) -> None:
        serialized = [asdict(account) for account in accounts]
        write_text_atomically(
            self.file_path,
            json.dumps(serialized, ensure_ascii=False, indent=2),
        )


class SettingsRepository:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.last_load_issue: LoadIssue | None = None
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            write_text_atomically(self.file_path, "{}")

    def backup_invalid_file(self) -> Path | None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.file_path.with_name(
            f"{self.file_path.stem}.invalid-{timestamp}{self.file_path.suffix}"
        )
        try:
            backup_path.write_text(self.file_path.read_text(encoding="utf-8"), encoding="utf-8")
            return backup_path
        except OSError:
            return None

    def load_settings(self) -> dict:
        self.last_load_issue = None
        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, dict):
                raise InvalidDataFileError(
                    f"Expected settings data to be an object, got {describe_json_type(raw_data)}."
                )
            return raw_data
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, InvalidDataFileError) as error:
            backup_path = self.backup_invalid_file()
            self.last_load_issue = LoadIssue(
                file_path=self.file_path,
                backup_path=backup_path,
                error=str(error),
            )
            return {}

    def save_settings(self, settings: dict) -> None:
        write_text_atomically(
            self.file_path,
            json.dumps(settings, ensure_ascii=False, indent=2),
        )
