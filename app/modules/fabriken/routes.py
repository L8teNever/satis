import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import abort, flash, g, redirect, render_template, request, url_for

from ...core import get_db
from . import bp
from .solver import EXTERNAL, ITEMS, RECIPES, SolveError, default_recipe, recipes_for, solve

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


def _render(targets, choices, plan=None):
    result, error = None, None
    if targets:
        try:
            result = solve(targets, choices)
        except SolveError as exc:
            error = str(exc)
    log = []
    if plan:
        log = get_db().execute("SELECT * FROM plan_log WHERE plan_id = ? ORDER BY id DESC", (plan["id"],)).fetchall()
    return render_template(
        "fabriken/calc.html", targets=targets, choices=choices, result=result, error=error, plan=plan, log=log,
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
