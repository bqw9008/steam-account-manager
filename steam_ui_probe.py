from __future__ import annotations

import csv
import ctypes
import io
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

try:
    from .system_utils import detect_steam_executable
except ImportError:
    from system_utils import detect_steam_executable


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
MAX_CHILD_WINDOWS = 40

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def get_class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def get_process_id(hwnd: int) -> int:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def get_process_image_path(process_id: int) -> str:
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ,
        False,
        process_id,
    )
    if not handle:
        return ""

    try:
        buffer_length = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(buffer_length.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(buffer_length)):
            return buffer.value.strip()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_tasklist_processes() -> list[dict[str, str]]:
    try:
        output = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return []

    processes: list[dict[str, str]] = []
    reader = csv.reader(io.StringIO(output))
    for row in reader:
        if len(row) < 5:
            continue
        processes.append(
            {
                "image_name": row[0],
                "pid": row[1],
                "session_name": row[2],
                "session_num": row[3],
                "mem_usage": row[4],
            }
        )
    return processes


def list_visible_windows() -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        title = get_window_text(int(hwnd))
        if not title:
            return True

        process_id = get_process_id(int(hwnd))
        process_path = get_process_image_path(process_id)
        windows.append(
            {
                "hwnd": int(hwnd),
                "title": title,
                "class_name": get_class_name(int(hwnd)),
                "process_id": process_id,
                "process_path": process_path,
            }
        )
        return True

    user32.EnumWindows(callback, 0)
    return windows


def list_child_windows(hwnd: int, limit: int = MAX_CHILD_WINDOWS) -> list[dict[str, object]]:
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
            }
        )
        return True

    user32.EnumChildWindows(hwnd, callback, 0)
    return children


def find_steam_related_windows() -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for window in list_visible_windows():
        title = str(window["title"]).lower()
        process_path = str(window["process_path"]).lower()
        class_name = str(window["class_name"]).lower()
        if "steam" in title or "steam" in process_path or "chrome_widgetwin" in class_name:
            matches.append(window)
    return matches


def guess_window_type(child_windows: list[dict[str, object]]) -> str:
    class_names = [str(child["class_name"]).lower() for child in child_windows]

    native_classes = {"edit", "button", "combobox", "richedit50w"}
    native_hits = sum(1 for class_name in class_names if class_name in native_classes)
    webview_hits = sum(
        1
        for class_name in class_names
        if "chrome_widgetwin" in class_name
        or "cef" in class_name
        or "webview" in class_name
        or "renderwidget" in class_name
    )

    if webview_hits and native_hits == 0:
        return "Likely embedded webview / CEF"
    if native_hits >= 2 and webview_hits == 0:
        return "Likely native Win32 controls"
    if webview_hits and native_hits:
        return "Mixed signals: likely a host window with embedded web content"
    return "Inconclusive"


def print_process_summary() -> None:
    processes = list_tasklist_processes()
    steam_processes = [
        process
        for process in processes
        if process["image_name"].lower() in {"steam.exe", "steamwebhelper.exe"}
    ]

    print("== Process Check ==")
    if not steam_processes:
        print("No running Steam-related processes were detected.")
        return

    for process in steam_processes:
        print(
            f"{process['image_name']}  PID={process['pid']}  Session={process['session_name']}  Memory={process['mem_usage']}"
        )


def print_window_summary() -> int:
    windows = find_steam_related_windows()

    print("\n== Window Check ==")
    if not windows:
        print("No visible Steam-related windows were detected.")
        return 1

    for index, window in enumerate(windows, start=1):
        hwnd = int(window["hwnd"])
        child_windows = list_child_windows(hwnd)

        print(f"\n[{index}] {window['title']}")
        print(f"HWND: {hwnd}")
        print(f"Class: {window['class_name']}")
        print(f"PID: {window['process_id']}")
        print(f"Process: {window['process_path'] or 'Unknown'}")
        print(f"Heuristic: {guess_window_type(child_windows)}")
        print("Child windows:")

        if not child_windows:
            print("  (No child windows detected)")
            continue

        for child in child_windows:
            print(
                "  - "
                f"Class={child['class_name'] or 'Unknown'}; "
                f"Title={child['title'] or '<empty>'}; "
                f"Visible={child['visible']}; "
                f"Enabled={child['enabled']}"
            )

    return 0


def print_steam_path() -> None:
    print("== Steam Path Check ==")
    steam_path = detect_steam_executable()
    if steam_path:
        print(f"Detected steam.exe: {steam_path}")
    else:
        print("Steam executable was not detected on this machine.")


def main() -> int:
    print("Steam UI Probe")
    print("Run this while the Steam login window is open for the best result.\n")

    print_steam_path()
    print_process_summary()
    window_exit_code = print_window_summary()

    if window_exit_code != 0:
        print(
            "\nNext step: after Steam is installed, open the login window and run this script again."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
