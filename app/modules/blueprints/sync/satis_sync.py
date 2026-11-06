#!/usr/bin/env python3
"""Satis-Sync: läuft auf deinem PC neben Satisfactory.

- Neue oder geänderte Blueprints von der Satis-Seite landen direkt im Blueprint-Ordner des Spiels.
- Dein neuester Spielstand geht automatisch für die Karte auf den Server.

Starten:   python satis_sync.py           (läuft weiter, bis du es mit Strg+C beendest)
           python satis_sync.py liste     (zeigt, welche Blueprints auf dem Server liegen)
           python satis_sync.py einmal    (ein Durchlauf, dann Ende)

Beim ersten Start fragt es nach dem Sync-Schlüssel (Blueprint-Seite → „Sync-Schlüssel erstellen“)
und legt daneben satis_sync.ini an. Nur Python 3, keine weiteren Pakete nötig.
"""
import configparser
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
INI = HERE / "satis_sync.ini"
STATE = HERE / "satis_sync_state.json"
DEFAULT_URL = "__SATIS_URL__"
BAD = '<>:"/\\|?*'


# --------------------------------------------------------------------------- Einstellungen
def default_savegames():
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FactoryGame" / "Saved" / "SaveGames"
    # Linux mit Steam/Proton
    return Path.home() / ".steam/steam/steamapps/compatdata/526870/pfx/drive_c/users/steamuser/AppData/Local/FactoryGame/Saved/SaveGames"


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(INI, encoding="utf-8")
    if not cfg.has_section("satis"):
        cfg.add_section("satis")
    s = cfg["satis"]
    changed = False
    if not s.get("url"):
        s["url"] = DEFAULT_URL if not DEFAULT_URL.startswith("__") else input("Adresse der Satis-Seite: ").strip()
        changed = True
    if not s.get("token"):
        print("Erstell auf der Blueprint-Seite einen Sync-Schlüssel und füg ihn hier ein.")
        s["token"] = input("Sync-Schlüssel: ").strip()
        changed = True
    if "cf_client_id" not in s:
        print("Cloudflare-Service-Token (bekommst du von Simon, leer lassen falls keins nötig):")
        s["cf_client_id"] = input("  Client-ID: ").strip()
        s["cf_client_secret"] = input("  Client-Secret: ").strip() if s["cf_client_id"] else ""
        changed = True
    s.setdefault("savegames", str(default_savegames()))
    s.setdefault("sessions", "")         # leer = alle Blueprint-Ordner, sonst z. B. "MeineWelt, Zweite"
    s.setdefault("interval", "30")       # Sekunden zwischen zwei Durchläufen
    s.setdefault("save_every_min", "5")  # höchstens so oft einen Spielstand hochladen
    s.setdefault("upload_saves", "ja")
    if changed or not INI.exists():
        with open(INI, "w", encoding="utf-8") as f:
            cfg.write(f)
        print(f"Gespeichert in {INI}")
    return s


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE)


