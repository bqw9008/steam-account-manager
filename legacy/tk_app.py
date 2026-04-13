from __future__ import annotations

import copy
import queue
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from .config import (
        DATA_FILE,
        SETTINGS_FILE,
        THEMES,
        THEME_POLL_INTERVAL_MS,
        get_status_label,
        get_status_options,
        get_translations,
        normalize_language,
        normalize_status_value,
    )
    from .models import SteamAccount
    from .repositories import AccountRepository, LoadIssue, SettingsRepository
    from .system_utils import (
        apply_window_size,
        configure_tk_scaling,
        detect_system_language,
        detect_steam_executable,
        enable_high_dpi_awareness,
        get_windows_theme_mode,
        is_process_running,
        request_steam_shutdown,
        terminate_steam_processes,
        wait_for_steam_processes_exit,
    )
    from .text_importer import parse_account_block, split_import_blocks
except ImportError:
    from config import (
        DATA_FILE,
        SETTINGS_FILE,
        THEMES,
        THEME_POLL_INTERVAL_MS,
        get_status_label,
        get_status_options,
        get_translations,
        normalize_language,
        normalize_status_value,
    )
    from models import SteamAccount
    from repositories import AccountRepository, LoadIssue, SettingsRepository
    from system_utils import (
        apply_window_size,
        configure_tk_scaling,
        detect_system_language,
        detect_steam_executable,
        enable_high_dpi_awareness,
        get_windows_theme_mode,
        is_process_running,
        request_steam_shutdown,
        terminate_steam_processes,
        wait_for_steam_processes_exit,
    )
    from text_importer import parse_account_block, split_import_blocks


