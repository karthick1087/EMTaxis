"""EMTaxis web server (Flask)."""

from __future__ import annotations

import os
import pickle
import secrets
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

from engine import engine

ROOT = Path(__file__).resolve().parent
UPLOADS = ROOT / "uploads"
SESSIONS = ROOT / "sessions"
UPLOADS.mkdir(exist_ok=True)
SESSIONS.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
# Set EMTAXIS_SECRET_KEY in production; random fallback is fine for local use
app.secret_key = os.environ.get("EMTAXIS_SECRET_KEY") or secrets.token_hex(16)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB


def _session_path(sid: str) -> Path:
    return SESSIONS / f"{sid}.pkl"


def _save_result(sid: str, payload: dict) -> None:
    # Drop heavy objects? keep X + probas for explain
    with open(_session_path(sid), "wb") as f:
        pickle.dump(
            {"X": payload["X"], "probas": payload["probas"], "samples": payload["samples"]},
            f,
        )


def _load_result(sid: str) -> dict | None:
    p = _session_path(sid)
    if not p.exists():
        return None
    with open(p, "rb") as f:
        return pickle.load(f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        data_type = request.form.get("data_type", "log₂(TPM + 1)")

        if "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            uid = uuid.uuid4().hex[:10]
            path = UPLOADS / f"{uid}_{f.filename}"
            f.save(path)
        else:
            return jsonify({"error": "Please upload a CSV file."}), 400

        payload = engine.predict_file(path, data_type)
        sid = uuid.uuid4().hex
        session["result_id"] = sid
        _save_result(sid, payload)

        # JSON-safe response (no DataFrame)
        return jsonify(
            {
                "ok": True,
                "result_id": sid,
                "summary": payload["summary"],
                "rows": payload["rows"],
                "cohort_img": payload["cohort_img"],
                "samples": payload["samples"],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/explain", methods=["POST"])
def explain():
    try:
        body = request.get_json(force=True)
        sample = body.get("sample")
        sid = body.get("result_id") or session.get("result_id")
        if not sample:
            return jsonify({"error": "No sample selected."}), 400
        if not sid:
            return jsonify({"error": "Run prediction first."}), 400
        data = _load_result(sid)
        if data is None:
            return jsonify({"error": "Session expired. Run prediction again."}), 400
        out = engine.explain_sample(data["X"], data["probas"], sample)
        return jsonify({"ok": True, **out})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    print("EMTaxis web server → http://127.0.0.1:7860")
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
