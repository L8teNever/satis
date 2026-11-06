import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for

from ...core import get_db
from . import bp
from .solver import EPS, EXTERNAL, ITEMS, RECIPES, SolveError, default_recipe, recipes_for, solve

MAX_TARGETS = 30
BERLIN = ZoneInfo("Europe/Berlin")
ACTIONS = {
    "created": ("fa-plus", "erstellt"),
    "updated": ("fa-edit", "geändert"),
    "deleted": ("fa-trash-alt", "gelöscht"),
    "restored": ("fa-undo", "wiederhergestellt"),
}
ITEM_CHOICES = sorted(((k, v["name"]) for k, v in ITEMS.items() if recipes_for(k)), key=lambda x: x[1])


@bp.app_template_filter("num")
def num(value):
    """Zahl auf Deutsch, ohne unnötige Nachkommastellen."""
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


@bp.app_template_filter("when")
def when(value):
    """SQLite-Zeit (UTC) als deutsche Ortszeit."""
    t = datetime.fromisoformat(value).replace(tzinfo=timezone.utc).astimezone(BERLIN)
    return t.strftime("%d.%m.%Y %H:%M")


def _rate(text):
    try:
        rate = float(str(text).replace(",", "."))
    except ValueError:
        return None
    return rate if math.isfinite(rate) and 0 < rate <= 1_000_000 else None


def _clean(rows, recipes):
    """Prüft Eingaben. rows: [(item, rate)], recipes: {item: wahl}. Unbekanntes fällt still weg."""
    targets = {}
    for item, rate in rows:
        value = _rate(rate) or (1.0 if rate in ("", None) else None)
        if item in ITEMS and value and (item in targets or len(targets) < MAX_TARGETS):
            targets[item] = targets.get(item, 0.0) + value
    choices = {}
    for item, cls in recipes.items():
        if item in ITEMS and cls != default_recipe(item) and (cls == EXTERNAL or cls in recipes_for(item)):
            choices[item] = cls
    return targets, choices


def _from_request(args):
    items, rates = args.getlist("item"), args.getlist("rate")
    rows = list(zip(items, rates + [""] * len(items)))
    remove = args.get("remove", "")
    if remove.isdigit() and int(remove) < len(rows):
        del rows[int(remove)]
    recipes = dict(v.split("|", 1) for v in args.getlist("recipe") if "|" in v)
    return _clean(rows, recipes)


def _state(targets, choices):
    return json.dumps({"targets": targets, "choices": choices}, sort_keys=True)


def _summary(targets):
    return ", ".join(f"{num(r)} {ITEMS[i]['name']}" for i, r in targets.items())


def _plan_or_404(plan_id):
    plan = get_db().execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        abort(404)
    return plan


def _may_delete(plan):
    return g.user["role"] == "admin" or plan["created_by"] == g.user["id"]


def _log(plan_id, action, detail=""):
    get_db().execute("INSERT INTO plan_log (plan_id, user_name, action, detail) VALUES (?, ?, ?, ?)",
                     (plan_id, g.user["name"], action, detail))


def _users():
    return get_db().execute("SELECT id, name FROM users ORDER BY name COLLATE NOCASE").fetchall()


def _progress(plan_id, steps):
    """Stand je Schritt: {rezept: {...}}. Abgehakt zählt nur, solange die gebaute Menge noch reicht."""
    rows = {r["recipe"]: r for r in get_db().execute(
        "SELECT p.*, u.name AS assignee FROM plan_steps p LEFT JOIN users u ON u.id = p.assignee_id "
        "WHERE p.plan_id = ?", (plan_id,))}
    progress = {}
    for s in steps:
        row = rows.get(s["recipe"])
        ticked = row is not None and row["done_at"] is not None
        done = ticked and row["done_count"] >= s["count"] - EPS
        assignee = row["assignee"] if row else None
        by = row["done_by_name"] if ticked else None
        progress[s["recipe"]] = {
            "done": done, "short": ticked and not done, "by": by, "at": row["done_at"] if ticked else None,
            "count": row["done_count"] if ticked else None, "assignee_id": row["assignee_id"] if row else None,
            "tag": f"Erledigt: {by}" if done else f"Zuständig: {assignee}" if assignee else "",
        }
    return progress