class SteamAccountManagerApp:
    def __init__(self, root: tk.Tk, dpi_scale: float = 1.0) -> None:
        self.root = root
        self.dpi_scale = dpi_scale
        self.theme_mode = get_windows_theme_mode()
        self.theme = THEMES[self.theme_mode]
        self.settings_repository = SettingsRepository(SETTINGS_FILE)
        self.settings = self.settings_repository.load_settings()
        self.language = normalize_language(self.settings.get("language") or detect_system_language())
        self.messages = get_translations(self.language)
        self.status_options = get_status_options(self.language)
        self.root.title(self.t("app_title"))
        apply_window_size(self.root, self.dpi_scale)
        self.root.configure(bg=self.theme["app_bg"])

        self.repository = AccountRepository(DATA_FILE)
        self.accounts = self.repository.load_accounts()
        self.load_issues: list[tuple[str, LoadIssue]] = []
        if self.settings_repository.last_load_issue:
            self.load_issues.append(("settings_load_failed", self.settings_repository.last_load_issue))
        if self.repository.last_load_issue:
            self.load_issues.append(("accounts_load_failed", self.repository.last_load_issue))
        self.current_account_id: str | None = None
        self.login_in_progress = False

        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value=self.t("status_all"))
        self.batch_status_var = tk.StringVar(value=self.status_options[0])
        self.form_vars = {
            "profile_name": tk.StringVar(),
            "login_name": tk.StringVar(),
            "password": tk.StringVar(),
            "email": tk.StringVar(),
            "phone": tk.StringVar(),
            "status": tk.StringVar(value=self.status_options[0]),
            "last_login": tk.StringVar(),
        }
        self.summary_var = tk.StringVar()
        self.selection_var = tk.StringVar(value=self.t("default_selection"))
        self.login_status_var = tk.StringVar(value=self.t("login_status_idle"))
        self.steam_shutdown_strategy_var = tk.StringVar(
            value=self.get_steam_shutdown_strategy_label(
                self.settings.get("steam_shutdown_strategy")
            )
        )
        self.password_visible = tk.BooleanVar(value=False)
        self.surface_frames: list[tk.Widget] = []
        self.header_frames: list[tk.Widget] = []
        self.main_frames: list[tk.Widget] = []
        self.primary_labels: list[tk.Widget] = []
        self.secondary_labels: list[tk.Widget] = []
        self.header_labels: list[tk.Widget] = []
        self.form_labels: list[tk.Widget] = []
        self.entry_widgets: list[tk.Widget] = []
        self.text_widgets: list[tk.Widget] = []
        self.checkbuttons: list[tk.Widget] = []
        self.comboboxes: list[ttk.Combobox] = []
        self.button_roles: dict[tk.Widget, str] = {}
        self.canvases: list[tk.Canvas] = []
        self.login_action_button: tk.Button | None = None

        self.setup_style()
        self.build_layout()
        self.apply_theme()
        self.watch_windows_theme()
        self.refresh_table()
        if self.load_issues:
            self.root.after(0, self.report_load_issues)

    def setup_style(self) -> None:
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure("Card.TFrame", background="#ffffff")
        self.style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        self.style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        self.style.configure(
            "Treeview.Heading",
            font=("Microsoft YaHei UI", 10, "bold"),
        )

    def register_frame(self, widget: tk.Widget, role: str = "surface") -> tk.Widget:
        if role == "header":
            self.header_frames.append(widget)
        elif role == "main":
            self.main_frames.append(widget)
        else:
            self.surface_frames.append(widget)
        return widget

    def register_label(self, widget: tk.Widget, role: str = "primary") -> tk.Widget:
        if role == "header":
            self.header_labels.append(widget)
        elif role == "secondary":
            self.secondary_labels.append(widget)
        elif role == "form":
            self.form_labels.append(widget)
        else:
            self.primary_labels.append(widget)
        return widget

    def register_entry(self, widget: tk.Widget) -> tk.Widget:
        self.entry_widgets.append(widget)
        return widget

    def register_text_widget(self, widget: tk.Widget) -> tk.Widget:
        self.text_widgets.append(widget)
        return widget

    def register_button(self, widget: tk.Widget, role: str) -> tk.Widget:
        self.button_roles[widget] = role
        return widget

    def register_checkbutton(self, widget: tk.Widget) -> tk.Widget:
        self.checkbuttons.append(widget)
        return widget

    def register_combobox(self, widget: ttk.Combobox) -> ttk.Combobox:
        self.comboboxes.append(widget)
        return widget

    def t(self, key: str, **kwargs) -> str:
        return self.messages[key].format(**kwargs)

    def get_status_key(self, status_value: str | None) -> str:
        return normalize_status_value(status_value)

    def get_status_label(self, status_value: str | None) -> str:
        return get_status_label(status_value, self.language)

    def get_steam_shutdown_strategy_options(self) -> list[tuple[str, str]]:
        return [
            ("graceful_then_force", self.t("steam_shutdown_strategy_graceful_then_force")),
            ("force", self.t("steam_shutdown_strategy_force")),
        ]

    def get_steam_shutdown_strategy_key(self, label: str | None) -> str:
        for key, option_label in self.get_steam_shutdown_strategy_options():
            if label == option_label:
                return key
        stored_key = str(label or "").strip()
        if stored_key in {"graceful_then_force", "force"}:
            return stored_key
        return "graceful_then_force"

    def get_steam_shutdown_strategy_label(self, strategy_key: str | None) -> str:
        normalized_key = strategy_key if strategy_key in {"graceful_then_force", "force"} else "graceful_then_force"
        for key, label in self.get_steam_shutdown_strategy_options():
            if key == normalized_key:
                return label
        return self.t("steam_shutdown_strategy_graceful_then_force")

    def clone_accounts(self) -> list[SteamAccount]:
        return copy.deepcopy(self.accounts)

    def save_accounts_with_feedback(self) -> bool:
        try:
            self.repository.save_accounts(self.accounts)
            return True
        except OSError as error:
            messagebox.showerror(
                self.t("error_title"),
                self.t(
                    "save_accounts_failed",
                    error=error,
                    path=self.repository.file_path,
                ),
            )
            return False

    def save_settings_with_feedback(self, settings: dict) -> bool:
        try:
            self.settings_repository.save_settings(settings)
            self.settings = settings
            return True
        except OSError as error:
            messagebox.showerror(
                self.t("error_title"),
                self.t(
                    "save_settings_failed",
                    error=error,
                    path=self.settings_repository.file_path,
                ),
            )
            return False

    def on_steam_shutdown_strategy_change(self, event: tk.Event | None = None) -> None:
        strategy_key = self.get_steam_shutdown_strategy_key(self.steam_shutdown_strategy_var.get())
        self.steam_shutdown_strategy_var.set(self.get_steam_shutdown_strategy_label(strategy_key))
        updated_settings = dict(self.settings)
        updated_settings["steam_shutdown_strategy"] = strategy_key
        self.save_settings_with_feedback(updated_settings)

    def report_load_issues(self) -> None:
        for translation_key, issue in self.load_issues:
            backup_path = issue.backup_path or self.t("backup_not_created")
            messagebox.showwarning(
                self.t("data_load_issue_title"),
                self.t(
                    translation_key,
                    path=issue.file_path,
                    backup_path=backup_path,
                    error=issue.error,
                ),
            )

    def get_button_colors(self, role: str) -> tuple[str, str, str]:
        return self.theme["button"].get(role, self.theme["button"]["neutral"])

    def apply_theme(self) -> None:
        self.theme = THEMES[self.theme_mode]
        theme = self.theme
        self.root.configure(bg=theme["app_bg"])

        for frame in self.main_frames:
            frame.configure(bg=theme["app_bg"])

        for frame in self.surface_frames:
            frame.configure(bg=theme["surface_bg"], highlightbackground=theme["border"])

        for canvas in self.canvases:
            canvas.configure(bg=theme["surface_bg"])

        for frame in self.header_frames:
            frame.configure(bg=theme["header_bg"], highlightbackground=theme["header_bg"])

        for label in self.primary_labels:
            label.configure(bg=theme["surface_bg"], fg=theme["text_primary"])

        for label in self.secondary_labels:
            label.configure(bg=theme["surface_bg"], fg=theme["text_secondary"])

        for label in self.form_labels:
            label.configure(bg=theme["surface_bg"], fg=theme["text_primary"])

        for label in self.header_labels:
            label.configure(bg=theme["header_bg"], fg=theme["header_fg"])

        if hasattr(self, "subtitle_label"):
            self.subtitle_label.configure(bg=theme["header_bg"], fg=theme["header_sub_fg"])

        if hasattr(self, "header_title_label"):
            self.header_title_label.configure(bg=theme["header_bg"], fg=theme["header_fg"])

        for entry in self.entry_widgets:
            entry.configure(
                bg=theme["entry_bg"],
                fg=theme["entry_fg"],
                insertbackground=theme["entry_insert"],
                highlightbackground=theme["border"],
                highlightcolor=theme["border"],
            )

        for text_widget in self.text_widgets:
            text_widget.configure(
                bg=theme["entry_bg"],
                fg=theme["entry_fg"],
                insertbackground=theme["entry_insert"],
                highlightbackground=theme["border"],
                highlightcolor=theme["border"],
            )

        for checkbutton in self.checkbuttons:
            checkbutton.configure(
                bg=theme["surface_bg"],
                fg=theme["text_primary"],
                selectcolor=theme["surface_bg"],
                activebackground=theme["surface_bg"],
                activeforeground=theme["text_primary"],
            )

        for button, role in self.button_roles.items():
            bg, fg, active_bg = self.get_button_colors(role)
            button.configure(
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                highlightbackground=theme["border"],
            )

        self.style.configure(
            "Treeview",
            rowheight=30,
            font=("Segoe UI", 10),
            background=theme["tree_bg"],
            fieldbackground=theme["tree_bg"],
            foreground=theme["tree_fg"],
            bordercolor=theme["border"],
        )
        self.style.map(
            "Treeview",
            background=[("selected", theme["tree_selected_bg"])],
            foreground=[("selected", theme["tree_selected_fg"])],
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Microsoft YaHei UI", 10, "bold"),
            background=theme["tree_heading_bg"],
            foreground=theme["tree_heading_fg"],
            bordercolor=theme["border"],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=theme["entry_bg"],
            background=theme["entry_bg"],
            foreground=theme["entry_fg"],
            arrowcolor=theme["entry_fg"],
            bordercolor=theme["border"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", theme["entry_bg"])],
            foreground=[("readonly", theme["entry_fg"])],
            selectbackground=[("readonly", theme["entry_bg"])],
            selectforeground=[("readonly", theme["entry_fg"])],
        )

    def watch_windows_theme(self) -> None:
        next_theme = get_windows_theme_mode()
        if next_theme != self.theme_mode:
            self.theme_mode = next_theme
            self.apply_theme()
        self.root.after(THEME_POLL_INTERVAL_MS, self.watch_windows_theme)

    def build_layout(self) -> None:
        header = self.register_frame(tk.Frame(self.root, padx=24, pady=18), "header")
        header.pack(fill="x")

        title = self.register_label(
            tk.Label(
                header,
                text=self.t("app_title"),
                font=("Microsoft YaHei UI", 24, "bold"),
            ),
            "header",
        )
        title.pack(anchor="w")
        self.header_title_label = title

        subtitle = self.register_label(
            tk.Label(
                header,
                text=self.t("app_subtitle"),
                font=("Microsoft YaHei UI", 11),
            ),
            "header",
        )
        subtitle.pack(anchor="w", pady=(6, 0))
        self.subtitle_label = subtitle

        main_area = self.register_frame(tk.Frame(self.root, padx=18, pady=18), "main")
        main_area.pack(fill="both", expand=True)
        # Give the account list more horizontal space than the detail form.
        main_area.grid_columnconfigure(0, weight=7, minsize=620)
        main_area.grid_columnconfigure(1, weight=5, minsize=460)
        main_area.grid_rowconfigure(0, weight=1)

        left_panel = self.register_frame(tk.Frame(main_area, bd=1, relief="solid"), "surface")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.build_list_panel(left_panel)

        right_panel = self.register_frame(tk.Frame(main_area, bd=1, relief="solid"), "surface")
        right_panel.grid(row=0, column=1, sticky="nsew")
        self.build_scrollable_detail_panel(right_panel)

    def build_list_panel(self, parent: tk.Frame) -> None:
        toolbar = self.register_frame(tk.Frame(parent, padx=16, pady=14), "surface")
        toolbar.pack(fill="x")
        toolbar.grid_columnconfigure(1, weight=1)

        self.register_label(
            tk.Label(
                toolbar,
                text=self.t("list_title"),
                font=("Microsoft YaHei UI", 16, "bold"),
            ),
            "primary",
        ).grid(row=0, column=0, sticky="w")

        self.summary_label = self.register_label(
            tk.Label(
                toolbar,
                textvariable=self.summary_var,
                font=("Microsoft YaHei UI", 10),
            ),
            "secondary",
        )
        self.summary_label.grid(row=0, column=1, sticky="e")

        search_row = self.register_frame(tk.Frame(parent, padx=16, pady=6), "surface")
        search_row.pack(fill="x")
        search_row.grid_columnconfigure(1, weight=1)

        self.register_label(
            tk.Label(
                search_row,
                text=self.t("search_label"),
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        search_entry = self.register_entry(
            tk.Entry(
                search_row,
                textvariable=self.search_var,
                font=("Segoe UI", 10),
                relief="solid",
                bd=1,
            )
        )
        search_entry.grid(row=0, column=1, sticky="ew")
        search_entry.bind("<KeyRelease>", lambda event: self.refresh_table())

        self.register_label(
            tk.Label(
                search_row,
                text=self.t("status_filter_label"),
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).grid(row=0, column=2, sticky="w", padx=(12, 8))

        status_filter = self.register_combobox(
            ttk.Combobox(
                search_row,
                textvariable=self.status_filter_var,
                values=[self.t("status_all"), *self.status_options],
                state="readonly",
                width=10,
            )
        )
        status_filter.grid(row=0, column=3, sticky="e")
        status_filter.bind("<<ComboboxSelected>>", lambda event: self.refresh_table())

        table_frame = self.register_frame(tk.Frame(parent, padx=16, pady=10), "surface")
        table_frame.pack(fill="both", expand=True)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_rowconfigure(1, weight=0)

        columns = ("profile_name", "login_name", "status", "last_login")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("profile_name", text=self.t("column_profile_name"))
        self.tree.heading("login_name", text=self.t("column_login_name"))
        self.tree.heading("status", text=self.t("column_status"))
        self.tree.heading("last_login", text=self.t("column_last_login"))

        self.tree.column("profile_name", width=180, anchor="w")
        self.tree.column("login_name", width=170, anchor="w")
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("last_login", width=150, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.on_tree_select)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.tree.configure(
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )

        action_row = self.register_frame(tk.Frame(parent, padx=16, pady=14), "surface")
        action_row.pack(fill="x")

        self.new_button = self.register_button(
            tk.Button(
                action_row,
                text=self.t("button_new"),
                command=self.prepare_new_account,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=14,
                pady=8,
            ),
            "primary",
        )
        self.new_button.pack(side="left")

        self.delete_button = self.register_button(
            tk.Button(
                action_row,
                text=self.t("button_delete"),
                command=self.delete_current_account,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=14,
                pady=8,
            ),
            "danger",
        )
        self.delete_button.pack(side="left", padx=10)

        self.refresh_button = self.register_button(
            tk.Button(
                action_row,
                text=self.t("button_refresh"),
                command=self.refresh_table,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=14,
                pady=8,
            ),
            "neutral",
        )
        self.refresh_button.pack(side="left")

        self.import_button = self.register_button(
            tk.Button(
                action_row,
                text=self.t("button_import"),
                command=self.open_text_import_dialog,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=14,
                pady=8,
            ),
            "accent",
        )
        self.import_button.pack(side="left", padx=10)

        self.quick_line_button = self.register_button(
            tk.Button(
                action_row,
                text=self.t("button_quick_line_import"),
                command=self.open_quick_line_import_dialog,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=14,
                pady=8,
            ),
            "info",
        )
        self.quick_line_button.pack(side="left")

        batch_row = self.register_frame(tk.Frame(parent, padx=16, pady=0), "surface")
        batch_row.pack(fill="x", pady=(0, 14))

        self.register_label(
            tk.Label(
                batch_row,
                text=self.t("batch_status_label"),
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).pack(side="left", padx=(0, 8))

        batch_status_box = self.register_combobox(
            ttk.Combobox(
                batch_row,
                textvariable=self.batch_status_var,
                values=self.status_options,
                state="readonly",
                width=12,
            )
        )
        batch_status_box.pack(side="left")

        self.batch_status_button = self.register_button(
            tk.Button(
                batch_row,
                text=self.t("button_apply_batch_status"),
                command=self.apply_batch_status,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=12,
                pady=7,
            ),
            "success",
        )
        self.batch_status_button.pack(side="left", padx=10)

    def build_scrollable_detail_panel(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            parent,
            highlightthickness=0,
            bd=0,
            bg=self.theme["surface_bg"],
        )
        self.canvases.append(canvas)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_content = self.register_frame(tk.Frame(canvas), "surface")
        content_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        def update_scroll_region(event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(content_window, width=event.width)

        def on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        scroll_content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_content_width)
        canvas.bind("<MouseWheel>", on_mousewheel)
        scroll_content.bind("<MouseWheel>", on_mousewheel)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.detail_canvas = canvas

        self.build_detail_panel(scroll_content)

    def build_detail_panel(self, parent: tk.Frame) -> None:
        header = self.register_frame(tk.Frame(parent, padx=18, pady=16), "surface")
        header.pack(fill="x")

        self.register_label(
            tk.Label(
                header,
                text=self.t("detail_title"),
                font=("Microsoft YaHei UI", 16, "bold"),
            ),
            "primary",
        ).pack(anchor="w")

        self.selection_label = self.register_label(
            tk.Label(
                header,
                textvariable=self.selection_var,
                font=("Microsoft YaHei UI", 10),
            ),
            "secondary",
        )
        self.selection_label.pack(anchor="w", pady=(6, 0))

        form = self.register_frame(tk.Frame(parent, padx=18, pady=8), "surface")
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(1, weight=1)

        self.add_form_entry(form, 0, self.t("field_profile_name"), "profile_name")
        self.add_form_entry(form, 1, self.t("field_login_name"), "login_name")
        self.add_password_entry(form, 2)
        self.add_form_entry(form, 3, self.t("field_email"), "email")
        self.add_form_entry(form, 4, self.t("field_phone"), "phone")
        self.add_status_field(form, 5)
        self.add_form_entry(form, 6, self.t("field_last_login"), "last_login")

        self.register_label(
            tk.Label(
                form,
                text=self.t("field_note"),
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).grid(row=7, column=0, sticky="nw", pady=(10, 0), padx=(0, 12))

        self.note_text = self.register_text_widget(
            tk.Text(
                form,
                height=6,
                font=("Segoe UI", 10),
                relief="solid",
                bd=1,
                wrap="word",
            )
        )
        self.note_text.grid(row=7, column=1, sticky="nsew", pady=(10, 0))
        form.grid_rowconfigure(7, weight=1)

        footer = self.register_frame(tk.Frame(parent, padx=18, pady=12), "surface")
        footer.pack(fill="x")

        button_row = self.register_frame(tk.Frame(footer), "surface")
        button_row.pack(fill="x")

        self.save_button = self.register_button(
            tk.Button(
                button_row,
                text=self.t("button_save"),
                command=self.save_account,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=12,
                pady=9,
            ),
            "success",
        )
        self.save_button.pack(side="left")

        self.login_button = self.register_button(
            tk.Button(
                button_row,
                text=self.t("button_login"),
                command=self.open_steam_login_dialog,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=12,
                pady=9,
            ),
            "warning",
        )
        self.login_button.pack(side="left", padx=10)

        self.clear_button = self.register_button(
            tk.Button(
                button_row,
                text=self.t("button_clear"),
                command=self.clear_form,
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="flat",
                padx=12,
                pady=9,
            ),
            "neutral",
        )
        self.clear_button.pack(side="left", padx=10)

        hint = self.register_label(
            tk.Label(
                footer,
                text=self.t("detail_action_hint"),
                font=("Microsoft YaHei UI", 9),
                justify="left",
                anchor="w",
                wraplength=420,
            ),
            "secondary",
        )
        hint.pack(fill="x", pady=(10, 0))

    def open_steam_login_dialog(self) -> None:
        theme = self.theme
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("steam_login_dialog_title"))
        dialog.geometry("620x360")
        dialog.minsize(560, 330)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=theme["app_bg"])

        container = tk.Frame(dialog, bg=theme["app_bg"], padx=18, pady=18)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=self.t("steam_login_dialog_heading"),
            bg=theme["app_bg"],
            fg=theme["text_primary"],
            font=("Microsoft YaHei UI", 15, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            container,
            textvariable=self.selection_var,
            bg=theme["app_bg"],
            fg=theme["text_secondary"],
            font=("Microsoft YaHei UI", 10),
            anchor="w",
        ).pack(fill="x", pady=(6, 12))

        tk.Label(
            container,
            text=self.t("auto_login_hint"),
            bg=theme["app_bg"],
            fg=theme["text_secondary"],
            font=("Microsoft YaHei UI", 10),
            justify="left",
            anchor="w",
            wraplength=560,
        ).pack(fill="x")

        settings_row = tk.Frame(container, bg=theme["app_bg"], pady=14)
        settings_row.pack(fill="x")
        settings_row.grid_columnconfigure(1, weight=1)

        tk.Label(
            settings_row,
            text=self.t("steam_shutdown_strategy_label"),
            bg=theme["app_bg"],
            fg=theme["text_primary"],
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        shutdown_strategy = ttk.Combobox(
            settings_row,
            textvariable=self.steam_shutdown_strategy_var,
            values=[label for _, label in self.get_steam_shutdown_strategy_options()],
            state="readonly",
            width=32,
        )
        shutdown_strategy.grid(row=0, column=1, sticky="w")
        shutdown_strategy.bind("<<ComboboxSelected>>", self.on_steam_shutdown_strategy_change)

        status_label = tk.Label(
            container,
            textvariable=self.login_status_var,
            bg=theme["app_bg"],
            fg=theme["text_secondary"],
            font=("Microsoft YaHei UI", 10),
            justify="left",
            anchor="w",
            wraplength=560,
        )
        status_label.pack(fill="x", pady=(4, 12))

        footer = tk.Frame(container, bg=theme["app_bg"])
        footer.pack(fill="x")

        login_bg, login_fg, login_active = self.get_button_colors("warning")
        self.login_action_button = tk.Button(
            footer,
            text=self.t("button_start_auto_login"),
            command=self.login_selected_account,
            bg=login_bg,
            fg=login_fg,
            activebackground=login_active,
            activeforeground=login_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        )
        self.login_action_button.pack(side="left")

        choose_bg, choose_fg, choose_active = self.get_button_colors("info")
        tk.Button(
            footer,
            text=self.t("button_choose_steam"),
            command=self.choose_steam_executable,
            bg=choose_bg,
            fg=choose_fg,
            activebackground=choose_active,
            activeforeground=choose_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        ).pack(side="left", padx=10)

        def on_close() -> None:
            self.login_action_button = None
            dialog.destroy()

        close_bg, close_fg, close_active = self.get_button_colors("neutral")
        tk.Button(
            footer,
            text=self.t("button_close"),
            command=on_close,
            bg=close_bg,
            fg=close_fg,
            activebackground=close_active,
            activeforeground=close_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def add_form_entry(self, parent: tk.Frame, row: int, label_text: str, field_name: str) -> None:
        self.register_label(
            tk.Label(
                parent,
                text=label_text,
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).grid(row=row, column=0, sticky="w", pady=10, padx=(0, 12))

        self.register_entry(
            tk.Entry(
                parent,
                textvariable=self.form_vars[field_name],
                font=("Segoe UI", 10),
                relief="solid",
                bd=1,
            )
        ).grid(row=row, column=1, sticky="ew", pady=10)

    def add_password_entry(self, parent: tk.Frame, row: int) -> None:
        self.register_label(
            tk.Label(
                parent,
                text=self.t("field_password"),
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).grid(row=row, column=0, sticky="w", pady=10, padx=(0, 12))

        password_row = self.register_frame(tk.Frame(parent), "surface")
        password_row.grid(row=row, column=1, sticky="ew", pady=10)
        password_row.grid_columnconfigure(0, weight=1)

        self.password_entry = self.register_entry(
            tk.Entry(
                password_row,
                textvariable=self.form_vars["password"],
                font=("Segoe UI", 10),
                relief="solid",
                bd=1,
                show="*",
            )
        )
        self.password_entry.grid(row=0, column=0, sticky="ew")

        self.register_checkbutton(
            tk.Checkbutton(
                password_row,
                text=self.t("show_password"),
                variable=self.password_visible,
                command=self.toggle_password_visibility,
                font=("Microsoft YaHei UI", 9),
            )
        ).grid(row=0, column=1, padx=(10, 0))

    def add_status_field(self, parent: tk.Frame, row: int) -> None:
        self.register_label(
            tk.Label(
                parent,
                text=self.t("field_status"),
                font=("Microsoft YaHei UI", 10, "bold"),
            ),
            "form",
        ).grid(row=row, column=0, sticky="w", pady=10, padx=(0, 12))

        status_box = self.register_combobox(
            ttk.Combobox(
                parent,
                textvariable=self.form_vars["status"],
                values=self.status_options,
                state="readonly",
            )
        )
        status_box.grid(row=row, column=1, sticky="ew", pady=10)

    def toggle_password_visibility(self) -> None:
        self.password_entry.configure(show="" if self.password_visible.get() else "*")

    def get_filtered_accounts(self) -> list[SteamAccount]:
        keyword = self.search_var.get().strip().lower()
        status_filter = self.status_filter_var.get().strip()
        filtered_accounts: list[SteamAccount] = []

        for account in self.accounts:
            if status_filter != self.t("status_all") and account.status != self.get_status_key(status_filter):
                continue

            haystack = " ".join(
                [
                    account.profile_name,
                    account.login_name,
                    account.email,
                    account.phone,
                    account.note,
                ]
            ).lower()

            if keyword and keyword not in haystack:
                continue

            filtered_accounts.append(account)

        filtered_accounts.sort(key=lambda item: item.updated_at, reverse=True)
        return filtered_accounts

    def refresh_table(self) -> None:
        current_selection = self.current_account_id
        for item in self.tree.get_children():
            self.tree.delete(item)

        filtered_accounts = self.get_filtered_accounts()
        for account in filtered_accounts:
            self.tree.insert(
                "",
                "end",
                iid=account.account_id,
                values=(
                    account.profile_name,
                    account.login_name,
                    self.get_status_label(account.status),
                    account.last_login or "-",
                ),
            )

        self.summary_var.set(
            self.t("summary_text", total=len(self.accounts), filtered=len(filtered_accounts))
        )

        if current_selection and self.tree.exists(current_selection):
            self.tree.selection_set(current_selection)
            self.tree.focus(current_selection)
        elif self.current_account_id and not self.tree.exists(self.current_account_id):
            self.current_account_id = None
            self.selection_var.set(self.t("default_selection"))

    def get_selected_accounts(self) -> list[SteamAccount]:
        selected_accounts: list[SteamAccount] = []
        for account_id in self.tree.selection():
            account = self.find_account(account_id)
            if account:
                selected_accounts.append(account)
        return selected_accounts

    def on_tree_select(self, event: tk.Event | None = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return

        account_id = selection[0]
        account = self.find_account(account_id)
        if not account:
            return

        self.current_account_id = account.account_id
        self.fill_form(account)

    def find_account(self, account_id: str) -> SteamAccount | None:
        for account in self.accounts:
            if account.account_id == account_id:
                return account
        return None

    def fill_form(self, account: SteamAccount) -> None:
        self.form_vars["profile_name"].set(account.profile_name)
        self.form_vars["login_name"].set(account.login_name)
        self.form_vars["password"].set(account.password)
        self.form_vars["email"].set(account.email)
        self.form_vars["phone"].set(account.phone)
        self.form_vars["status"].set(self.get_status_label(account.status))
        self.form_vars["last_login"].set(account.last_login)
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", account.note)
        self.selection_var.set(
            self.t(
                "selection_current",
                profile_name=account.profile_name,
                login_name=account.login_name,
            )
        )

    def collect_form_data(self) -> dict:
        return {
            "profile_name": self.form_vars["profile_name"].get().strip(),
            "login_name": self.form_vars["login_name"].get().strip(),
            "password": self.form_vars["password"].get(),
            "email": self.form_vars["email"].get().strip(),
            "phone": self.form_vars["phone"].get().strip(),
            "status": self.get_status_key(self.form_vars["status"].get().strip()),
            "last_login": self.form_vars["last_login"].get().strip(),
            "note": self.note_text.get("1.0", "end").strip(),
        }

    def validate_form(self, form_data: dict) -> bool:
        if not form_data["profile_name"]:
            messagebox.showwarning(self.t("prompt_title"), self.t("account_name_required"))
            return False
        if not form_data["login_name"]:
            messagebox.showwarning(self.t("prompt_title"), self.t("login_name_required"))
            return False
        if self.has_duplicate_login_name(form_data["login_name"], self.current_account_id):
            messagebox.showwarning(
                self.t("prompt_title"),
                self.t("login_name_duplicate", login_name=form_data["login_name"]),
            )
            return False
        return True

    def find_account_by_login_name(self, login_name: str) -> SteamAccount | None:
        target = login_name.strip().lower()
        if not target:
            return None

        for account in self.accounts:
            if account.login_name.strip().lower() == target:
                return account
        return None

    def has_duplicate_login_name(self, login_name: str, current_account_id: str | None = None) -> bool:
        target = login_name.strip().lower()
        if not target:
            return False

        for account in self.accounts:
            if account.account_id == current_account_id:
                continue
            if account.login_name.strip().lower() == target:
                return True
        return False

    def parse_import_accounts(self, raw_text: str) -> tuple[list[dict], int]:
        parsed_accounts: list[dict] = []
        skipped_count = 0

        for block in split_import_blocks(raw_text):
            account_data = parse_account_block(block, language_code=self.language)
            if not account_data["login_name"] or not account_data["password"]:
                skipped_count += 1
                continue
            parsed_accounts.append(account_data)

        return parsed_accounts, skipped_count

    def find_duplicate_import_login_names(self, parsed_accounts: list[dict]) -> list[str]:
        login_name_counts: dict[str, tuple[str, int]] = {}

        for account_data in parsed_accounts:
            login_name = account_data["login_name"].strip()
            normalized_login_name = login_name.lower()
            if not normalized_login_name:
                continue

            display_name, count = login_name_counts.get(normalized_login_name, (login_name, 0))
            login_name_counts[normalized_login_name] = (display_name, count + 1)

        duplicates = [
            display_name
            for display_name, count in login_name_counts.values()
            if count > 1
        ]
        duplicates.sort(key=str.lower)
        return duplicates

    def preview_import_accounts(
        self,
        parsed_accounts: list[dict],
        skipped_count: int,
    ) -> tuple[int, int, int, list[str]]:
        created_count = 0
        updated_count = 0
        duplicate_login_names = self.find_duplicate_import_login_names(parsed_accounts)

        for account_data in parsed_accounts:
            existing_account = self.find_account_by_login_name(account_data["login_name"])
            if existing_account:
                updated_count += 1
            else:
                created_count += 1

        return created_count, updated_count, skipped_count, duplicate_login_names

    def import_accounts(self, parsed_accounts: list[dict], skipped_count: int) -> tuple[int, int, int] | None:
        created_count = 0
        updated_count = 0
        original_accounts = self.clone_accounts()
        latest_accounts_by_login_name: dict[str, dict] = {}

        for account_data in parsed_accounts:
            latest_accounts_by_login_name[account_data["login_name"].strip().lower()] = account_data

        for account_data in latest_accounts_by_login_name.values():
            existing_account = self.find_account_by_login_name(account_data["login_name"])
            if existing_account:
                existing_account.profile_name = account_data["profile_name"] or existing_account.profile_name
                existing_account.login_name = account_data["login_name"] or existing_account.login_name
                existing_account.password = account_data["password"] or existing_account.password
                existing_account.email = account_data["email"] or existing_account.email
                existing_account.phone = account_data["phone"] or existing_account.phone
                existing_account.status = account_data["status"] or existing_account.status
                if account_data["last_login"]:
                    existing_account.last_login = account_data["last_login"]
                if account_data["note"]:
                    existing_account.note = account_data["note"]
                existing_account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated_count += 1
            else:
                self.accounts.append(SteamAccount.create(**account_data))
                created_count += 1

        if created_count or updated_count:
            if not self.save_accounts_with_feedback():
                self.accounts = original_accounts
                self.refresh_table()
                return None
            self.refresh_table()

        return created_count, updated_count, skipped_count

    def apply_batch_status(self) -> None:
        selected_accounts = self.get_selected_accounts()
        if not selected_accounts:
            messagebox.showwarning(self.t("prompt_title"), self.t("batch_no_selection_warning"))
            return

        status_key = self.get_status_key(self.batch_status_var.get())
        status_label = self.get_status_label(status_key)
        confirmed = messagebox.askyesno(
            self.t("batch_status_confirm_title"),
            self.t(
                "batch_status_confirm_message",
                count=len(selected_accounts),
                status=status_label,
            ),
        )
        if not confirmed:
            return

        original_accounts = self.clone_accounts()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        selected_ids = {account.account_id for account in selected_accounts}
        for account in self.accounts:
            if account.account_id in selected_ids:
                account.status = status_key
                account.updated_at = now

        if not self.save_accounts_with_feedback():
            self.accounts = original_accounts
            self.refresh_table()
            return

        self.refresh_table()
        for account_id in selected_ids:
            if self.tree.exists(account_id):
                self.tree.selection_add(account_id)
        messagebox.showinfo(
            self.t("success_title"),
            self.t("batch_status_success", count=len(selected_ids), status=status_label),
        )

    def select_account_by_login_name(self, login_name: str) -> None:
        account = self.find_account_by_login_name(login_name)
        if not account:
            return

        self.current_account_id = account.account_id
        self.refresh_table()
        if self.tree.exists(account.account_id):
            self.tree.selection_set(account.account_id)
            self.tree.focus(account.account_id)
        self.fill_form(account)

    def open_quick_line_import_dialog(self) -> None:
        theme = self.theme
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("quick_line_dialog_title"))
        dialog.geometry("760x420")
        dialog.minsize(680, 360)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=theme["app_bg"])

        container = tk.Frame(dialog, bg=theme["app_bg"], padx=18, pady=18)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=self.t("quick_line_dialog_heading"),
            bg=theme["app_bg"],
            fg=theme["text_primary"],
            font=("Microsoft YaHei UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            container,
            text=self.t("quick_line_dialog_description"),
            bg=theme["app_bg"],
            fg=theme["text_secondary"],
            font=("Microsoft YaHei UI", 10),
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(6, 12))

        text_box = tk.Text(
            container,
            font=("Consolas", 11),
            height=8,
            wrap="word",
            relief="solid",
            bd=1,
            bg=theme["entry_bg"],
            fg=theme["entry_fg"],
            insertbackground=theme["entry_insert"],
        )
        text_box.pack(fill="both", expand=True)
        text_box.focus_set()

        footer = tk.Frame(container, bg=theme["app_bg"], pady=14)
        footer.pack(fill="x")

        def handle_save() -> None:
            raw_text = text_box.get("1.0", "end").strip()
            if not raw_text:
                messagebox.showwarning(self.t("prompt_title"), self.t("quick_line_empty_warning"))
                return

            parsed_accounts, skipped_count = self.parse_import_accounts(raw_text)
            if not parsed_accounts:
                messagebox.showwarning(self.t("prompt_title"), self.t("import_no_match_warning"))
                return

            created_count, updated_count, skipped_count, duplicate_login_names = self.preview_import_accounts(
                parsed_accounts,
                skipped_count,
            )
            preview_lines = [
                self.t(
                    "import_preview_summary",
                    created=created_count,
                    updated=updated_count,
                    skipped=skipped_count,
                )
            ]
            if updated_count:
                preview_lines.append(self.t("import_preview_update_hint"))
            if duplicate_login_names:
                preview_lines.append(
                    self.t(
                        "import_preview_duplicate_hint",
                        login_names=", ".join(duplicate_login_names),
                    )
                )
            preview_lines.append(self.t("import_confirm_question"))

            confirmed = messagebox.askyesno(
                self.t("import_preview_title"),
                "\n\n".join(preview_lines),
            )
            if not confirmed:
                return

            result = self.import_accounts(parsed_accounts, skipped_count)
            if result is None:
                return

            created_count, updated_count, skipped_count = result
            if len(parsed_accounts) == 1:
                self.select_account_by_login_name(parsed_accounts[0]["login_name"])
            messagebox.showinfo(
                self.t("import_result_title"),
                self.t(
                    "import_result_summary",
                    created=created_count,
                    updated=updated_count,
                    skipped=skipped_count,
                ),
            )
            dialog.destroy()

        save_bg, save_fg, save_active = self.get_button_colors("success")
        tk.Button(
            footer,
            text=self.t("button_quick_line_save"),
            command=handle_save,
            bg=save_bg,
            fg=save_fg,
            activebackground=save_active,
            activeforeground=save_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        ).pack(side="left")

        close_bg, close_fg, close_active = self.get_button_colors("neutral")
        tk.Button(
            footer,
            text=self.t("button_close"),
            command=dialog.destroy,
            bg=close_bg,
            fg=close_fg,
            activebackground=close_active,
            activeforeground=close_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        ).pack(side="left", padx=10)

    def open_text_import_dialog(self) -> None:
        theme = self.theme
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("import_dialog_title"))
        dialog.geometry("760x520")
        dialog.minsize(700, 480)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=theme["app_bg"])

        container = tk.Frame(dialog, bg=theme["app_bg"], padx=18, pady=18)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=self.t("import_dialog_heading"),
            bg=theme["app_bg"],
            fg=theme["text_primary"],
            font=("Microsoft YaHei UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            container,
            text=self.t("import_dialog_description"),
            bg=theme["app_bg"],
            fg=theme["text_secondary"],
            font=("Microsoft YaHei UI", 10),
            anchor="w",
        ).pack(fill="x", pady=(6, 12))

        text_box = tk.Text(
            container,
            font=("Consolas", 11),
            wrap="word",
            relief="solid",
            bd=1,
            bg=theme["entry_bg"],
            fg=theme["entry_fg"],
            insertbackground=theme["entry_insert"],
        )
        text_box.pack(fill="both", expand=True)

        footer = tk.Frame(container, bg=theme["app_bg"], pady=14)
        footer.pack(fill="x")

        def handle_import() -> None:
            raw_text = text_box.get("1.0", "end").strip()
            if not raw_text:
                messagebox.showwarning(self.t("prompt_title"), self.t("import_empty_warning"))
                return

            parsed_accounts, skipped_count = self.parse_import_accounts(raw_text)
            created_count, updated_count, skipped_count, duplicate_login_names = self.preview_import_accounts(
                parsed_accounts,
                skipped_count,
            )
            if not (created_count or updated_count or skipped_count):
                messagebox.showwarning(self.t("prompt_title"), self.t("import_no_match_warning"))
                return

            preview_lines = [
                self.t(
                    "import_preview_summary",
                    created=created_count,
                    updated=updated_count,
                    skipped=skipped_count,
                )
            ]
            if updated_count:
                preview_lines.append(self.t("import_preview_update_hint"))
            if duplicate_login_names:
                preview_lines.append(
                    self.t(
                        "import_preview_duplicate_hint",
                        login_names=", ".join(duplicate_login_names),
                    )
                )
            preview_lines.append(self.t("import_confirm_question"))

            confirmed = messagebox.askyesno(
                self.t("import_preview_title"),
                "\n\n".join(preview_lines),
            )
            if not confirmed:
                return

            result = self.import_accounts(parsed_accounts, skipped_count)
            if result is None:
                return

            created_count, updated_count, skipped_count = result

            summary = self.t(
                "import_result_summary",
                created=created_count,
                updated=updated_count,
                skipped=skipped_count,
            )
            if skipped_count:
                summary += f"\n{self.t('import_result_partial_hint')}"

            messagebox.showinfo(self.t("import_result_title"), summary)
            if created_count or updated_count:
                dialog.destroy()

        import_bg, import_fg, import_active = self.get_button_colors("success")
        tk.Button(
            footer,
            text=self.t("button_start_import"),
            command=handle_import,
            bg=import_bg,
            fg=import_fg,
            activebackground=import_active,
            activeforeground=import_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        ).pack(side="left")

        close_bg, close_fg, close_active = self.get_button_colors("neutral")
        tk.Button(
            footer,
            text=self.t("button_close"),
            command=dialog.destroy,
            bg=close_bg,
            fg=close_fg,
            activebackground=close_active,
            activeforeground=close_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=8,
        ).pack(side="left", padx=10)

    def save_account(self) -> None:
        form_data = self.collect_form_data()
        if not self.validate_form(form_data):
            return

        original_accounts = self.clone_accounts()
        original_account_id = self.current_account_id

        if self.current_account_id:
            account = self.find_account(self.current_account_id)
            if not account:
                messagebox.showerror(self.t("error_title"), self.t("update_not_found_error"))
                return

            account.profile_name = form_data["profile_name"]
            account.login_name = form_data["login_name"]
            account.password = form_data["password"]
            account.email = form_data["email"]
            account.phone = form_data["phone"]
            account.status = form_data["status"]
            account.last_login = form_data["last_login"]
            account.note = form_data["note"]
            account.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = self.t("account_updated_success")
        else:
            account = SteamAccount.create(**form_data)
            self.accounts.append(account)
            self.current_account_id = account.account_id
            message = self.t("account_created_success")

        if not self.save_accounts_with_feedback():
            self.accounts = original_accounts
            self.current_account_id = original_account_id
            self.refresh_table()
            if self.current_account_id:
                restored_account = self.find_account(self.current_account_id)
                if restored_account:
                    self.fill_form(restored_account)
            else:
                self.clear_form()
            return

        self.refresh_table()

        if self.current_account_id and self.tree.exists(self.current_account_id):
            self.tree.selection_set(self.current_account_id)
            self.tree.focus(self.current_account_id)

        messagebox.showinfo(self.t("success_title"), message)

    def set_login_status(self, message: str) -> None:
        self.root.after(0, lambda: self.login_status_var.set(self.t("login_status_prefix", message=message)))

    def is_valid_steam_executable(self, steam_path: Path) -> bool:
        return (
            steam_path.exists()
            and steam_path.is_file()
            and steam_path.name.lower() == "steam.exe"
        )

    def choose_steam_executable(self) -> Path | None:
        detected_path = detect_steam_executable()
        if detected_path and self.is_valid_steam_executable(detected_path):
            updated_settings = dict(self.settings)
            updated_settings["steam_path"] = str(detected_path)
            if not self.save_settings_with_feedback(updated_settings):
                return None
            self.set_login_status(self.t("steam_path_set_status", path=detected_path))
            messagebox.showinfo(
                self.t("success_title"),
                self.t("steam_path_set_status", path=detected_path),
            )
            return detected_path

        initial_path = Path(self.settings.get("steam_path", "")).parent if self.settings.get("steam_path") else None
        selected_path = filedialog.askopenfilename(
            title=self.t("choose_steam_exe_title"),
            initialdir=str(initial_path) if initial_path else r"C:\Program Files (x86)\Steam",
            filetypes=[
                (self.t("filetype_steam_client"), "steam.exe"),
            ],
        )
        if not selected_path:
            return None

        steam_path = Path(selected_path)
        if not self.is_valid_steam_executable(steam_path):
            messagebox.showwarning(
                self.t("invalid_steam_path_title"),
                self.t("invalid_steam_path_warning", path=steam_path),
            )
            return None

        updated_settings = dict(self.settings)
        updated_settings["steam_path"] = str(steam_path)
        if not self.save_settings_with_feedback(updated_settings):
            return None
        self.set_login_status(self.t("steam_path_set_status", path=steam_path))
        return steam_path

    def resolve_steam_executable(self) -> Path | None:
        stored_path = self.settings.get("steam_path", "")
        if stored_path:
            candidate = Path(stored_path)
            if self.is_valid_steam_executable(candidate):
                return candidate
            if candidate.exists() and candidate.is_file():
                messagebox.showwarning(
                    self.t("invalid_steam_path_title"),
                    self.t("invalid_saved_steam_path_warning", path=candidate),
                )

        detected_path = detect_steam_executable()
        if detected_path and self.is_valid_steam_executable(detected_path):
            updated_settings = dict(self.settings)
            updated_settings["steam_path"] = str(detected_path)
            if not self.save_settings_with_feedback(updated_settings):
                return None
            return detected_path

        messagebox.showinfo(self.t("prompt_title"), self.t("steam_not_detected_info"))
        return self.choose_steam_executable()

    def login_selected_account(self) -> None:
        if self.login_in_progress:
            messagebox.showwarning(self.t("prompt_title"), self.t("login_in_progress_warning"))
            return

        if not self.current_account_id:
            messagebox.showwarning(self.t("prompt_title"), self.t("select_account_warning"))
            return

        form_data = self.collect_form_data()
        login_name = form_data["login_name"]
        password = form_data["password"]
        profile_name = form_data["profile_name"] or login_name

        if not login_name:
            messagebox.showwarning(self.t("prompt_title"), self.t("missing_login_warning"))
            return
        if not password:
            messagebox.showwarning(self.t("prompt_title"), self.t("missing_password_warning"))
            return

        steam_path = self.resolve_steam_executable()
        if not steam_path:
            self.set_login_status(self.t("steam_path_missing_status"))
            return

        self.login_in_progress = True
        self.login_button.configure(state="disabled")
        if self.login_action_button:
            self.login_action_button.configure(state="disabled")
        self.set_login_status(self.t("launching_login_status", profile_name=profile_name))

        threading.Thread(
            target=self.perform_steam_login,
            args=(steam_path, login_name, password, profile_name),
            daemon=True,
        ).start()

    def perform_steam_login(
        self,
        steam_path: Path,
        login_name: str,
        password: str,
        profile_name: str,
    ) -> None:
        try:
            if is_process_running("steam.exe") or is_process_running("steamwebhelper.exe"):
                shutdown_strategy = self.get_steam_shutdown_strategy_key(
                    self.settings.get("steam_shutdown_strategy")
                )
                if shutdown_strategy == "force":
                    self.set_login_status(self.t("steam_force_closing_running_status"))
                    if not terminate_steam_processes():
                        raise RuntimeError(self.t("steam_running_close_required_error"))
                else:
                    self.set_login_status(self.t("steam_graceful_closing_running_status"))
                    request_steam_shutdown(steam_path)
                    if not wait_for_steam_processes_exit(timeout_seconds=12.0):
                        self.set_login_status(self.t("steam_graceful_close_timeout_status"))
                        if not self.confirm_force_close_after_graceful_timeout():
                            raise RuntimeError(self.t("steam_force_close_cancelled_error"))
                        self.set_login_status(self.t("steam_force_closing_running_status"))
                        if not terminate_steam_processes():
                            raise RuntimeError(self.t("steam_running_close_required_error"))
                    else:
                        self.set_login_status(self.t("steam_graceful_close_success_status"))

                if is_process_running("steam.exe") or is_process_running("steamwebhelper.exe"):
                    raise RuntimeError(self.t("steam_running_close_required_error"))

            subprocess.Popen(
                [str(steam_path), "-login", login_name, password],
                cwd=str(steam_path.parent),
            )
            self.set_login_status(self.t("steam_started_status"))
            time.sleep(1.0)

            self.finish_steam_login(
                success=True,
                message=self.t("login_success_status", profile_name=profile_name),
            )
        except Exception as error:
            self.finish_steam_login(success=False, message=str(error))

    def confirm_force_close_after_graceful_timeout(self) -> bool:
        response_queue: queue.Queue[bool] = queue.Queue(maxsize=1)

        def ask_user() -> None:
            confirmed = messagebox.askyesno(
                self.t("steam_force_close_confirm_title"),
                self.t("steam_force_close_confirm_message"),
            )
            response_queue.put(confirmed)

        self.root.after(0, ask_user)
        return response_queue.get()

    def finish_steam_login(self, success: bool, message: str) -> None:
        def update_ui() -> None:
            self.login_in_progress = False
            self.login_button.configure(state="normal")
            if self.login_action_button:
                self.login_action_button.configure(state="normal")
            self.login_status_var.set(self.t("login_status_prefix", message=message))
            if not success:
                messagebox.showerror(self.t("steam_login_failed_title"), message)
            elif not self.settings.get("hide_login_attempt_notice", False):
                self.show_login_attempt_notice()

        self.root.after(0, update_ui)

    def show_login_attempt_notice(self) -> None:
        theme = self.theme
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("login_attempt_notice_title"))
        dialog.geometry("520x240")
        dialog.minsize(480, 220)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=theme["app_bg"])

        container = tk.Frame(dialog, bg=theme["app_bg"], padx=18, pady=18)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text=self.t("login_attempt_notice_heading"),
            bg=theme["app_bg"],
            fg=theme["text_primary"],
            font=("Microsoft YaHei UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            container,
            text=self.t("login_attempt_notice_message"),
            bg=theme["app_bg"],
            fg=theme["text_secondary"],
            font=("Microsoft YaHei UI", 10),
            justify="left",
            anchor="w",
            wraplength=470,
        ).pack(fill="x", pady=(12, 14))

        dont_show_again = tk.BooleanVar(value=False)
        tk.Checkbutton(
            container,
            text=self.t("login_attempt_notice_dont_show_again"),
            variable=dont_show_again,
            bg=theme["app_bg"],
            fg=theme["text_primary"],
            selectcolor=theme["entry_bg"],
            activebackground=theme["app_bg"],
            activeforeground=theme["text_primary"],
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w")

        footer = tk.Frame(container, bg=theme["app_bg"], pady=14)
        footer.pack(fill="x")

        def close_dialog() -> None:
            if dont_show_again.get():
                updated_settings = dict(self.settings)
                updated_settings["hide_login_attempt_notice"] = True
                self.save_settings_with_feedback(updated_settings)
            dialog.destroy()

        ok_bg, ok_fg, ok_active = self.get_button_colors("primary")
        tk.Button(
            footer,
            text=self.t("button_ok"),
            command=close_dialog,
            bg=ok_bg,
            fg=ok_fg,
            activebackground=ok_active,
            activeforeground=ok_fg,
            font=("Microsoft YaHei UI", 10, "bold"),
            relief="flat",
            padx=18,
            pady=8,
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def prepare_new_account(self) -> None:
        self.clear_form()
        self.selection_var.set(self.t("new_mode_selection"))

    def clear_form(self) -> None:
        for key, variable in self.form_vars.items():
            if key == "status":
                variable.set(self.status_options[0])
            else:
                variable.set("")
        self.note_text.delete("1.0", "end")
        self.current_account_id = None
        self.tree.selection_remove(self.tree.selection())
        self.selection_var.set(self.t("default_selection"))
        self.password_visible.set(False)
        self.toggle_password_visibility()

    def delete_current_account(self) -> None:
        selected_accounts = self.get_selected_accounts()
        if not selected_accounts and self.current_account_id:
            account = self.find_account(self.current_account_id)
            if account:
                selected_accounts = [account]

        if not selected_accounts:
            messagebox.showwarning(self.t("prompt_title"), self.t("select_account_warning"))
            return

        if len(selected_accounts) == 1:
            confirmed = messagebox.askyesno(
                self.t("delete_confirm_title"),
                self.t("delete_confirm_message", profile_name=selected_accounts[0].profile_name),
            )
        else:
            confirmed = messagebox.askyesno(
                self.t("delete_confirm_title"),
                self.t("batch_delete_confirm_message", count=len(selected_accounts)),
            )
        if not confirmed:
            return

        original_accounts = self.clone_accounts()
        selected_ids = {account.account_id for account in selected_accounts}
        self.accounts = [
            item for item in self.accounts if item.account_id not in selected_ids
        ]
        if not self.save_accounts_with_feedback():
            self.accounts = original_accounts
            return
        self.clear_form()
        self.refresh_table()
        if len(selected_ids) == 1:
            messagebox.showinfo(self.t("success_title"), self.t("account_deleted_success"))
        else:
            messagebox.showinfo(
                self.t("success_title"),
                self.t("batch_deleted_success", count=len(selected_ids)),
            )


def main() -> None:
    enable_high_dpi_awareness()
    root = tk.Tk()
    dpi_scale = configure_tk_scaling(root)
    SteamAccountManagerApp(root, dpi_scale=dpi_scale)
    root.mainloop()
