# Satis

Planungsseite für unsere Satisfactory-Welt. Läuft als ein Docker-Container (Python/Flask, SQLite),
Login komplett über Cloudflare Tunnel + Zero Trust Access. Eigene Passwörter gibt es nicht.

- Die E-Mail kommt von Cloudflare. Wer sich als **Erstes** anmeldet, wird automatisch **Admin**.
- Alle anderen legt der Admin unter **Nutzer** mit Name und E-Mail an. Danach sind sie direkt eingeloggt.
- Unter **Aufgaben** lassen sich Aufgaben anlegen, Leuten zuteilen und filtern.

## Starten

Es wird nur die `docker-compose.yml` gebraucht, das Image baut Docker direkt aus diesem Repo.

```bash
docker compose up -d --build
# Update auf den neuesten Stand von main:
docker compose build --pull --no-cache && docker compose up -d
```

Daten liegen im Volume `satis-data` (`/data/satis.db`). Einstellungen stehen in einer `.env` neben der Compose-Datei:

| Variable | Bedeutung |
| --- | --- |
| `CF_ACCESS_TEAM_DOMAIN` | z. B. `deinteam.cloudflareaccess.com` |
| `CF_ACCESS_AUD` | AUD-Tag der Access-Anwendung |
| `PORT` | Port auf dem Host, Standard `8000` |

## Cloudflare einrichten

1. **Tunnel:** Public Hostname anlegen, Service `http://localhost:8000`
   (läuft cloudflared als Container im selben Netzwerk: `http://satis:8000`).
2. **Access:** Self-hosted Application für denselben Hostname, Policy mit den erlaubten E-Mails.
3. Team-Domain und AUD-Tag in die `.env` eintragen und den Container neu starten.

**Wichtig:** Melde dich als Erstes selbst an, sonst wird jemand anderes Admin. Neue Leute müssen
zweimal eingetragen werden: in der Access-Policy und in der App unter **Nutzer**.

Ohne `CF_ACCESS_*` vertraut die App dem Header `Cf-Access-Authenticated-User-Email`. Das ist nur
sicher, solange der Port nicht von außen erreichbar ist. Mit beiden Werten wird das signierte JWT geprüft.

## Neue Funktion hinzufügen

Eine Funktion ist ein Paket in `app/modules/`. Es wird beim Start automatisch gefunden, erscheint
im Menü und auf der Übersicht. Am Kern muss nichts geändert werden.

```
app/modules/fabriken/
├── __init__.py
├── routes.py
└── templates/fabriken/index.html
```

```python
# __init__.py
from flask import Blueprint
from ...core import Module

bp = Blueprint("fabriken", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401

module = Module(
    name="fabriken",           # URL: /fabriken/
    label="Fabriken",
    icon="▤",
    order=20,                  # Position im Menü
    blueprint=bp,
    schema="CREATE TABLE IF NOT EXISTS fabriken (id INTEGER PRIMARY KEY, name TEXT NOT NULL);",
    description="Text für die Übersicht.",
)
```

Jedes Modul braucht eine View `index` (`@bp.get("/")`). Templates erben von `base.html`, jedes
POST-Formular braucht `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
Datenbankzugriff läuft über `core.get_db()`, der aktuelle Nutzer steht in `g.user`.
`schema` legt nur neue Tabellen an. Spalten in bestehenden Tabellen müssen per `ALTER TABLE` ergänzt werden.

## Lokal entwickeln

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest
DEV_EMAIL=du@example.com INSECURE_COOKIES=1 flask --app app:create_app run --debug
```