def _render(targets, choices, plan=None):
    result, error = None, None
    if targets:
        try:
            result = solve(targets, choices)
        except SolveError as exc:
            error = str(exc)
    log, progress = [], {}
    if plan:
        log = get_db().execute("SELECT * FROM plan_log WHERE plan_id = ? ORDER BY id DESC", (plan["id"],)).fetchall()
    # Abhaken geht nur auf dem gespeicherten Stand, nicht auf ungespeicherten Änderungen
    unsaved = bool(plan) and _state(targets, choices) != _state(*_stored(plan))
    tracking = bool(result and plan and not plan["deleted_at"] and not unsaved)
    if tracking:
        progress = _progress(plan["id"], result["steps"])
        for node in result["graph"]["nodes"]:
            if node["id"] in progress:
                node.update(done=progress[node["id"]]["done"], tag=progress[node["id"]]["tag"])
    return render_template(
        "fabriken/calc.html", targets=targets, choices=choices, result=result, error=error, plan=plan, log=log,
        tracking=tracking, unsaved=unsaved, progress=progress, users=_users() if tracking else [],
        ITEMS=ITEMS, RECIPES=RECIPES, ITEM_CHOICES=ITEM_CHOICES, ACTIONS=ACTIONS, EXTERNAL=EXTERNAL,
        recipes_for=recipes_for, default_recipe=default_recipe, state=_state(targets, choices),
        may_delete=plan is not None and _may_delete(plan))


@bp.get("/")
def index():
    show_deleted = request.args.get("show") == "deleted"
    rows = get_db().execute(
        f"SELECT * FROM plans WHERE deleted_at IS {'NOT ' if show_deleted else ''}NULL "
        "ORDER BY COALESCE(deleted_at, updated_at) DESC, id DESC").fetchall()
    plans = [{"row": p, "summary": _summary(_stored(p)[0]), "may_delete": _may_delete(p)} for p in rows]
    return render_template("fabriken/index.html", plans=plans, show_deleted=show_deleted)


@bp.get("/rechner")
def calc():
    return _render(*_from_request(request.args))


def _stored(plan):
    data = json.loads(plan["state"])
    return _clean(list(data["targets"].items()), data["choices"])


@bp.get("/<int:plan_id>")
def show(plan_id):
    plan = _plan_or_404(plan_id)
    return _render(*(_from_request(request.args) if "item" in request.args else _stored(plan)), plan=plan)


def _posted():
    try:
        state = json.loads(request.form.get("state") or "{}")
    except ValueError:
        abort(400, "Ungültiger Plan.")
    if not isinstance(state, dict):
        abort(400, "Ungültiger Plan.")
    targets, choices = state.get("targets"), state.get("choices")
    if not isinstance(targets, dict) or not isinstance(choices, dict):
        abort(400, "Ungültiger Plan.")
    return _clean(list(targets.items()), choices)


def _plan_steps(plan):
    try:
        return solve(*_stored(plan))["steps"]
    except SolveError:
        return []


