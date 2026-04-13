# Steam Account Manager

### [中文](README_zh.md) | [English](README.md)

Steam Account Manager is a local Windows desktop tool for managing multiple Steam account records and starting a Steam login attempt for the selected account.

The current UI is built with PySide6. The older Tkinter implementation is still kept in `app.py` as a fallback/reference, but `main.py` starts the PySide6 UI by default.

![UI](imgs/main_page.png)

## Features

- Local account management with JSON persistence.
- Search and status filtering.
- Create, edit, delete, and batch-delete accounts.
- Batch status updates for selected accounts.
- Quick import for one-line or multi-line account text.
- Bulk text import with preview before saving.
- Duplicate import handling by `login_name`.
- Safer import overwrite behavior: empty imported fields do not wipe existing `last_login` or notes.
- Steam path auto-detection before manual selection.
- Steam login panel with configurable shutdown behavior:
  - graceful shutdown first, ask before force close
  - force close directly
- Light/dark UI styling based on the Windows app theme.

## Requirements

- Windows
- Python 3.10+
- PySide6

Install dependencies:

```powershell
pip install -r requirements.txt
```

If you use Conda:

```powershell
conda activate py
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

`main.py` starts `qt_app.py` by default.

If PySide6 is not installed, the program will fail with an install hint. The Tkinter fallback can be enabled explicitly:

```powershell
$env:SAM_ALLOW_TKINTER_FALLBACK="1"
python main.py
```

## Data Files

Runtime data is stored in the local `data/` directory:

```text
data/accounts.json
data/settings.json
```

These files are intentionally ignored by Git because they may contain account names, passwords, email addresses, phone numbers, Steam paths, and local settings.

## Import Format

The importer is designed for loosely structured account text containing labels such as:

- `5E账号`
- `5E密码`
- `昵称`
- `steam账号`
- `密码`
- `邮箱账号` / `油箱账号`
- `邮箱地址` / `油箱地址`
- `手机号`

One-account-per-line formats and multi-line account blocks are both supported.

## Security Notes

This tool is intended for local personal use and low-value secondary accounts.

Important tradeoffs:

- Account passwords are stored in local JSON as plain text.
- The Steam login attempt currently uses `steam.exe -login <login_name> <password>`.
- Command-line arguments may be visible to local diagnostic tools or other local processes.
- Do not commit, upload, or share `data/accounts.json`, `data/settings.json`, or raw import files such as `accounts.txt`.

If you need stronger security, add encrypted storage before using this with important accounts.

## Packaging

For a Windows executable, PyInstaller is the most practical option.

Recommended first build:

```powershell
pip install pyinstaller
pyinstaller --noconsole --onedir --name SteamAccountManager main.py
```

Recommended layout:

```text
SteamAccountManager/
├─ SteamAccountManager.exe
├─ _internal/
└─ data/
   ├─ accounts.json
   └─ settings.json
```

Keep real account data outside Git and avoid bundling real `accounts.json` into distributable archives.

## Project Structure

```text
main.py              Entry point; starts the PySide6 UI
qt_app.py            Current PySide6 desktop UI
app.py               Older Tkinter UI fallback/reference
models.py            SteamAccount data model
repositories.py      JSON load/save with validation and atomic writes
text_importer.py     Account text parsing logic
system_utils.py      Windows/Steam helper functions
config.py            Paths, status definitions, translations, theme constants
steam_ui_probe.py    Helper script for investigating Steam login UI structure
data/                Local runtime data, ignored by Git
```

## Notes

This is a personal local utility, not an official Steam tool. Use it at your own risk.
