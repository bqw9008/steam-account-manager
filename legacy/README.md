# Legacy Tkinter UI

This folder keeps the old Tkinter implementation as a reference backup only.

The active application entry point is `main.py`, which starts the PySide6 UI in `qt_app.py`.
The Tkinter code is not imported by `main.py` and is not intended to be included in release builds.

If this legacy UI is ever needed for investigation, run it manually from the project root:

```powershell
python legacy\tk_app.py
```
