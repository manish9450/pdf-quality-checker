"""
desktop_app.py -- Native desktop window wrapper for the PDF Quality Checker.

Run this instead of app.py directly for the "real software" experience:
double-click, a proper app window opens (no browser tabs, no address
bar, no visible URL), works exactly like any other installed program.

Under the hood, this is still the same Flask app -- it just runs
silently in a background thread, and pywebview displays it inside a
native window instead of you opening a browser tab yourself. Nothing
about privacy changes (it was already 100% local either way), only how
it looks: no browser chrome that might make someone wonder whether
their PDF is being uploaded somewhere.
"""

import threading
import webview

from app import app  # the existing Flask app, unchanged


def start_flask():
    # use_reloader must stay off -- Flask's reloader spawns a second
    # process, which breaks the "one window, one process" model this
    # wrapper depends on.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    webview.create_window(
        "PDF Quality Checker",
        "http://127.0.0.1:5000",
        width=1000,
        height=800,
        resizable=True,
    )
    webview.start()