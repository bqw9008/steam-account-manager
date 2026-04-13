from __future__ import annotations

import copy
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QToolBar,
    QVBoxLayout, QWidget,
)

try:
    from .config import DATA_FILE, SETTINGS_FILE, get_status_label, get_status_options, get_translations, normalize_language, normalize_status_value
    from .models import SteamAccount
    from .repositories import AccountRepository, SettingsRepository
    from .system_utils import detect_steam_executable, detect_system_language, get_windows_theme_mode, is_process_running, request_steam_shutdown, terminate_steam_processes, wait_for_steam_processes_exit
    from .text_importer import parse_account_block, split_import_blocks
except ImportError:
    from config import DATA_FILE, SETTINGS_FILE, get_status_label, get_status_options, get_translations, normalize_language, normalize_status_value
    from models import SteamAccount
    from repositories import AccountRepository, SettingsRepository
    from system_utils import detect_steam_executable, detect_system_language, get_windows_theme_mode, is_process_running, request_steam_shutdown, terminate_steam_processes, wait_for_steam_processes_exit
    from text_importer import parse_account_block, split_import_blocks


class LoginSignals(QObject):
    status = Signal(str)
    finished = Signal(bool, str)
    force_close_requested = Signal(object)


class AccountDialog(QDialog):
    def __init__(self, parent, messages, language, account=None):
        super().__init__(parent)
        self.messages = messages
        self.language = language
        self.account = account
        self.setWindowTitle(messages["detail_title"])
        self.resize(560, 520)
        self.profile_name = QLineEdit(account.profile_name if account else "")
        self.login_name = QLineEdit(account.login_name if account else "")
        self.password = QLineEdit(account.password if account else "")
        self.password.setEchoMode(QLineEdit.Password)
        self.email = QLineEdit(account.email if account else "")
        self.phone = QLineEdit(account.phone if account else "")
        self.status = QComboBox(); self.status.addItems(get_status_options(language))
        self.status.setCurrentText(get_status_label(account.status, language) if account else get_status_options(language)[0])
        self.last_login = QLineEdit(account.last_login if account else "")
        self.note = QTextEdit(account.note if account else "")
        show_password = QCheckBox(messages["show_password"])
        show_password.toggled.connect(lambda checked: self.password.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password))
        form = QFormLayout()
        for label, widget in [
            ("field_profile_name", self.profile_name), ("field_login_name", self.login_name),
            ("field_password", self.password), ("", show_password), ("field_email", self.email),
            ("field_phone", self.phone), ("field_status", self.status), ("field_last_login", self.last_login),
            ("field_note", self.note),
        ]:
            form.addRow(messages[label] if label else "", widget)
        save = QPushButton(messages["button_save"]); save.clicked.connect(self.accept)
        close = QPushButton(messages["button_close"]); close.clicked.connect(self.reject)
        buttons = QHBoxLayout(); buttons.addStretch(); buttons.addWidget(save); buttons.addWidget(close)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons)

    def data(self):
        return {
            "profile_name": self.profile_name.text().strip(),
            "login_name": self.login_name.text().strip(),
            "password": self.password.text(),
            "email": self.email.text().strip(),
            "phone": self.phone.text().strip(),
            "status": normalize_status_value(self.status.currentText()),
            "last_login": self.last_login.text().strip(),
            "note": self.note.toPlainText().strip(),
        }


class TextDialog(QDialog):
    def __init__(self, parent, messages, title_key):
        super().__init__(parent)
        self.messages = messages
        self.setWindowTitle(messages[title_key])
        self.resize(760, 520)
        self.text = QTextEdit(); self.text.setPlaceholderText(messages["import_dialog_description"])
        start = QPushButton(messages["button_start_import"]); start.clicked.connect(self.accept)
        close = QPushButton(messages["button_close"]); close.clicked.connect(self.reject)
        footer = QHBoxLayout(); footer.addWidget(start); footer.addWidget(close); footer.addStretch()
        layout = QVBoxLayout(self); layout.addWidget(QLabel(messages["import_dialog_heading"])); layout.addWidget(self.text, 1); layout.addLayout(footer)

    def value(self):
        return self.text.toPlainText().strip()


class SteamDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_app = parent
        m = parent.messages
        self.setWindowTitle(m["steam_login_dialog_title"]); self.resize(640, 360)
        account = parent.current_account()
        selected = m["selection_current"].format(profile_name=account.profile_name, login_name=account.login_name) if account else m["default_selection"]
        status = QLabel(parent.login_status_text); status.setWordWrap(True); parent.login_status_changed.connect(status.setText)
        strategy = QComboBox(); strategy.addItems([label for _, label in parent.shutdown_options()])
        strategy.setCurrentText(parent.shutdown_label(parent.settings.get("steam_shutdown_strategy")))
        strategy.currentTextChanged.connect(parent.set_shutdown_strategy)
        login = QPushButton(m["button_start_auto_login"]); login.clicked.connect(parent.login_selected_account)
        choose = QPushButton(m["button_choose_steam"]); choose.clicked.connect(parent.choose_steam_executable)
        close = QPushButton(m["button_close"]); close.clicked.connect(self.close)
        footer = QHBoxLayout(); footer.addWidget(login); footer.addWidget(choose); footer.addWidget(close); footer.addStretch()
        layout = QVBoxLayout(self)
        for text in (m["steam_login_dialog_heading"], selected, m["auto_login_hint"]):
            label = QLabel(text); label.setWordWrap(True); layout.addWidget(label)
        form = QFormLayout(); form.addRow(m["steam_shutdown_strategy_label"], strategy); layout.addLayout(form)
        layout.addWidget(status); layout.addStretch(); layout.addLayout(footer)


