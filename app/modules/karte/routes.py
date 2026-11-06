"""Spielstand hochladen und die fertige Welt ausliefern.

Das Einlesen läuft im Hintergrund, große Spielstände brauchen länger als eine Anfrage dauern darf.
Die Welt und der Status liegen als Dateien im Datenordner, damit alle Gunicorn-Worker denselben Stand sehen.
"""
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from flask import abort, g, jsonify, render_template, request, send_file

from ...core import bump_live, data_dir
from . import bp
from .layers import build

EXTRACT = Path(__file__).parent / "extract" / "extract.mjs"
MAX_BYTES = 512 * 1024 * 1024
STALE_SECONDS = 15 * 60


def _dir():
    path = data_dir() / "karte"
    path.mkdir(exist_ok=True)
    return path


def _write(path, data):
    """Atomar, damit nie eine halbe Datei ausgeliefert wird."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(f.name, path)


def _status():
    try:
        status = json.loads((_dir() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "empty"}
    if status["state"] == "running" and time.time() - status["started"] > STALE_SECONDS:
        return {"state": "failed", "error": "Das Einlesen wurde unterbrochen. Lad den Spielstand noch einmal hoch."}
    return status


def _read_save(folder, sav, by, filename=""):
    raw = folder / "raw.json"
    try:
        run = subprocess.run(["node", "--max-old-space-size=4096", str(EXTRACT), str(sav), str(raw)],
                             capture_output=True, timeout=STALE_SECONDS - 60)
        if run.returncode:
            raise ValueError(run.stderr.decode("utf-8", "replace")[-500:])
        world = build(json.loads(raw.read_text(encoding="utf-8")), by, filename=filename)
        _write(folder / "world.json", world)
        _write(folder / "status.json", {"state": "ok", "at": time.time(), "filename": filename})
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print("Spielstand nicht lesbar:", exc, flush=True)
        _write(folder / "status.json", {"state": "failed", "error": "Die Datei ließ sich nicht als Spielstand lesen.", "filename": filename})
    finally:
        sav.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)
        bump_live()  # fertig oder fehlgeschlagen: die offenen Karten holen sich den neuen Stand


@bp.get("/")
def index():
    return render_template("karte/index.html")


@bp.post("/upload")
def upload():
    if (request.content_length or 0) > MAX_BYTES:
        abort(413)
    file = request.files.get("save")
    if not file or not file.filename.lower().endswith(".sav"):
        return jsonify(error="Wähl eine .sav-Datei aus."), 400
    if _status()["state"] == "running":
        return jsonify(error="Gerade wird schon ein Spielstand eingelesen."), 409
    folder = _dir()
    filename = Path(file.filename).name
    _write(folder / "status.json", {"state": "running", "started": time.time(), "filename": filename})
    sav = folder / "upload.sav"
    file.save(sav)
    threading.Thread(target=_read_save, args=(folder, sav, g.user["name"], filename), daemon=True).start()
    return jsonify(_status()), 202


@bp.get("/status")
def status():
    return jsonify(_status())


@bp.get("/world.json")
def world():
    path = _dir() / "world.json"
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="application/json", max_age=0)


MAP_URL = "https://raw.githubusercontent.com/Fade97/satisfactory-logistics-map/main/frontend/public/map.jpg"


@bp.get("/bild")
def image():
    """Das Kartenbild gehört Coffee Stain und liegt im Datenordner. Fehlt es, wird es einmalig geladen."""
    path = _dir() / "map.jpg"
    if not path.exists():
        try:
            import urllib.request
            urllib.request.urlretrieve(MAP_URL, path)
        except Exception:
            abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=86400)
