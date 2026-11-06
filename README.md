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

### Live-Aktualisierung

Ändert jemand etwas, sehen es alle anderen ohne Neuladen. Jede geglückte POST-Anfrage zählt in der Tabelle `live`
einen Zähler hoch. Offene Seiten fragen `/live` alle 4 Sekunden ab, aber nur solange sie sichtbar sind. Bei einem neuen
Stand holen sie die Seite still neu und tauschen jeden Bereich mit `data-live="name"`, dessen HTML sich geändert hat.

- **Neue Module:** Mehr braucht es nicht. `base.html` legt den ganzen Inhalt in einen Bereich `content`.
- **Eigene Bereiche:** `{% block live %}{% endblock %}` schaltet den Gesamtbereich ab, dann einzelne Elemente mit `data-live` markieren (siehe `calc.html`).
- **Skripte:** Nach dem Tausch läuft `satisEnhance` für den Bereich, danach kommt das Ereignis `satis:load` (siehe unten). Für einen Sondertausch gibt es `satisLive.swap[name] = (alt, neu) => true`, das nutzt der Graph.
- **Schutz:** Wer in einem Bereich tippt oder ein Menü offen hat, behält ihn, bis er fertig ist.
- **Hintergrund-Arbeit:** Läuft etwas außerhalb einer Anfrage, ruft man am Ende `core.bump_live()` auf, wie beim Spielstand.

### Seitenwechsel ohne Neuladen

Links und Formulare laden nicht die ganze Seite neu. `satis.js` holt die neue Seite im Hintergrund und tauscht nur, was
anders ist: Kopf (`data-part="header"`), Brotkrumen, Meldungen und Inhalt einzeln. Bleibt man auf derselben Seite und das
Gerüst ohne die `data-live`-Bereiche ist gleich, werden nur die geänderten Bereiche getauscht. Im Rechner bleibt
Zoom und offener Tab dadurch stehen. Dauert es länger als einen Moment, laufen oben ein Ladebalken und der Inhalt wird
leicht abgedunkelt. Zeigt die Maus oder der Finger auf einen Link, wird die Seite schon vorgeladen.

- **Seitenskripte:** Ein Skript im Block `scripts` wird nur einmal geladen, auch wenn man die Seite mehrmals öffnet.
  Es startet darum nicht selbst, sondern hört auf `satis:load` (neue Inhalte, `event.target` ist der Bereich) und räumt bei
  `satis:unload` auf. Klicks am `document` anhängen. Inline-Skripte im Inhalt laufen nach einem Wechsel nicht.
- **Formulare:** Normal mit `method` und `action` schreiben. Zum Absenden aus Skripten `form.requestSubmit()` nehmen,
  `form.submit()` geht am Wechsel vorbei.
- **Ausnahmen:** `data-no-nav` an Link oder Formular lädt ganz normal. Links mit `target`, `download` oder nach `/cdn-cgi/` sowieso.
- **Updates:** `<meta name="satis-assets">` enthält eine Prüfsumme über `static/*.js` und `*.css`. Passt sie nicht mehr,
  lädt der nächste Wechsel die Seite einmal ganz.
- **Notfall:** Klappt der Abruf nicht (z. B. Cloudflare-Login abgelaufen), lädt der Browser ganz normal.

## Karte

Die Karte hat eine eigene Seite im Menü (`/karte/`). Dort lädt man einen Spielstand hoch, `extract/extract.mjs` liest ihn im Hintergrund aus und
`app/modules/karte/layers.py` macht daraus die Ebenen. Eine neue Ebene ist ein Eintrag in `LAYERS` und eine Regel in `RULES`.
Das Kartenbild gehört Coffee Stain und ist nicht im Repo. Ohne `/data/karte/map.jpg` bleibt der Hintergrund einfarbig.

## Fabriken-Rechner

`app/modules/fabriken/solver.py` rechnet aus Zielen pro Minute die Rezepte, Gebäude, Rohstoffe und den Strom. Pläne werden nie
wirklich gelöscht, `plan_log` hält fest, wer wann was gemacht hat.

In gespeicherten Plänen lassen sich Schritte abhaken und Leuten zuteilen (`plan_steps`, ein Eintrag pro Plan und Rezept). Wird ein Plan
größer, gilt ein abgehakter Schritt wieder als offen, bis die neue Menge abgehakt ist. Bei einem anderen Rezept beginnt der Schritt neu.

Die Spieldaten in `data.json` kommen aus [SatisfactoryTools](https://github.com/greeny/SatisfactoryTools) (MIT, Stand Spielversion 1.0).
Neu bauen mit `python tools/build_fabriken_data.py <data.json> app/modules/fabriken/data.json`. Item-Bilder gehören Coffee Stain und sind nicht enthalten.

## Notizen

Jeder hat eigene Notiz-Blöcke unter `/notizen/`. Sie speichern sich beim Tippen von selbst. Wer am Zeilenende eine Rechnung mit `=` abschließt (z. B. `4*5=`), bekommt das Ergebnis direkt dahinter (`+ - * / ^ %`, Klammern, Komma oder Punkt). Notizen lassen sich anheften, verschieben, mit einer Kategorie versehen und sortieren. Über „Freigeben“ bekommen andere Nutzer Lese- oder Schreibzugriff.

## Blueprints und Sync-Skript

Unter `/blueprints/` lädt jeder `.sbp` (+ `.sbpcfg`) hoch, gleicher Name ersetzt die alte Version.
Unter `/blueprints/sync` stehen Anleitung und Download: Dort stellt man den Pfad ein und bekommt das Skript fertig mit Server, Pfad und eigenem Schlüssel. Ein Admin trägt dort einmal das Cloudflare-Service-Token ein, das dann in jedem Download steckt.
Das Skript `satis_sync.py` (nur Python 3) läuft auf dem eigenen PC: Es holt neue Blueprints in
`%LOCALAPPDATA%\FactoryGame\Saved\SaveGames\blueprints\<Session>` und lädt den neuesten Spielstand für die Karte hoch.
Es meldet sich mit einem Sync-Schlüssel (`X-Satis-Token`, auf der Seite erstellen) an, der nur für `blueprints` und
`karte` gilt. Damit Cloudflare Access das Skript durchlässt, braucht es ein Service-Token
(`CF-Access-Client-Id`/`-Secret` in `satis_sync.ini`) und in der Access-App eine Regel „Service Auth“ dafür.

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