class SteamAccountManagerQt(QMainWindow):
    login_status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings_repo = SettingsRepository(SETTINGS_FILE); self.settings = self.settings_repo.load_settings()
        self.language = normalize_language(self.settings.get("language") or detect_system_language())
        self.messages = get_translations(self.language); self.status_options = get_status_options(self.language)
        self.repo = AccountRepository(DATA_FILE); self.accounts = self.repo.load_accounts()
        self.current_account_id = None; self.login_in_progress = False; self.login_status_text = self.messages["login_status_idle"]
        self.signals = LoginSignals(); self.signals.status.connect(self.set_login_status); self.signals.finished.connect(self.finish_login); self.signals.force_close_requested.connect(self.answer_force_close)
        self.setWindowTitle(self.messages["app_title"]); self.resize(1240, 760)
        self.build_ui(); self.apply_style(); self.refresh_table(); self.report_load_issues()

    def t(self, key, **kwargs): return self.messages[key].format(**kwargs)

    def build_ui(self):
        root = QWidget(); layout = QVBoxLayout(root)
        title = QLabel(self.messages["app_title"]); title.setObjectName("Title")
        subtitle = QLabel(self.messages["app_subtitle"]); subtitle.setObjectName("Subtitle")
        layout.addWidget(title); layout.addWidget(subtitle)
        bar = QToolBar(); self.search = QLineEdit(); self.search.setPlaceholderText(self.messages["search_label"]); self.search.textChanged.connect(self.refresh_table)
        self.status_filter = QComboBox(); self.status_filter.addItems([self.messages["status_all"], *self.status_options]); self.status_filter.currentTextChanged.connect(self.refresh_table)
        bar.addWidget(QLabel(self.messages["search_label"])); bar.addWidget(self.search); bar.addWidget(QLabel(self.messages["status_filter_label"])); bar.addWidget(self.status_filter); bar.addSeparator()
        for text, fn in [
            ("button_new", self.new_account), ("detail_title", self.edit_account), ("button_login", self.open_steam_dialog),
            ("button_quick_line_import", lambda: self.open_text_import("quick_line_dialog_title")),
            ("button_import", lambda: self.open_text_import("import_dialog_title")), ("button_delete", self.delete_selected),
        ]:
            button = QPushButton(self.messages[text]); button.clicked.connect(fn); bar.addWidget(button)
        layout.addWidget(bar)
        batch = QHBoxLayout(); self.batch_status = QComboBox(); self.batch_status.addItems(self.status_options)
        apply_status = QPushButton(self.messages["button_apply_batch_status"]); apply_status.clicked.connect(self.apply_batch_status)
        batch.addWidget(QLabel(self.messages["batch_status_label"])); batch.addWidget(self.batch_status); batch.addWidget(apply_status); batch.addStretch(); layout.addLayout(batch)
        self.table = QTableWidget(0, 7); self.table.setHorizontalHeaderLabels([self.messages["column_profile_name"], self.messages["column_login_name"], self.messages["field_email"], self.messages["field_phone"], self.messages["column_status"], self.messages["column_last_login"], "Updated"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setSelectionMode(QTableWidget.ExtendedSelection); self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.selection_changed); self.table.doubleClicked.connect(self.edit_account)
        layout.addWidget(self.table, 1); self.summary = QLabel(); layout.addWidget(self.summary); self.setCentralWidget(root)

    def apply_style(self):
        if get_windows_theme_mode() == "dark":
            colors = {
                "app": "#0f172a", "surface": "#111827", "card": "#1f2937", "text": "#e5edf7",
                "muted": "#a5b4c7", "border": "#334155", "header": "#1e293b",
                "primary": "#2563eb", "primary_hover": "#1d4ed8", "selected": "#2563eb",
            }
        else:
            colors = {
                "app": "#eef3f8", "surface": "#ffffff", "card": "#ffffff", "text": "#16324f",
                "muted": "#688099", "border": "#d5deea", "header": "#e8eef6",
                "primary": "#2563eb", "primary_hover": "#1d4ed8", "selected": "#2c7be5",
            }
        self.setStyleSheet(f'''
            QWidget {{
                background: {colors["app"]};
                color: {colors["text"]};
                font-family: "Microsoft YaHei UI";
            }}
            QLabel#Title {{
                font-size: 26px;
                font-weight: 800;
                color: {colors["text"]};
            }}
            QLabel#Subtitle {{
                color: {colors["muted"]};
            }}
            QLineEdit, QTextEdit, QComboBox, QTableWidget {{
                background: {colors["surface"]};
                color: {colors["text"]};
                border: 1px solid {colors["border"]};
                border-radius: 6px;
                padding: 6px;
            }}
            QTableWidget {{
                gridline-color: {colors["border"]};
                selection-background-color: {colors["selected"]};
                selection-color: white;
            }}
            QPushButton {{
                background: {colors["primary"]};
                color: white;
                border: 0;
                border-radius: 7px;
                padding: 8px 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {colors["primary_hover"]};
            }}
            QToolBar {{
                border: 0;
                spacing: 8px;
                background: {colors["app"]};
            }}
            QHeaderView::section {{
                background: {colors["header"]};
                color: {colors["text"]};
                padding: 7px;
                border: 0;
                font-weight: 700;
            }}
            QComboBox QAbstractItemView {{
                background: {colors["surface"]};
                color: {colors["text"]};
                selection-background-color: {colors["selected"]};
            }}
        ''')

    def report_load_issues(self):
        for key, issue in [("settings_load_failed", self.settings_repo.last_load_issue), ("accounts_load_failed", self.repo.last_load_issue)]:
            if issue:
                backup = issue.backup_path or self.messages["backup_not_created"]
                QMessageBox.warning(self, self.messages["data_load_issue_title"], self.t(key, path=issue.file_path, backup_path=backup, error=issue.error))

    def filtered_accounts(self):
        keyword = self.search.text().strip().lower(); status = self.status_filter.currentText().strip(); result = []
        for account in self.accounts:
            if status != self.messages["status_all"] and account.status != normalize_status_value(status): continue
            haystack = " ".join([account.profile_name, account.login_name, account.email, account.phone, account.note]).lower()
            if keyword and keyword not in haystack: continue
            result.append(account)
        return sorted(result, key=lambda a: a.updated_at, reverse=True)

    def refresh_table(self):
        selected = self.selected_ids(); rows = self.filtered_accounts(); self.table.setRowCount(0)
        for account in rows:
            row = self.table.rowCount(); self.table.insertRow(row)
            values = [account.profile_name, account.login_name, account.email, account.phone, get_status_label(account.status, self.language), account.last_login or "-", account.updated_at]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value); item.setData(Qt.UserRole, account.account_id); self.table.setItem(row, col, item)
            if account.account_id in selected: self.table.selectRow(row)
        self.summary.setText(self.t("summary_text", total=len(self.accounts), filtered=len(rows)))

    def selected_ids(self):
        return {item.data(Qt.UserRole) for item in self.table.selectedItems() if item.data(Qt.UserRole)}

    def selected_accounts(self):
        ids = self.selected_ids(); return [a for a in self.accounts if a.account_id in ids]

    def selection_changed(self):
        selected = self.selected_accounts(); self.current_account_id = selected[0].account_id if selected else None

    def current_account(self):
        selected = self.selected_accounts()
        if selected: return selected[0]
        return next((a for a in self.accounts if a.account_id == self.current_account_id), None)

    def find_by_login(self, login_name):
        target = login_name.strip().lower(); return next((a for a in self.accounts if a.login_name.strip().lower() == target), None)

    def save_accounts(self):
        try: self.repo.save_accounts(self.accounts); return True
        except OSError as e: QMessageBox.critical(self, self.messages["error_title"], self.t("save_accounts_failed", error=e, path=self.repo.file_path)); return False

    def save_settings(self, settings):
        try: self.settings_repo.save_settings(settings); self.settings = settings; return True
        except OSError as e: QMessageBox.critical(self, self.messages["error_title"], self.t("save_settings_failed", error=e, path=self.settings_repo.file_path)); return False

    def new_account(self): self.edit_account_dialog(None)

    def edit_account(self):
        account = self.current_account()
        if not account: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["select_account_warning"]); return
        self.edit_account_dialog(account)

    def edit_account_dialog(self, account):
        dialog = AccountDialog(self, self.messages, self.language, account)
        if dialog.exec() != QDialog.Accepted: return
        data = dialog.data()
        if not data["profile_name"]: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["account_name_required"]); return
        if not data["login_name"]: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["login_name_required"]); return
        duplicate = self.find_by_login(data["login_name"])
        if duplicate and (not account or duplicate.account_id != account.account_id): QMessageBox.warning(self, self.messages["prompt_title"], self.t("login_name_duplicate", login_name=data["login_name"])); return
        old = copy.deepcopy(self.accounts)
        if account:
            for key, value in data.items(): setattr(account, key, value)
            account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); message = self.messages["account_updated_success"]
        else:
            account = SteamAccount.create(**data); self.accounts.append(account); message = self.messages["account_created_success"]
        if not self.save_accounts(): self.accounts = old; return
        self.current_account_id = account.account_id; self.refresh_table(); QMessageBox.information(self, self.messages["success_title"], message)

    def parse_import(self, text):
        parsed, skipped = [], 0
        for block in split_import_blocks(text):
            data = parse_account_block(block, language_code=self.language)
            if not data["login_name"] or not data["password"]: skipped += 1; continue
            parsed.append(data)
        return parsed, skipped

    def open_text_import(self, title_key):
        dialog = TextDialog(self, self.messages, title_key)
        if dialog.exec() != QDialog.Accepted: return
        raw = dialog.value()
        if not raw: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["import_empty_warning"]); return
        parsed, skipped = self.parse_import(raw)
        if not parsed: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["import_no_match_warning"]); return
        created = sum(1 for d in parsed if not self.find_by_login(d["login_name"])); updated = len(parsed) - created
        if QMessageBox.question(self, self.messages["import_preview_title"], self.t("import_preview_summary", created=created, updated=updated, skipped=skipped) + "\n\n" + self.messages["import_confirm_question"]) != QMessageBox.Yes: return
        old = copy.deepcopy(self.accounts); latest = {d["login_name"].strip().lower(): d for d in parsed}; created = updated = 0
        for data in latest.values():
            account = self.find_by_login(data["login_name"])
            if account:
                for key in ("profile_name", "login_name", "password", "email", "phone", "status", "last_login", "note"):
                    if data[key]: setattr(account, key, data[key])
                account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); updated += 1
            else:
                self.accounts.append(SteamAccount.create(**data)); created += 1
        if not self.save_accounts(): self.accounts = old; return
        self.refresh_table(); QMessageBox.information(self, self.messages["import_result_title"], self.t("import_result_summary", created=created, updated=updated, skipped=skipped))

    def apply_batch_status(self):
        selected = self.selected_accounts()
        if not selected: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["batch_no_selection_warning"]); return
        status_key = normalize_status_value(self.batch_status.currentText()); status_label = get_status_label(status_key, self.language)
        if QMessageBox.question(self, self.messages["batch_status_confirm_title"], self.t("batch_status_confirm_message", count=len(selected), status=status_label)) != QMessageBox.Yes: return
        old = copy.deepcopy(self.accounts); now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for account in selected: account.status = status_key; account.updated_at = now
        if not self.save_accounts(): self.accounts = old; return
        self.refresh_table(); QMessageBox.information(self, self.messages["success_title"], self.t("batch_status_success", count=len(selected), status=status_label))

    def delete_selected(self):
        selected = self.selected_accounts()
        if not selected: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["select_account_warning"]); return
        message = self.t("delete_confirm_message", profile_name=selected[0].profile_name) if len(selected) == 1 else self.t("batch_delete_confirm_message", count=len(selected))
        if QMessageBox.question(self, self.messages["delete_confirm_title"], message) != QMessageBox.Yes: return
        old = copy.deepcopy(self.accounts); ids = {a.account_id for a in selected}; self.accounts = [a for a in self.accounts if a.account_id not in ids]
        if not self.save_accounts(): self.accounts = old; return
        self.refresh_table(); QMessageBox.information(self, self.messages["success_title"], self.messages["account_deleted_success"] if len(ids) == 1 else self.t("batch_deleted_success", count=len(ids)))

    def shutdown_options(self): return [("graceful_then_force", self.messages["steam_shutdown_strategy_graceful_then_force"]), ("force", self.messages["steam_shutdown_strategy_force"])]
    def shutdown_key(self, label): return next((k for k, v in self.shutdown_options() if v == label), label if label in {"graceful_then_force", "force"} else "graceful_then_force")
    def shutdown_label(self, key): return next((v for k, v in self.shutdown_options() if k == key), self.messages["steam_shutdown_strategy_graceful_then_force"])
    def set_shutdown_strategy(self, label): updated = dict(self.settings); updated["steam_shutdown_strategy"] = self.shutdown_key(label); self.save_settings(updated)
    def open_steam_dialog(self): SteamDialog(self).exec()
    def valid_steam(self, path): return path.exists() and path.is_file() and path.name.lower() == "steam.exe"

    def choose_steam_executable(self):
        detected = detect_steam_executable()
        if detected and self.valid_steam(detected):
            updated = dict(self.settings)
            updated["steam_path"] = str(detected)
            if self.save_settings(updated):
                self.set_login_status(self.t("steam_path_set_status", path=detected))
                QMessageBox.information(
                    self,
                    self.messages["success_title"],
                    self.t("steam_path_set_status", path=detected),
                )
                return detected

        path, _ = QFileDialog.getOpenFileName(self, self.messages["choose_steam_exe_title"], str(Path(self.settings.get("steam_path", "")).parent) if self.settings.get("steam_path") else r"C:\Program Files (x86)\Steam", "steam.exe (steam.exe)")
        if not path: return None
        steam_path = Path(path)
        if not self.valid_steam(steam_path): QMessageBox.warning(self, self.messages["invalid_steam_path_title"], self.t("invalid_steam_path_warning", path=steam_path)); return None
        updated = dict(self.settings); updated["steam_path"] = str(steam_path)
        if self.save_settings(updated): self.set_login_status(self.t("steam_path_set_status", path=steam_path)); return steam_path
        return None

    def resolve_steam(self):
        stored = self.settings.get("steam_path", "")
        if stored and self.valid_steam(Path(stored)): return Path(stored)
        detected = detect_steam_executable()
        if detected and self.valid_steam(detected): updated = dict(self.settings); updated["steam_path"] = str(detected); self.save_settings(updated); return detected
        QMessageBox.information(self, self.messages["prompt_title"], self.messages["steam_not_detected_info"]); return self.choose_steam_executable()

    def set_login_status(self, message): self.login_status_text = self.t("login_status_prefix", message=message); self.login_status_changed.emit(self.login_status_text)

    def login_selected_account(self):
        if self.login_in_progress: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["login_in_progress_warning"]); return
        account = self.current_account()
        if not account: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["select_account_warning"]); return
        if not account.login_name: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["missing_login_warning"]); return
        if not account.password: QMessageBox.warning(self, self.messages["prompt_title"], self.messages["missing_password_warning"]); return
        steam_path = self.resolve_steam()
        if not steam_path: self.set_login_status(self.messages["steam_path_missing_status"]); return
        self.login_in_progress = True; self.set_login_status(self.t("launching_login_status", profile_name=account.profile_name or account.login_name))
        threading.Thread(target=self.perform_login, args=(steam_path, account.login_name, account.password, account.profile_name or account.login_name), daemon=True).start()

    def perform_login(self, steam_path, login_name, password, profile_name):
        try:
            if is_process_running("steam.exe") or is_process_running("steamwebhelper.exe"):
                if self.shutdown_key(self.settings.get("steam_shutdown_strategy")) == "force":
                    self.signals.status.emit(self.messages["steam_force_closing_running_status"])
                    if not terminate_steam_processes(): raise RuntimeError(self.messages["steam_running_close_required_error"])
                else:
                    self.signals.status.emit(self.messages["steam_graceful_closing_running_status"]); request_steam_shutdown(steam_path)
                    if not wait_for_steam_processes_exit(timeout_seconds=12.0):
                        q = queue.Queue(maxsize=1); self.signals.force_close_requested.emit(q)
                        if not q.get(): raise RuntimeError(self.messages["steam_force_close_cancelled_error"])
                        self.signals.status.emit(self.messages["steam_force_closing_running_status"])
                        if not terminate_steam_processes(): raise RuntimeError(self.messages["steam_running_close_required_error"])
            subprocess.Popen([str(steam_path), "-login", login_name, password], cwd=str(steam_path.parent))
            self.signals.status.emit(self.messages["steam_started_status"]); time.sleep(1.0)
            self.signals.finished.emit(True, self.t("login_success_status", profile_name=profile_name))
        except Exception as e:
            self.signals.finished.emit(False, str(e))

    def answer_force_close(self, q): q.put(QMessageBox.question(self, self.messages["steam_force_close_confirm_title"], self.messages["steam_force_close_confirm_message"]) == QMessageBox.Yes)

    def finish_login(self, success, message):
        self.login_in_progress = False; self.set_login_status(message)
        if not success: QMessageBox.critical(self, self.messages["steam_login_failed_title"], message); return
        if self.settings.get("hide_login_attempt_notice", False): return
        box = QMessageBox(self); box.setWindowTitle(self.messages["login_attempt_notice_title"]); box.setText(self.messages["login_attempt_notice_message"]); cb = QCheckBox(self.messages["login_attempt_notice_dont_show_again"]); box.setCheckBox(cb); box.exec()
        if cb.isChecked(): updated = dict(self.settings); updated["hide_login_attempt_notice"] = True; self.save_settings(updated)


def main():
    app = QApplication(sys.argv)
    window = SteamAccountManagerQt()
    window.show()
    sys.exit(app.exec())
