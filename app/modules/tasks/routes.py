from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for

from ...core import get_db
from . import bp

STATUS = {"open": "Offen", "doing": "In Arbeit", "done": "Erledigt"}
PRIORITY = {1: "Niedrig", 2: "Normal", 3: "Hoch"}


def _users():
    return get_db().execute("SELECT id, name FROM users ORDER BY name COLLATE NOCASE").fetchall()


def _task_or_404(task_id):
    t = get_db().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not t:
        abort(404)
    return t


def _valid_due(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _form():
    title = request.form.get("title", "").strip()
    if not title:
        return None
    try:
        prio = min(3, max(1, int(request.form.get("priority", 2))))
    except ValueError:
        prio = 2
    assignee = {str(u["id"]): u["id"] for u in _users()}.get(request.form.get("assignee_id", ""))
    status = request.form.get("status", "open")
    return {
        "title": title[:200],
        "description": request.form.get("description", "").strip()[:5000],
        "priority": prio,
        "assignee_id": assignee,
        "status": status if status in STATUS else "open",
        "due": _valid_due(request.form.get("due", "")),
    }


@bp.get("/")
def index():
    status = request.args.get("status", "")
    who = request.args.get("who", "")
    users = _users()
    sql = ("SELECT t.*, a.name AS assignee_name, c.name AS creator_name FROM tasks t "
           "LEFT JOIN users a ON a.id = t.assignee_id LEFT JOIN users c ON c.id = t.created_by WHERE 1=1")
    args = []
    if status in STATUS:
        sql += " AND t.status = ?"
        args.append(status)
    if who == "me":
        sql += " AND t.assignee_id = ?"
        args.append(g.user["id"])
    elif who == "none":
        sql += " AND t.assignee_id IS NULL"
    elif who in {str(u["id"]) for u in users}:
        sql += " AND t.assignee_id = ?"
        args.append(int(who))
    sql += " ORDER BY (t.status = 'done'), t.priority DESC, t.due IS NULL, t.due, t.id DESC"
    rows = get_db().execute(sql, args).fetchall()
    return render_template("tasks/index.html", tasks=rows, users=users, STATUS=STATUS, PRIORITY=PRIORITY,
                           f_status=status, f_who=who, today=date.today().isoformat())


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        data = _form()
        if data:
            db = get_db()
            db.execute(
                "INSERT INTO tasks (title, description, priority, assignee_id, status, due, created_by) "
                "VALUES (:title, :description, :priority, :assignee_id, :status, :due, :uid)",
                {**data, "uid": g.user["id"]})
            db.commit()
            flash("Aufgabe angelegt.")
            return redirect(url_for("tasks.index"))
        flash("Titel fehlt.")
    return render_template("tasks/form.html", t=None, users=_users(), STATUS=STATUS, PRIORITY=PRIORITY)


@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
def edit(task_id):
    t = _task_or_404(task_id)
    if request.method == "POST":
        data = _form()
        if data:
            db = get_db()
            db.execute(
                "UPDATE tasks SET title=:title, description=:description, priority=:priority, "
                "assignee_id=:assignee_id, status=:status, due=:due, updated_at=datetime('now') WHERE id=:id",
                {**data, "id": task_id})
            db.commit()
            flash("Gespeichert.")
            return redirect(url_for("tasks.index"))
        flash("Titel fehlt.")
    return render_template("tasks/form.html", t=t, users=_users(), STATUS=STATUS, PRIORITY=PRIORITY)


@bp.post("/<int:task_id>/status")
def set_status(task_id):
    _task_or_404(task_id)
    status = request.form.get("status")
    if status in STATUS:
        db = get_db()
        db.execute("UPDATE tasks SET status=?, updated_at=datetime('now') WHERE id=?", (status, task_id))
        db.commit()
    return redirect(request.referrer or url_for("tasks.index"))


@bp.post("/<int:task_id>/delete")
def delete(task_id):
    t = _task_or_404(task_id)
    if g.user["role"] != "admin" and t["created_by"] != g.user["id"]:
        abort(403)
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    flash("Aufgabe gelöscht.")
    return redirect(url_for("tasks.index"))
