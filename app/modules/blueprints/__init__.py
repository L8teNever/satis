from flask import Blueprint

from ...core import Module

bp = Blueprint("blueprints", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

SCHEMA = """
CREATE TABLE IF NOT EXISTS blueprints (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    has_cfg     INTEGER NOT NULL DEFAULT 0,
    size        INTEGER NOT NULL DEFAULT 0,
    sha         TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

module = Module(
    name="blueprints",
    label="Blueprints",
    icon="fa-drafting-compass",
    order=25,
    blueprint=bp,
    schema=SCHEMA,
    description="Blueprints teilen. Das Sync-Skript holt sie direkt in den Spielordner.",
)
