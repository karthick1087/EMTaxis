"""
EMTaxis — launch the web interface.

  python app.py

Opens http://127.0.0.1:7860
"""

from pathlib import Path
import sys

WEB = Path(__file__).resolve().parent / "web"
sys.path.insert(0, str(WEB))

from server import app  # noqa: E402

if __name__ == "__main__":
    print("EMTaxis web interface → http://127.0.0.1:7860")
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
