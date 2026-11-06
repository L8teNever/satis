from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

from ...core import get_db
from . import bp

SORTS = {"manual": "Eigene Reihenfolge", "updated": "Zuletzt geändert", "title": "Titel", "category": "Kategorie"}
ORDER = {
    "manual": "n.position, n.id",
    "updated": "n.updated_at DESC, n.id DESC",
    "title": "n.title = '', n.title COLLATE NOCASE, n.id",
    "category": "n.category = '', n.category COLLATE NOCASE, n.position, n.id",
}


def _note(note_id, edit=False):
    """Notiz mit Rechten des aktuellen Nutzers: eigene oder freigegebene."""
    n = get_db().execute(
        "SELECT n.*, u.name AS owner_name, s.can_edit AS shared_edit FROM notes n "
        "JOIN users u ON u.id = n.owner_id "
        "LEFT JOIN note_shares s ON s.note_id = n.id AND s.user_id = :me "
        "WHERE n.id = :id AND (n.owner_id = :me OR s.user_id IS NOT NULL)",
        {"id": note_id, "me": g.user["id"]}).fetchone()
    if not n:
        abort(404)
    if edit and n["owner_id"] != g.user["id"] and not n["shared_edit"]:
        abort(403)
    return n


def _own(note_id):
    n = _note(note_id)
    if n["owner_id"] != g.user["id"]:
        abort(403)
    return n


def _back():
    return redirect(request.referrer or url_for("notizen.index"))


@bp.get("/")
def index():
    db = get_db()
    me = g.user["id"]
    sort = request.args.get("sort", "manual")
    sort = sort if sort in SORTS else "manual"
    cat = request.args.get("cat", "")
    view = request.args.get("view", "")  # "" alle, "mine" eigene, "shared" mit mir geteilt
    sql = ("SELECT n.*, u.name AS owner_name, s.can_edit AS shared_edit, "
           "(SELECT group_concat(su.name, ', ') FROM note_shares x JOIN users su ON su.id = x.user_id "
           " WHERE x.note_id = n.id) AS shared_with "
           "FROM notes n JOIN users u ON u.id = n.owner_id "
           "LEFT JOIN note_shares s ON s.note_id = n.id AND s.user_id = :me "
           "WHERE (n.owner_id = :me OR s.user_id IS NOT NULL)")
    args = {"me": me}
    if view == "mine":
        sql += " AND n.owner_id = :me"
    elif view == "shared":
        sql += " AND n.owner_id != :me"
    if cat:
        sql += " AND n.category = :cat"
        args["cat"] = cat
    sql += " ORDER BY n.pinned DESC, " + ORDER[sort]
    notes = db.execute(sql, args).fetchall()
    cats = [r[0] for r in db.execute(
        "SELECT DISTINCT n.category FROM notes n LEFT JOIN note_shares s ON s.note_id = n.id AND s.user_id = :me "
        "WHERE n.category != '' AND (n.owner_id = :me OR s.user_id IS NOT NULL) ORDER BY n.category COLLATE NOCASE",
        {"me": me})]
    return render_template("notizen/index.html", notes=notes, cats=cats, SORTS=SORTS,
                           f_sort=sort, f_cat=cat, f_view=view)


@bp.post("/new")
def new():
    db = get_db()
    me = g.user["id"]
    pos = db.execute("SELECT COALESCE(MIN(position), 0) - 1 FROM notes WHERE owner_id = ?", (me,)).fetchone()[0]
    cat = request.form.get("category", "").strip()[:60]
    db.execute("INSERT INTO notes (owner_id, position, category) VALUES (?, ?, ?)", (me, pos, cat))
    db.commit()
    return _back()


@bp.post("/<int:note_id>/save")
def save(note_id):
    """Speichert automatisch beim Tippen (fetch aus notizen.js) oder per Formular."""
    _note(note_id, edit=True)
    db = get_db()
    db.execute("UPDATE notes SET title = ?, body = ?, category = ?, updated_at = datetime('now') WHERE id = ?",
               (request.form.get("title", "").strip()[:200], request.form.get("body", "")[:50000],
                request.form.get("category", "").strip()[:60], note_id))
    db.commit()
    if request.headers.get("X-Satis-Autosave") or request.form.get("autosave"):
        return jsonify(ok=True)
    flash("Notiz gespeichert.")
    return _back()


@bp.post("/<int:note_id>/pin")
def pin(note_id):
    n = _own(note_id)
    db = get_db()
    db.execute("UPDATE notes SET pinned = ? WHERE id = ?", (0 if n["pinned"] else 1, note_id))
    db.commit()
    return _back()


@bp.post("/<int:note_id>/move")
def move(note_id):
    """Eine Stelle nach vorn oder hinten in der eigenen Reihenfolge."""
    n = _own(note_id)
    db = get_db()
    ids = [r[0] for r in db.execute(
        "SELECT id FROM notes WHERE owner_id = ? AND pinned = ? ORDER BY position, id", (n["owner_id"], n["pinned"]))]
    i = ids.index(note_id)
    j = i - 1 if request.form.get("dir") == "up" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        db.executemany("UPDATE notes SET position = ? WHERE id = ?", [(p, x) for p, x in enumerate(ids)])
        db.commit()
    return _back()


@bp.route("/<int:note_id>/share", methods=["GET", "POST"])
def share(note_id):
    n = _own(note_id)
    db = get_db()
    users = db.execute("SELECT id, name FROM users WHERE id != ? ORDER BY name COLLATE NOCASE",
                       (g.user["id"],)).fetchall()
    if request.method == "POST":
        valid = {u["id"] for u in users}
        db.execute("DELETE FROM note_shares WHERE note_id = ?", (note_id,))
        rows = []
        for u in valid:
            mode = request.form.get(f"u{u}", "")
            if mode in ("read", "edit"):
                rows.append((note_id, u, 1 if mode == "edit" else 0))
        db.executemany("INSERT INTO note_shares (note_id, user_id, can_edit) VALUES (?, ?, ?)", rows)
        db.commit()
        flash("Freigabe gespeichert." if rows else "Notiz ist wieder nur für dich.")
        return redirect(url_for("notizen.index"))
    shares = {r["user_id"]: r["can_edit"] for r in db.execute(
        "SELECT user_id, can_edit FROM note_shares WHERE note_id = ?", (note_id,))}
    return render_template("notizen/share.html", n=n, users=users, shares=shares)


@bp.post("/<int:note_id>/leave")
def leave(note_id):
    """Freigegebene Notiz aus der eigenen Liste entfernen."""
    _note(note_id)
    db = get_db()
    db.execute("DELETE FROM note_shares WHERE note_id = ? AND user_id = ?", (note_id, g.user["id"]))
    db.commit()
    return _back()


@bp.post("/<int:note_id>/delete")
def delete(note_id):
    _own(note_id)
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    flash("Notiz gelöscht.")
    return _back()
