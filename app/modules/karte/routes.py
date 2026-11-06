"""Spielstand hochladen und die fertige Welt ausliefern.

Das Einlesen läuft im Hintergrund, große Spielstände brauchen länger als eine Anfrage dauern darf.
Die Welt und der Status liegen als Dateien im Datenordner, damit alle Gunicorn-Worker denselben Stand sehen.
"""
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from flask import abort, g, jsonify, render_template, request, send_file

from ...core import bump_live, data_dir, get_db
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
    return render_template("karte/index.html", tiles=tile_levels())


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


# Schärfere Karten als Kacheln (256 px, z/x/y.jpg, gleicher Bereich wie BOUNDS): game = Spielkarte,
# ground = Gelände mit Biomen, relief = Höhen. Sie gehören Coffee Stain und liegen im Datenordner unter
# karte/tiles/<karte>/ (Quelle: Tunefish92/SatisfactoryMapRenderer, Ordner app/basemaps/tiles, „background“ = game).
# Fehlen sie, nimmt die Karte das einzelne Bild von /bild.
TILE_MAPS = ("game", "ground", "relief")


def tile_levels():
    """Höchste vorhandene Zoomstufe je Karte, z. B. {"game": 5, "ground": 7}."""
    out = {}
    for name in TILE_MAPS:
        try:
            levels = [int(d.name) for d in (_dir() / "tiles" / name).iterdir() if d.name.isdigit()]
        except OSError:
            continue
        if levels:
            out[name] = max(levels)
    return out


@bp.get("/kacheln/<name>/<int:z>/<int:x>/<int:y>.jpg")
def tile(name, z, x, y):
    if name not in TILE_MAPS or not 0 <= z <= 12 or not 0 <= x < 2 ** z or not 0 <= y < 2 ** z:
        abort(404)
    path = _dir() / "tiles" / name / str(z) / str(x) / f"{y}.jpg"
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=7 * 86400)


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


# --------------------------------------------------------------------------- Zeichnungen
# Alle sehen und löschen alle Zeichnungen, die Karte ist ein gemeinsamer Planungstisch.
KINDS = {"pen": (4, 4000), "line": (4, 4), "rect": (4, 4), "pin": (2, 2)}  # Anzahl Zahlen in points: min, max
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _mark(row):
    return {"id": row["id"], "kind": row["kind"], "color": row["color"], "width": row["width"],
            "points": json.loads(row["points"]), "text": row["text"], "by": row["name"], "byId": row["user_id"],
            "at": row["created_at"]}


@bp.get("/zeichnungen")
def marks():
    rows = get_db().execute("SELECT m.*, u.name FROM karte_marks m JOIN users u ON u.id = m.user_id ORDER BY m.id").fetchall()
    response = jsonify(marks=[_mark(r) for r in rows], me=g.user["id"])
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.post("/zeichnungen")
def add_mark():
    data = request.get_json(silent=True) or {}
    kind, color, points = data.get("kind"), str(data.get("color", "")), data.get("points")
    if kind not in KINDS or not COLOR.match(color) or not isinstance(points, list):
        return jsonify(error="Zeichnung unvollständig."), 400
    low, high = KINDS[kind]
    if not low <= len(points) <= high or len(points) % 2:
        return jsonify(error="Zeichnung unvollständig."), 400
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) < 1e7 for v in points):
        return jsonify(error="Zeichnung unvollständig."), 400
    try:
        width = min(20.0, max(1.0, float(data.get("width", 3))))
    except (TypeError, ValueError):
        width = 3.0
    text = str(data.get("text", ""))[:120].strip()
    db = get_db()
    cur = db.execute("INSERT INTO karte_marks (user_id, kind, color, width, points, text) VALUES (?, ?, ?, ?, ?, ?)",
                     (g.user["id"], kind, color.lower(), width, json.dumps([round(v, 1) for v in points]), text))
    db.commit()
    row = db.execute("SELECT m.*, u.name FROM karte_marks m JOIN users u ON u.id = m.user_id WHERE m.id = ?",
                     (cur.lastrowid,)).fetchone()
    return jsonify(_mark(row)), 201


@bp.delete("/zeichnungen/<int:mark_id>")
def delete_mark(mark_id):
    db = get_db()
    if not db.execute("DELETE FROM karte_marks WHERE id = ?", (mark_id,)).rowcount:
        abort(404)
    db.commit()
    return jsonify(ok=True)
