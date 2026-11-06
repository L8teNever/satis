from flask import Blueprint

from ...core import Module

bp = Blueprint("tasks", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','doing','done')),
    priority    INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    due         TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id);
"""

module = Module(
    name="tasks",
    label="Aufgaben",
    icon="☑",
    order=10,
    blueprint=bp,
    schema=SCHEMA,
    description="Aufgaben anlegen und Leuten zuteilen.",
)
