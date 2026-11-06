"""Karte der Spielwelt mit eigener Seite im Menü."""
from flask import Blueprint

from ...core import Module

bp = Blueprint("karte", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

# Zeichnungen auf der Karte (Planung). Punkte in Spielkoordinaten (cm), flach: [x, y, x, y, ...]
SCHEMA = """
CREATE TABLE IF NOT EXISTS karte_marks (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('pen', 'line', 'rect', 'pin')),
    color      TEXT NOT NULL,
    width      REAL NOT NULL DEFAULT 3,
    points     TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

module = Module(name="karte", label="Karte", icon="fa-map", order=30, blueprint=bp, schema=SCHEMA,
                description="Spielstand hochladen, die Welt ansehen und gemeinsam darauf planen.")
