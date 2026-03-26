"""
Standalone launcher for Email Extractor.
This is the entry point used by PyInstaller.
It starts Flask in a background thread and opens the browser automatically.
"""

import os
import sys
import threading
import time
import webbrowser

# --------------------------------------------------------------------------
# Resource path helper (works both in dev and in PyInstaller bundle)
# --------------------------------------------------------------------------

def resource_path(relative: str) -> str:
    """Return absolute path to a bundled resource."""
    if hasattr(sys, "_MEIPASS"):
        # Running inside PyInstaller bundle
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


# Expose helper so app.py can import it
os.environ["RESOURCE_PATH_BASE"] = (
    sys._MEIPASS if hasattr(sys, "_MEIPASS")
    else os.path.dirname(os.path.abspath(__file__))
)

# --------------------------------------------------------------------------
# Import and configure Flask app (must come after env var is set)
# --------------------------------------------------------------------------

from app import app  # noqa: E402

HOST = "127.0.0.1"
PORT = 5000
URL  = f"http://{HOST}:{PORT}"


def _open_browser():
    """Wait for Flask to be ready, then open the default browser."""
    time.sleep(1.5)
    webbrowser.open(URL)


def main():
    print("=" * 50)
    print("  网页邮箱提取器")
    print(f"  访问地址: {URL}")
    print("  关闭此窗口即可退出程序")
    print("=" * 50)

    # Open browser in background thread
    t = threading.Thread(target=_open_browser, daemon=True)
    t.start()

    # Start Flask (production-like, no reloader, no debugger)
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
