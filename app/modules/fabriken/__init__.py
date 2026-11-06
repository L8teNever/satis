from flask import Blueprint

from ...core import Module

bp = Blueprint("fabriken", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    state           TEXT NOT NULL,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_by_name TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by_name TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_by_name TEXT,
    deleted_at      TEXT
);
CREATE TABLE IF NOT EXISTS plan_log (
    id        INTEGER PRIMARY KEY,
    plan_id   INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    action    TEXT NOT NULL CHECK (action IN ('created','updated','deleted','restored')),
    detail    TEXT NOT NULL DEFAULT '',
    at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plan_log_plan ON plan_log(plan_id);
CREATE TABLE IF NOT EXISTS plan_steps (
    plan_id      INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    recipe       TEXT NOT NULL,
    assignee_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    done_by_name TEXT,
    done_at      TEXT,
    done_count   REAL,
    PRIMARY KEY (plan_id, recipe)
);
"""

module = Module(
    name="fabriken",
    label="Fabriken",
    icon="fa-industry",
    order=20,
    blueprint=bp,
    schema=SCHEMA,
    description="Produktion berechnen und als Plan speichern.",
)
