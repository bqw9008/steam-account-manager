from __future__ import annotations

import os
import sys

try:
    from .qt_app import main
except ImportError as qt_error:
    try:
        from qt_app import main
    except ImportError as script_qt_error:
        if os.environ.get("SAM_ALLOW_TKINTER_FALLBACK") == "1":
            try:
                from .app import main
            except ImportError:
                from app import main
        else:
            print(
                "Failed to start the PySide6 UI.\n"
                "Install dependencies in the Python environment used to run this project:\n"
                "  pip install -r requirements.txt\n\n"
                f"Package import error: {qt_error}\n"
                f"Script import error: {script_qt_error}",
                file=sys.stderr,
            )
            raise


if __name__ == "__main__":
    main()