# --------------------------------------------------------------------------- Server
class Server:
    def __init__(self, s):
        self.base = s["url"].rstrip("/")
        self.headers = {"X-Satis-Token": s["token"], "User-Agent": "satis-sync/1"}
        if s.get("cf_client_id"):
            self.headers["CF-Access-Client-Id"] = s["cf_client_id"]
            self.headers["CF-Access-Client-Secret"] = s.get("cf_client_secret", "")

    def request(self, path, data=None, headers=None, timeout=60):
        req = urllib.request.Request(self.base + path, data=data, headers={**self.headers, **(headers or {})})
        try:
            res = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                msg = json.loads(body).get("error")
            except ValueError:
                msg = None
            raise SyncError(exc.code, msg or f"Server meldet Fehler {exc.code}") from None
        with res:
            if "cloudflareaccess.com" in res.geturl():
                raise SyncError(401, "Cloudflare lässt das Skript nicht durch. Trag in satis_sync.ini ein "
                                     "gültiges Service-Token ein (cf_client_id / cf_client_secret).")
            return res.read()

    def json(self, path):
        return json.loads(self.request(path))

    def upload(self, path, field, file):
        """Datei als multipart/form-data hochladen."""
        boundary = uuid.uuid4().hex
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{file.name}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode()
        body = head + file.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return self.request(path, data=body, timeout=600,
                            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


class SyncError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# --------------------------------------------------------------------------- Blueprints
def blueprint_dirs(s):
    root = Path(s["savegames"]) / "blueprints"
    wanted = [x.strip() for x in s["sessions"].split(",") if x.strip()]
    if wanted:
        dirs = [root / w for w in wanted]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        return dirs
    return sorted(d for d in root.iterdir() if d.is_dir()) if root.is_dir() else []


def safe(name):
    return "".join("_" if c in BAD else c for c in name).strip(" .") or "Blueprint"


def file_sha(sbp, cfg):
    return hashlib.sha256(sbp.read_bytes() + b"\0" + (cfg.read_bytes() if cfg.exists() else b"")).hexdigest()


def write(path, data):
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as f:
        f.write(data)
    os.replace(f.name, path)


def sync_blueprints(server, s, state, warned):
    dirs = blueprint_dirs(s)
    if not dirs:
        if "nodir" not in warned:
            log(f"Kein Blueprint-Ordner unter {Path(s['savegames']) / 'blueprints'}. Öffne im Spiel einmal den "
                "Blueprint-Designer oder trag in satis_sync.ini bei sessions den Namen deiner Session ein.")
            warned.add("nodir")
        return
    known = state.setdefault("blueprints", {})
    for bp in server.json("/blueprints/api/list")["blueprints"]:
        name = safe(bp["name"])
        for d in dirs:
            key = f"{d.name}/{name}"
            sbp, cfg = d / f"{name}.sbp", d / f"{name}.sbpcfg"
            if known.get(key) == bp["sha"] and sbp.exists():
                continue
            if sbp.exists() and key not in known:
                if file_sha(sbp, cfg) == bp["sha"]:  # liegt schon genau so da
                    known[key] = bp["sha"]
                    continue
                if key not in warned:  # eigene Blueprint mit gleichem Namen: nicht überschreiben
                    log(f"„{name}“ gibt es in {d.name} schon in einer anderen Version, ich lasse deine stehen.")
                    warned.add(key)
                continue
            if sbp.exists() and known.get(key) and file_sha(sbp, cfg) != known[key]:
                if key not in warned:  # selbst im Spiel geändert: auch nicht überschreiben
                    log(f"„{name}“ hast du in {d.name} selbst geändert, die neue Version vom Server lasse ich weg.")
                    warned.add(key)
                continue
            data = server.request(bp["files"]["sbp"])
            extra = server.request(bp["files"]["sbpcfg"]) if "sbpcfg" in bp["files"] else None
            write(sbp, data)
            if extra is not None:
                write(cfg, extra)
            known[key] = bp["sha"]
            save_state(state)
            log(f"Blueprint „{name}“ von {bp.get('by') or '?'} → {d.name}")


def print_list(server):
    rows = server.json("/blueprints/api/list")["blueprints"]
    if not rows:
        print("Auf dem Server liegen noch keine Blueprints.")
    for bp in rows:
        print(f"- {bp['name']}  (von {bp.get('by') or '?'}, {bp['updated']})")


# --------------------------------------------------------------------------- Spielstand
def newest_save(s):
    root = Path(s["savegames"])
    if not root.is_dir():
        return None
    saves = [p for p in root.rglob("*.sav") if "blueprints" not in p.parts]
    return max(saves, key=lambda p: p.stat().st_mtime, default=None)


def sync_save(server, s, state):
    if s.get("upload_saves", "ja").lower() in ("nein", "no", "0", "false"):
        return
    sav = newest_save(s)
    if not sav:
        return
    mtime = sav.stat().st_mtime
    last = state.get("save", {})
    if last.get("path") == str(sav) and last.get("mtime") == mtime:
        return
    if time.time() - mtime < 10:  # das Spiel schreibt vielleicht noch
        return
    if time.time() - last.get("at", 0) < float(s["save_every_min"]) * 60:
        return
    try:
        server.upload("/karte/upload", "save", sav)
    except SyncError as exc:
        if exc.code == 409:  # der Server liest gerade noch einen ein
            return
        raise
    state["save"] = {"path": str(sav), "mtime": mtime, "at": time.time()}
    save_state(state)
    log(f"Spielstand {sav.name} hochgeladen, die Karte aktualisiert sich gleich.")


# --------------------------------------------------------------------------- Start
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    s = load_config()
    server = Server(s)
    if mode == "liste":
        print_list(server)
        return
    state, warned = load_state(), set()
    log(f"Satis-Sync läuft mit {server.base}. Beenden mit Strg+C.")
    log(f"Spielstände: {s['savegames']}")
    while True:
        for step in (lambda: sync_blueprints(server, s, state, warned), lambda: sync_save(server, s, state)):
            try:
                step()
            except SyncError as exc:
                log(f"Fehler: {exc}")
                if exc.code == 401:
                    return
            except (OSError, ValueError) as exc:  # Netz weg, Server startet neu …
                log(f"Gerade nicht erreichbar ({exc}), ich versuche es gleich wieder.")
        if mode == "einmal":
            return
        time.sleep(max(5, float(s["interval"])))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
