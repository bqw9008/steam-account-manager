from __future__ import annotations

import ctypes
import locale
import os
import subprocess
import time
import tkinter as tk
import winreg
from ctypes import wintypes
from pathlib import Path

try:
    from .config import (
        BASE_MIN_HEIGHT,
        BASE_MIN_WIDTH,
        BASE_WINDOW_HEIGHT,
        BASE_WINDOW_WIDTH,
        CF_UNICODETEXT,
        GMEM_MOVEABLE,
        KEYEVENTF_KEYUP,
        SW_RESTORE,
        VK_CONTROL,
    )
except ImportError:
    from config import (
        BASE_MIN_HEIGHT,
        BASE_MIN_WIDTH,
        BASE_WINDOW_HEIGHT,
        BASE_WINDOW_WIDTH,
        CF_UNICODETEXT,
        GMEM_MOVEABLE,
        KEYEVENTF_KEYUP,
        SW_RESTORE,
        VK_CONTROL,
    )

GWL_STYLE = -16
WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
ES_PASSWORD = 0x0020
STEAM_PROCESS_NAMES = ("steam.exe", "steamwebhelper.exe")


def enable_high_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def configure_tk_scaling(root: tk.Tk) -> float:
    try:
        pixels_per_inch = float(root.winfo_fpixels("1i"))
    except Exception:
        pixels_per_inch = 96.0

    dpi_scale = max(1.0, min(pixels_per_inch / 96.0, 2.5))
    tk_scaling = max(1.0, pixels_per_inch / 72.0)

    try:
        root.tk.call("tk", "scaling", tk_scaling)
    except Exception:
        pass

    return dpi_scale


