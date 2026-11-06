import re
import sqlite3

from flask import abort, flash, g, redirect, render_template, request, url_for

from ...core import get_db
from . import bp

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.get("/")
def index():
    users = get_db().execute("SELECT * FROM users ORDER BY role, name COLLATE NOCASE").fetchall()
    return render_template("admin/index.html", users=users)


@bp.post("/add")
def add():
    name = request.form.get("name", "").strip()[:80]
    email = request.form.get("email", "").strip().lower()[:200]
    role = "admin" if request.form.get("role") == "admin" else "user"
    if not name or not EMAIL_RE.match(email):
        flash("Name und gültige E-Mail nötig.")
    else:
        try:
            db = get_db()
            db.execute("INSERT INTO users (email, name, role) VALUES (?, ?, ?)", (email, name, role))
            db.commit()
            flash(f"{name} angelegt. Die E-Mail muss auch in der Cloudflare-Access-Policy erlaubt sein.")
        except sqlite3.IntegrityError:
            flash("Diese E-Mail gibt es schon.")
    return redirect(url_for("admin.index"))


@bp.post("/<int:user_id>/update")
def update(user_id):
    if user_id == g.user["id"] and request.form.get("role") != "admin":
        flash("Du kannst dir nicht selbst die Admin-Rolle nehmen.")
        return redirect(url_for("admin.index"))
    name = request.form.get("name", "").strip()[:80]
    role = "admin" if request.form.get("role") == "admin" else "user"
    if name:
        db = get_db()
        db.execute("UPDATE users SET name=?, role=? WHERE id=?", (name, role, user_id))
        db.commit()
        flash("Gespeichert.")
    return redirect(url_for("admin.index"))


@bp.post("/<int:user_id>/delete")
def delete(user_id):
    if user_id == g.user["id"]:
        abort(400, "Du kannst dich nicht selbst löschen.")
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("Nutzer gelöscht (Aufgaben bleiben, ohne Zuständigen).")
    return redirect(url_for("admin.index"))