@bp.post("/<int:plan_id>/step")
def step(plan_id):
    """Schritt abhaken (done=1/0) oder zuteilen (assignee_id). Feste Werte statt Umschalten, damit veraltete Seiten nichts verdrehen."""
    plan = _plan_or_404(plan_id)
    recipe = request.form.get("recipe", "")
    steps = [] if plan["deleted_at"] else _plan_steps(plan)
    if not any(s["recipe"] == recipe for s in steps):
        abort(409, "Der Plan wurde geändert. Lade die Seite neu.")
    db = get_db()
    db.execute("INSERT OR IGNORE INTO plan_steps (plan_id, recipe) VALUES (?, ?)", (plan_id, recipe))
    if "assignee_id" in request.form:
        assignee = {str(u["id"]): u["id"] for u in _users()}.get(request.form["assignee_id"])
        db.execute("UPDATE plan_steps SET assignee_id=? WHERE plan_id=? AND recipe=?", (assignee, plan_id, recipe))
    done = request.form.get("done")
    if done == "1" and not _progress(plan_id, steps)[recipe]["done"]:
        count = next(s["count"] for s in steps if s["recipe"] == recipe)
        db.execute("UPDATE plan_steps SET done_by_name=?, done_at=datetime('now'), done_count=? WHERE plan_id=? AND recipe=?",
                   (g.user["name"], count, plan_id, recipe))
    elif done == "0":
        db.execute("UPDATE plan_steps SET done_by_name=NULL, done_at=NULL, done_count=NULL WHERE plan_id=? AND recipe=?",
                   (plan_id, recipe))
    db.commit()
    if "application/json" not in request.headers.get("Accept", ""):
        return redirect(url_for("fabriken.show", plan_id=plan_id) + "#kette")
    progress = _progress(plan_id, steps)
    p = progress[recipe]
    return jsonify(done=p["done"], tag=p["tag"], finished=sum(x["done"] for x in progress.values()),
                   html=render_template("fabriken/_step.html", plan=plan, recipe=recipe, p=p))


@bp.post("/save")
def save():
    targets, choices = _posted()
    name = request.form.get("name", "").strip()[:120]
    if not name or not targets:
        flash("Der Plan braucht einen Namen und mindestens ein Ziel.")
        return redirect(url_for("fabriken.calc"))
    db = get_db()
    me = g.user
    cur = db.execute("INSERT INTO plans (name, state, created_by, created_by_name, updated_by_name) VALUES (?, ?, ?, ?, ?)",
                     (name, _state(targets, choices), me["id"], me["name"], me["name"]))
    _log(cur.lastrowid, "created", _summary(targets))
    db.commit()
    flash("Plan gespeichert.")
    return redirect(url_for("fabriken.show", plan_id=cur.lastrowid))


@bp.post("/<int:plan_id>/save")
def update(plan_id):
    plan = _plan_or_404(plan_id)
    targets, choices = _posted()
    name = request.form.get("name", "").strip()[:120]
    if plan["deleted_at"] or not name or not targets:
        flash("Der Plan braucht einen Namen und mindestens ein Ziel.")
        return redirect(url_for("fabriken.show", plan_id=plan_id))
    db = get_db()
    db.execute("UPDATE plans SET name=?, state=?, updated_by_name=?, updated_at=datetime('now') WHERE id=?",
               (name, _state(targets, choices), g.user["name"], plan_id))
    _log(plan_id, "updated", _summary(targets))
    db.commit()
    flash("Plan gespeichert.")
    return redirect(url_for("fabriken.show", plan_id=plan_id))


@bp.post("/<int:plan_id>/delete")
def delete(plan_id):
    plan = _plan_or_404(plan_id)
    if not _may_delete(plan):
        abort(403)
    if not plan["deleted_at"]:
        db = get_db()
        db.execute("UPDATE plans SET deleted_at=datetime('now'), deleted_by_name=? WHERE id=?", (g.user["name"], plan_id))
        _log(plan_id, "deleted")
        db.commit()
        flash("Plan gelöscht. Unter „Gelöscht“ kannst du ihn zurückholen.")
    return redirect(url_for("fabriken.index"))


@bp.post("/<int:plan_id>/restore")
def restore(plan_id):
    plan = _plan_or_404(plan_id)
    if not _may_delete(plan):
        abort(403)
    if plan["deleted_at"]:
        db = get_db()
        db.execute("UPDATE plans SET deleted_at=NULL, deleted_by_name=NULL WHERE id=?", (plan_id,))
        _log(plan_id, "restored")
        db.commit()
        flash("Plan wiederhergestellt.")
    return redirect(url_for("fabriken.show", plan_id=plan_id))
