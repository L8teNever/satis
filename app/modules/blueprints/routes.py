"""Blueprints teilen und das Sync-Skript ausliefern.

Eine Blueprint sind zwei Dateien aus dem Spiel: <Name>.sbp (der Bau) und <Name>.sbpcfg (Symbol, Farbe, Beschreibung).
Gespeichert wird nach id im Datenordner, der Name ist nur Anzeige und Dateiname beim Herunterladen.
Gleicher Name ersetzt die alte Version, das Sync-Skript erkennt das am geänderten sha.
"""
import hashlib
import os
import re
import tempfile
from pathlib import Path

from flask import abort, flash, g, jsonify, make_response, redirect, render_template, request, send_file, url_for

from ...core import data_dir, get_db, new_sync_token
from . import bp

MAX_BYTES = 50 * 1024 * 1024
EXTS = ("sbp", "sbpcfg")
SCRIPT = Path(__file__).parent / "sync" / "satis_sync.py"
BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _dir():
    path = data_dir() / "blueprints"
    path.mkdir(exist_ok=True)
    return path


def _name(filename):
    stem = BAD.sub("", Path(filename.replace("\\", "/")).name.rsplit(".", 1)[0]).strip(" .")
    return stem[:100]


def _rows():
    return get_db().execute(
        "SELECT b.*, u.name AS by_name FROM blueprints b LEFT JOIN users u ON u.id = b.uploaded_by "
        "ORDER BY b.updated_at DESC, b.id DESC").fetchall()


def _store(name, sbp, cfg, desc):
    """Legt an oder ersetzt eine Blueprint mit gleichem Namen."""
    db = get_db()
    sha = hashlib.sha256(sbp + b"\0" + (cfg or b"")).hexdigest()
    old = db.execute("SELECT id FROM blueprints WHERE name = ?", (name,)).fetchone()
    if old:
        bid = old["id"]
        db.execute("UPDATE blueprints SET name = ?, has_cfg = ?, size = ?, sha = ?, uploaded_by = ?, "
                   "description = CASE WHEN ? != '' THEN ? ELSE description END, updated_at = datetime('now') "
                   "WHERE id = ?", (name, int(cfg is not None), len(sbp), sha, g.user["id"], desc, desc, bid))
    else:
        bid = db.execute("INSERT INTO blueprints (name, description, has_cfg, size, sha, uploaded_by) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (name, desc, int(cfg is not None), len(sbp), sha, g.user["id"])).lastrowid
    folder = _dir()
    for ext, data in (("sbp", sbp), ("sbpcfg", cfg)):
        target = folder / f"{bid}.{ext}"
        if data is None:
            target.unlink(missing_ok=True)
            continue
        with tempfile.NamedTemporaryFile("wb", dir=folder, delete=False) as f:
            f.write(data)
        os.replace(f.name, target)
    db.commit()
    return bool(old)


def _bp_or_404(bid):
    b = get_db().execute("SELECT * FROM blueprints WHERE id = ?", (bid,)).fetchone()
    if not b:
        abort(404)
    return b


@bp.get("/")
def index():
    return render_template("blueprints/index.html", rows=_rows(), token=None)


@bp.post("/upload")
def upload():
    """Mehrere Dateien auf einmal. .sbp und .sbpcfg mit gleichem Namen gehören zusammen."""
    if (request.content_length or 0) > MAX_BYTES:
        abort(413)
    pairs = {}
    for f in request.files.getlist("files"):
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        name = _name(f.filename)
        if ext in EXTS and name:
            pairs.setdefault(name, {})[ext] = f.read()
    desc = request.form.get("description", "").strip()[:500]
    done, missing = [], []
    for name, files in pairs.items():
        if "sbp" not in files:
            missing.append(name)
            continue
        _store(name, files["sbp"], files.get("sbpcfg"), desc)
        done.append(name)
    if request.headers.get("X-Satis-Token"):
        return jsonify(ok=done, missing=missing), (200 if done else 400)
    if done:
        flash("Hochgeladen: " + ", ".join(done))
    if missing:
        flash("Ohne .sbp-Datei übersprungen: " + ", ".join(missing))
    if not pairs:
        flash("Wähl die .sbp-Datei aus, am besten zusammen mit der .sbpcfg.")
    return redirect(url_for("blueprints.index"))


@bp.get("/<int:bid>/<ext>")
def download(bid, ext):
    if ext not in EXTS:
        abort(404)
    b = _bp_or_404(bid)
    path = _dir() / f"{bid}.{ext}"
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=f"{b['name']}.{ext}",
                     mimetype="application/octet-stream", max_age=0)


@bp.post("/<int:bid>/delete")
def delete(bid):
    b = _bp_or_404(bid)
    if g.user["role"] != "admin" and b["uploaded_by"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("DELETE FROM blueprints WHERE id = ?", (bid,))
    db.commit()
    for ext in EXTS:
        (_dir() / f"{bid}.{ext}").unlink(missing_ok=True)
    flash(f"„{b['name']}“ gelöscht.")
    return redirect(url_for("blueprints.index"))


@bp.get("/api/list")
def api_list():
    """Für das Sync-Skript: was gerade auf dem Server liegt."""
    return jsonify(blueprints=[{
        "id": b["id"], "name": b["name"], "sha": b["sha"], "has_cfg": bool(b["has_cfg"]),
        "by": b["by_name"], "updated": b["updated_at"],
        "files": {ext: url_for("blueprints.download", bid=b["id"], ext=ext)
                  for ext in EXTS if ext == "sbp" or b["has_cfg"]},
    } for b in _rows()])


@bp.get("/token")
def token_page():
    return redirect(url_for("blueprints.index"))


@bp.post("/token")
def token():
    """Neuer Sync-Schlüssel für den eigenen Nutzer. Ein alter verliert dabei seine Gültigkeit."""
    if g.get("via_token"):
        abort(403)
    return render_template("blueprints/index.html", rows=_rows(), token=new_sync_token(g.user["id"]))


@bp.get("/skript")
def script():
    """Das Sync-Skript, die Server-Adresse ist schon eingetragen."""
    # Hinter dem Cloudflare-Tunnel kommt die Anfrage als http an, nach außen ist es immer https
    host = request.host if request.host.split(":")[0] in ("localhost", "127.0.0.1") else None
    base = f"http://{host}" if host else f"https://{request.host}"
    src = SCRIPT.read_text(encoding="utf-8").replace("__SATIS_URL__", base)
    res = make_response(src)
    res.headers["Content-Type"] = "text/x-python; charset=utf-8"
    res.headers["Content-Disposition"] = "attachment; filename=satis_sync.py"
    return res
