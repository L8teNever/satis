from flask import Blueprint

from ...core import Module

bp = Blueprint("notizen", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401  (registriert die Routen am Blueprint)

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    owner_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',
    pinned     INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notes_owner ON notes(owner_id);
CREATE TABLE IF NOT EXISTS note_shares (
    note_id  INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    can_edit INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (note_id, user_id)
);
"""

module = Module(
    name="notizen",
    label="Notizen",
    icon="fa-sticky-note",
    order=15,
    blueprint=bp,
    schema=SCHEMA,
    description="Eigene Notiz-Blöcke mit eingebautem Rechner, bei Bedarf für andere freigeben.",
)
