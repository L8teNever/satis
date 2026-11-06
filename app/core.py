"""Kern: Modul-Registry, Datenbank, Auth (Cloudflare Access), CSRF.

Neue Funktion = neues Paket in app/modules/<name>/ mit einer Variable `module`.
Mehr braucht es nicht (siehe README).
"""
import os
import secrets
import sqlite3
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path

from flask import abort, current_app, g, request, session


# --------------------------------------------------------------------------- Module
@dataclass
class Module:
    name: str                      # URL-Präfix + interner Name, z. B. "tasks"
    label: str                     # Anzeige im Menü
    blueprint: object              # Flask-Blueprint
    icon: str = "fa-cube"          # Font-Awesome-Klasse (Solid, Free)
    order: int = 100               # Sortierung im Menü
    admin_only: bool = False       # nur für Admins sichtbar/nutzbar
    schema: str = ""               # SQL (CREATE TABLE IF NOT EXISTS ...)
    description: str = ""          # Text auf der Startseite
    show_in_nav: bool = True

    @property
    def endpoint(self) -> str:
        """Startseite des Moduls – jedes Modul braucht eine View `index`."""
        return f"{self.blueprint.name}.index"


MODULES: list[Module] = []


# --------------------------------------------------------------------------- DB
def data_dir() -> Path:
    p = Path(os.environ.get("DATA_DIR", "./data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        con = sqlite3.connect(data_dir() / "satis.db")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        g.db = con
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin','user')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db():
    con = sqlite3.connect(data_dir() / "satis.db")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(CORE_SCHEMA)
    for m in MODULES:
        if m.schema:
            con.executescript(m.schema)
    con.commit()
    con.close()


# --------------------------------------------------------------------------- Auth
_jwk_client = None


def _email_from_jwt(token: str, team: str, aud: str) -> str | None:
    """Prüft das Cloudflare-Access-JWT (Signatur, Audience, Issuer)."""
    global _jwk_client
    import jwt  # PyJWT
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(f"https://{team}/cdn-cgi/access/certs", cache_keys=True)
    try:
        key = _jwk_client.get_signing_key_from_jwt(token).key
        payload = jwt.decode(token, key, algorithms=["RS256"], audience=aud, issuer=f"https://{team}")
    except Exception as exc:  # ungültig / abgelaufen / Netzwerkfehler
        current_app.logger.warning("Access-JWT abgelehnt: %s", exc)
        return None
    return payload.get("email")


def identity_email() -> str | None:
    team = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip().removeprefix("https://").rstrip("/")
    aud = os.environ.get("CF_ACCESS_AUD", "").strip()
    if team and aud:
        token = request.headers.get("Cf-Access-Jwt-Assertion")
        return _email_from_jwt(token, team, aud) if token else None
    # Ohne JWT-Prüfung: Header vertrauen (nur ok, wenn der Container NUR über den Tunnel erreichbar ist)
    email = request.headers.get("Cf-Access-Authenticated-User-Email") or os.environ.get("DEV_EMAIL")
    return email.strip() if email else None


def resolve_user():
    """Aktuellen Nutzer anhand der Cloudflare-Identität bestimmen.

    Der allererste Login (leere Nutzertabelle) wird atomar zum Admin.
    Alle anderen müssen vorher vom Admin angelegt worden sein.
    """
    email = identity_email()
    if not email:
        return None, "no-identity"
    db = get_db()
    find = "SELECT * FROM users WHERE email = ?"
    user = db.execute(find, (email,)).fetchone()
    if user is None:  # nur dann schreiben, nicht bei jedem Seitenaufruf
        db.execute(
            "INSERT INTO users (email, name, role) "
            "SELECT ?, ?, 'admin' WHERE NOT EXISTS (SELECT 1 FROM users)",
            (email.lower(), email.split("@")[0]),
        )
        db.commit()
        user = db.execute(find, (email,)).fetchone()
    return user, ("ok" if user else "unknown")


def admin_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not g.user or g.user["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    return wrapper


# --------------------------------------------------------------------------- CSRF
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        if not sent or not secrets.compare_digest(sent.encode(), session.get("csrf", "").encode()):
            abort(400, "CSRF-Token ungültig – Seite neu laden.")
