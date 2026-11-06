"""Start: pip install -r requirements.txt pytest && python -m pytest"""
import re

import pytest

from app import create_app

ADMIN = {"Cf-Access-Authenticated-User-Email": "Simon@example.com"}
FRIEND = {"Cf-Access-Authenticated-User-Email": "freund@example.com"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INSECURE_COOKIES", "1")
    for var in ("CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "DEV_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    return create_app().test_client()


def post(client, url, headers, page, **data):
    html = client.get(page, headers=headers).text
    data["csrf_token"] = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    return client.post(url, data=data, headers=headers, follow_redirects=True)


def add_friend(client):
    client.get("/", headers=ADMIN)
    return post(client, "/admin/add", ADMIN, "/admin/", name="Freund", email="freund@example.com", role="user")


def test_no_identity_is_denied(client):
    assert client.get("/").status_code == 403


def test_pages_have_no_footer(client):
    assert "<footer" not in client.get("/", headers=ADMIN).text


def test_healthz_needs_no_login(client):
    assert client.get("/healthz").text == "ok"


def test_first_login_becomes_admin_others_are_denied(client):
    assert client.get("/admin/", headers=ADMIN).status_code == 200
    denied = client.get("/", headers=FRIEND)
    assert denied.status_code == 403
    assert "freund@example.com" in denied.text


def test_added_user_logs_in_without_admin_rights(client):
    assert "Freund angelegt" in add_friend(client).text
    assert client.get("/tasks/", headers=FRIEND).status_code == 200
    assert client.get("/admin/", headers=FRIEND).status_code == 403
    assert "Nutzer" not in client.get("/", headers=FRIEND).text


def test_post_without_csrf_is_rejected(client):
    assert client.post("/tasks/new", data={"title": "x"}, headers=ADMIN).status_code == 400


def test_assign_task_and_filter(client):
    add_friend(client)
    post(client, "/tasks/new", ADMIN, "/tasks/new", title="Kohle ausbauen", assignee_id="2", priority="3",
         status="open", due="2026-12-01")
    post(client, "/tasks/new", ADMIN, "/tasks/new", title="Eisen", assignee_id="", priority="2", status="open")
    mine = client.get("/tasks/?who=me", headers=FRIEND).text
    assert "Kohle ausbauen" in mine and "Eisen" not in mine


def test_bad_task_input_does_not_crash(client):
    client.get("/", headers=ADMIN)
    r = post(client, "/tasks/new", ADMIN, "/tasks/new", title="x", assignee_id="999", due="kaputt")
    assert r.status_code == 200 and "Niemand zugeteilt" in r.text
    assert client.get("/tasks/?who=99999999999999999999999", headers=ADMIN).status_code == 200


def test_only_creator_or_admin_can_delete(client):
    add_friend(client)
    post(client, "/tasks/new", ADMIN, "/tasks/new", title="Admin-Aufgabe")
    r = post(client, "/tasks/1/delete", FRIEND, "/tasks/new", )
    assert r.status_code == 403


def test_admin_cannot_remove_himself(client):
    client.get("/", headers=ADMIN)
    r = post(client, "/admin/1/delete", ADMIN, "/admin/")
    assert r.status_code == 400


def test_live_counter_goes_up_on_changes(client):
    client.get("/", headers=ADMIN)
    before = client.get("/live", headers=ADMIN).get_json()["rev"]
    assert client.get("/tasks/", headers=ADMIN).status_code == 200
    assert client.get("/live", headers=ADMIN).get_json()["rev"] == before  # Ansehen ändert nichts
    add_friend(client)
    after = client.get("/live", headers=ADMIN).get_json()["rev"]
    assert after > before
    assert f'data-live-rev="{after}"' in client.get("/", headers=ADMIN).text


def test_failed_change_does_not_count(client):
    client.get("/", headers=ADMIN)
    before = client.get("/live", headers=ADMIN).get_json()["rev"]
    client.post("/admin/add", data={"name": "x"}, headers=ADMIN)  # ohne CSRF-Token
    assert client.get("/live", headers=ADMIN).get_json()["rev"] == before


def test_live_needs_login(client):
    assert client.get("/live").status_code == 403


def test_pages_are_built_for_switching_without_reload(client):
    # satis.js tauscht beim Seitenwechsel diese Teile einzeln und lädt bei neuer Asset-Version einmal richtig
    for page in ("/", "/tasks/", "/fabriken/rechner"):
        html = client.get(page, headers=ADMIN).text
        for name in ("header", "crumbs", "flash", "content"):
            assert f'data-part="{name}"' in html, (page, name)
        assert 'name="satis-assets" content="' in html
        assert "this.form.submit()" not in html  # das würde am Seitenwechsel vorbei neu laden
