"""
EMTaxis — launch the web interface.

  python app.py

Local:  http://127.0.0.1:7860
Render: PORT is set by the platform.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
sys.path.insert(0, str(WEB))

from server import app  # noqa: E402  — Flask application (gunicorn: app:app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    print(f"EMTaxis web interface → http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