def apply_window_size(root: tk.Tk, dpi_scale: float) -> None:
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    window_width = min(int(BASE_WINDOW_WIDTH * dpi_scale), screen_width - 120)
    window_height = min(int(BASE_WINDOW_HEIGHT * dpi_scale), screen_height - 120)
    min_width = min(int(BASE_MIN_WIDTH * dpi_scale), window_width)
    min_height = min(int(BASE_MIN_HEIGHT * dpi_scale), window_height)

    root.minsize(min_width, min_height)

    position_x = max((screen_width - window_width) // 2, 40)
    position_y = max((screen_height - window_height) // 2, 40)
    root.geometry(f"{window_width}x{window_height}+{position_x}+{position_y}")


def read_registry_value(root_key, sub_key: str, value_name: str) -> str:
    try:
        with winreg.OpenKey(root_key, sub_key) as handle:
            value, _ = winreg.QueryValueEx(handle, value_name)
            return str(value).strip()
    except OSError:
        return ""


def get_windows_theme_mode() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as handle:
            value, _ = winreg.QueryValueEx(handle, "AppsUseLightTheme")
            return "light" if int(value) else "dark"
    except OSError:
        return "light"


def detect_system_language() -> str:
    try:
        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return locale.windows_locale.get(language_id, "")
    except Exception:
        return ""


def detect_steam_executable() -> Path | None:
    registry_candidates = [
        read_registry_value(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamExe"),
        read_registry_value(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        read_registry_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        read_registry_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]

    path_candidates: list[Path] = []
    for raw_path in registry_candidates:
        if not raw_path:
            continue

        candidate = Path(raw_path)
        if candidate.is_dir():
            candidate = candidate / "steam.exe"
        path_candidates.append(candidate)

    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        env_text = os.environ.get(env_name, "").strip()
        if env_text:
            path_candidates.append(Path(env_text) / "Steam" / "steam.exe")

    path_candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Steam\steam.exe"),
            Path(r"C:\Program Files\Steam\steam.exe"),
        ]
    )

    for candidate in path_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def is_process_running(process_name: str) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
    except OSError:
        return False

    output = (result.stdout or "").lower()
    return process_name.lower() in output


def terminate_process(process_name: str, force: bool = True) -> bool:
    command = ["taskkill", "/IM", process_name, "/T"]
    if force:
        command.append("/F")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
    except OSError:
        return False

    if result.returncode == 0:
        return True

    stderr = (result.stderr or "").lower()
    stdout = (result.stdout or "").lower()
    not_found_markers = (
        "not found",
        "no tasks are running",
        "没有运行的任务",
        "找不到",
    )
    return any(marker in stderr or marker in stdout for marker in not_found_markers)


def are_steam_processes_running() -> bool:
    return any(is_process_running(name) for name in STEAM_PROCESS_NAMES)


def wait_for_steam_processes_exit(timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not are_steam_processes_running():
            return True
        time.sleep(0.3)
    return not are_steam_processes_running()


def request_steam_shutdown(steam_path: Path) -> bool:
    try:
        subprocess.Popen(
            [str(steam_path), "-shutdown"],
            cwd=str(steam_path.parent),
        )
        return True
    except OSError:
        return False


def terminate_steam_processes(timeout_seconds: float = 8.0) -> bool:
    running_names = [name for name in STEAM_PROCESS_NAMES if is_process_running(name)]
    if not running_names:
        return True

    for process_name in running_names:
        if not terminate_process(process_name):
            return False

    return wait_for_steam_processes_exit(timeout_seconds)


def set_clipboard_text(text: str, messages: dict[str, str] | None = None) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    clipboard_messages = messages or {
        "clipboard_alloc_error": "Unable to allocate clipboard memory.",
        "clipboard_write_error": "Unable to write to the clipboard.",
        "clipboard_open_error": "Unable to open the system clipboard.",
        "clipboard_set_error": "Unable to place text onto the clipboard.",
    }
    text_buffer = ctypes.create_unicode_buffer(text + "\0")
    buffer_size = ctypes.sizeof(text_buffer)
    memory_handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, buffer_size)

    if not memory_handle:
        raise RuntimeError(clipboard_messages["clipboard_alloc_error"])

    locked_memory = kernel32.GlobalLock(memory_handle)
    if not locked_memory:
        kernel32.GlobalFree(memory_handle)
        raise RuntimeError(clipboard_messages["clipboard_write_error"])

    try:
        ctypes.memmove(locked_memory, ctypes.addressof(text_buffer), buffer_size)
    finally:
        kernel32.GlobalUnlock(memory_handle)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(memory_handle)
        raise RuntimeError(clipboard_messages["clipboard_open_error"])

    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, memory_handle):
            kernel32.GlobalFree(memory_handle)
            raise RuntimeError(clipboard_messages["clipboard_set_error"])
    finally:
        user32.CloseClipboard()


def tap_key(virtual_key: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)


def tap_ctrl_shortcut(virtual_key: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def get_window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    title_length = user32.GetWindowTextLengthW(hwnd)
    if title_length <= 0:
        return ""

    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    return title_buffer.value.strip()


def get_class_name(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
    return class_buffer.value.strip()


def get_window_style(hwnd: int) -> int:
    user32 = ctypes.windll.user32
    getter = getattr(user32, "GetWindowLongPtrW", None)
    if getter:
        return int(getter(hwnd, GWL_STYLE))
    return int(user32.GetWindowLongW(hwnd, GWL_STYLE))


def list_child_windows(hwnd: int, limit: int = 200) -> list[dict[str, object]]:
    user32 = ctypes.windll.user32
    children: list[dict[str, object]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(child_hwnd, lparam):
        if len(children) >= limit:
            return False

        child_id = int(child_hwnd)
        children.append(
            {
                "hwnd": child_id,
                "title": get_window_text(child_id),
                "class_name": get_class_name(child_id),
                "visible": bool(user32.IsWindowVisible(child_id)),
                "enabled": bool(user32.IsWindowEnabled(child_id)),
                "style": get_window_style(child_id),
            }
        )
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    return children


def list_visible_windows() -> list[tuple[int, str]]:
    user32 = ctypes.windll.user32
    windows: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        title = get_window_text(int(hwnd))
        if title:
            windows.append((int(hwnd), title))
        return True

    user32.EnumWindows(callback, 0)
    return windows


def find_steam_window() -> tuple[int, str] | None:
    login_keywords = (
        "steam login",
        "steam 登录",
        "登录 steam",
        "sign in to steam",
        "login to steam",
    )
    generic_keywords = ("steam", "蒸汽平台")
    steam_windows: list[tuple[int, str]] = []

    for hwnd, title in list_visible_windows():
        lower_title = title.lower()
        if any(keyword in lower_title for keyword in login_keywords):
            return hwnd, title
        if any(keyword in lower_title for keyword in generic_keywords):
            steam_windows.append((hwnd, title))

    return steam_windows[0] if steam_windows else None


def wait_for_steam_window(timeout_seconds: int = 30) -> tuple[int, str] | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        steam_window = find_steam_window()
        if steam_window:
            return steam_window
        time.sleep(0.5)
    return None


def focus_window(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)


def choose_login_button(buttons: list[dict[str, object]]) -> dict[str, object] | None:
    preferred_keywords = (
        "login",
        "sign in",
        "登录",
        "登入",
        "继续",
        "continue",
    )

    for button in buttons:
        title = str(button["title"]).strip().lower()
        if title and any(keyword in title for keyword in preferred_keywords):
            return button

    return buttons[0] if buttons else None


def try_native_steam_login(hwnd: int, login_name: str, password: str) -> bool:
    user32 = ctypes.windll.user32
    child_windows = list_child_windows(hwnd)
    edit_controls = [
        child
        for child in child_windows
        if child["visible"]
        and child["enabled"]
        and str(child["class_name"]).lower() in {"edit", "richedit50w"}
    ]
    if len(edit_controls) < 2:
        return False

    password_controls = [
        child for child in edit_controls if int(child["style"]) & ES_PASSWORD
    ]
    username_controls = [
        child for child in edit_controls if not int(child["style"]) & ES_PASSWORD
    ]
    username_control = username_controls[0] if username_controls else edit_controls[0]

    if password_controls:
        password_control = password_controls[0]
    else:
        password_control = next(
            (
                child
                for child in edit_controls
                if int(child["hwnd"]) != int(username_control["hwnd"])
            ),
            None,
        )

    if not password_control:
        return False

    buttons = [
        child
        for child in child_windows
        if child["visible"]
        and child["enabled"]
        and str(child["class_name"]).lower() == "button"
    ]
    login_button = choose_login_button(buttons)
    if not login_button:
        return False

    user32.SendMessageW(int(username_control["hwnd"]), WM_SETTEXT, 0, login_name)
    user32.SendMessageW(int(password_control["hwnd"]), WM_SETTEXT, 0, password)
    user32.SendMessageW(int(login_button["hwnd"]), BM_CLICK, 0, 0)
    return True
