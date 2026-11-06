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
app/modules/zuege/
├── __init__.py
├── routes.py
└── templates/fabriken/index.html
```

```python
# __init__.py
from flask import Blueprint
from ...core import Module

bp = Blueprint("zuege", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401

module = Module(
    name="zuege",               # URL: /zuege/
    label="Züge",
    icon="fa-train",           # Font-Awesome-Klasse (Solid, Free)
    order=20,                  # Position im Menü
    blueprint=bp,
    schema="CREATE TABLE IF NOT EXISTS zuege (id INTEGER PRIMARY KEY, name TEXT NOT NULL);",
    description="Text für die Übersicht.",
)
```

Jedes Modul braucht eine View `index` (`@bp.get("/")`). Templates erben von `base.html`, jedes
POST-Formular braucht `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
Datenbankzugriff läuft über `core.get_db()`, der aktuelle Nutzer steht in `g.user`.
`schema` legt nur neue Tabellen an. Spalten in bestehenden Tabellen müssen per `ALTER TABLE` ergänzt werden.

## Fabriken-Rechner

`app/modules/fabriken/solver.py` rechnet aus Zielen pro Minute die Rezepte, Gebäude, Rohstoffe und den Strom. Pläne werden nie
wirklich gelöscht, `plan_log` hält fest, wer wann was gemacht hat.

Die Spieldaten in `data.json` kommen aus [SatisfactoryTools](https://github.com/greeny/SatisfactoryTools) (MIT, Stand Spielversion 1.0).
Neu bauen mit `python tools/build_fabriken_data.py <data.json> app/modules/fabriken/data.json`. Item-Bilder gehören Coffee Stain und sind nicht enthalten.

## Aussehen

Der Style entspricht satisfactory-calculator.com: Bootswatch Darkly auf Bootstrap 4.5, Lato, Icons von Font Awesome.
Alles liegt lokal unter `app/static/`, zur Laufzeit wird nichts von fremden Servern geladen.

- `vendor/bootstrap-darkly.min.css`: Darkly mit den Werten des Calculators (Basis 1rem, Links `#F39C12`). Nicht von Hand ändern.
- `satis.css`: die wenigen eigenen Ergänzungen.
- `satis.js`: macht aus jedem `<select>` ein Dropdown, aus `<input type="date">` einen Kalender und zeigt bei `<form data-confirm="Text">` einen Dialog. Neue Module schreiben einfach normale Formularfelder. Mit `<option data-icon="fa-...">` bekommt ein Eintrag ein Icon.
- `icon` eines Moduls ist eine Font-Awesome-Klasse aus dem Solid-Set der Free-Version 5.15, z. B. `fa-industry`. Pro-Icons gibt es nicht.

Lizenzen: Bootstrap, Bootswatch, jQuery, Cytoscape, dagre MIT; Font Awesome Free CC BY 4.0 / OFL / MIT; Lato OFL.

## Lokal entwickeln

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest
DEV_EMAIL=du@example.com INSECURE_COOKIES=1 flask --app app:create_app run --debug
```
