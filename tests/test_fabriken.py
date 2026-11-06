import re

import pytest

from app import create_app
from app.modules.fabriken.solver import BY_ITEM, EXTERNAL, ITEMS, RECIPES, SolveError, default_recipe, solve

ADMIN = {"Cf-Access-Authenticated-User-Email": "Simon@example.com"}
FRIEND = {"Cf-Access-Authenticated-User-Email": "freund@example.com"}


def step(result, name):
    return next(s for s in result["steps"] if s["name"] == name)


def raw(result):
    return {r["item"]: r["rate"] for r in result["raw"]}


def test_iron_plate():
    r = solve({"Desc_IronPlate_C": 20})
    assert step(r, "Iron Plate")["count"] == pytest.approx(1)
    assert step(r, "Iron Ingot")["count"] == pytest.approx(1)
    assert raw(r) == {"Desc_OreIron_C": pytest.approx(30)}
    assert r["power"] == pytest.approx(8)


def test_plutonium_fuel_rod():
    r = solve({"Desc_PlutoniumFuelRod_C": 2})
    rod = step(r, "Plutonium Fuel Rod")
    assert rod["count"] == pytest.approx(8) and rod["building"] == "Manufacturer"
    assert raw(r)["Desc_NuclearWaste_C"] > 0  # Uranabfall kommt aus dem Kraftwerk und wird angeliefert


def test_liquids_use_cubic_meters():
    r = solve({"Desc_NitricAcid_C": 30})  # 1 Blender: 120 Stickstoff, 30 Wasser, 10 Eisenplatten pro Minute
    assert step(r, "Nitric Acid")["count"] == pytest.approx(1)
    assert raw(r)["Desc_NitrogenGas_C"] == pytest.approx(120)
    assert raw(r)["Desc_Water_C"] == pytest.approx(30)


def test_default_is_never_alternate_when_a_normal_recipe_exists():
    assert default_recipe("Desc_AluminumIngot_C") == "Recipe_IngotAluminum_C"
    for item in BY_ITEM:
        cls = default_recipe(item)
        if cls and RECIPES[cls]["alternate"]:
            assert all(RECIPES[c]["alternate"] or RECIPES[c]["out"][0][0] != item or RECIPES[c]["name"].startswith("Unpackage")
                       for c in BY_ITEM[item])


def test_byproduct_is_credited():
    plastic = solve({"Desc_Plastic_C": 20})
    assert any(s["item"] == "Desc_HeavyOilResidue_C" for s in plastic["surplus"])
    both = solve({"Desc_Plastic_C": 20, "Desc_HeavyOilResidue_C": 10})
    assert step(both, "Plastic")["count"] == pytest.approx(step(plastic, "Plastic")["count"])
    assert "Alternate: Heavy Oil Residue" not in [s["name"] for s in both["steps"]]


def test_alternate_and_external_choice():
    alt = solve({"Desc_IronIngot_C": 30}, {"Desc_IronIngot_C": "Recipe_Alternate_PureIronIngot_C"})
    assert "Desc_Water_C" in raw(alt)
    ext = solve({"Desc_IronPlate_C": 20}, {"Desc_IronIngot_C": EXTERNAL})
    assert raw(ext) == {"Desc_IronIngot_C": pytest.approx(30)}


def test_every_item_and_recipe_terminates():
    for item in BY_ITEM:
        if default_recipe(item):
            solve({item: 10})
        for cls in BY_ITEM[item]:
            try:
                result = solve({item: 10}, {item: cls})
            except SolveError:
                continue
            assert result["power"] >= 0 and all(s["count"] > 0 for s in result["steps"])


def test_balance_adds_up():
    for item in ("Desc_ComputerSuper_C", "Desc_NuclearFuelRod_C", "Desc_Fuel_C"):
        r = solve({item: 5})
        made = {}
        for s in r["steps"]:
            for x in s["outputs"]:
                made[x["item"]] = made.get(x["item"], 0) + x["rate"]
            for x in s["inputs"]:
                made[x["item"]] = made.get(x["item"], 0) - x["rate"]
        assert made[item] == pytest.approx(5 + sum(x["rate"] for x in r["surplus"] if x["item"] == item))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INSECURE_COOKIES", "1")
    for var in ("CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "DEV_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    c = create_app().test_client()
    c.get("/", headers=ADMIN)
    return c


def post(client, url, headers, **data):
    html = client.get("/tasks/new", headers=headers).text
    data["csrf_token"] = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    return client.post(url, data=data, headers=headers, follow_redirects=True)


STATE = '{"targets": {"Desc_IronPlate_C": 20}, "choices": {}}'


def test_calc_page_and_bad_input(client):
    r = client.get("/fabriken/rechner?item=Desc_IronPlate_C&rate=20", headers=ADMIN)
    assert r.status_code == 200 and "Iron Ingot" in r.text and "8 MW" in r.text
    for q in ("item=kaputt&rate=x", "item=Desc_IronPlate_C&rate=-1", "item=Desc_IronPlate_C&rate=nan",
              "item=Desc_IronPlate_C&recipe=kaputt", "item=Desc_IronPlate_C&recipe=Desc_IronPlate_C|Recipe_Nope_C",
              "remove=99", "item=Desc_IronPlate_C&rate=1e308"):
        assert client.get("/fabriken/rechner?" + q, headers=ADMIN).status_code == 200


def test_plan_history_and_rights(client):
    post(client, "/admin/add", ADMIN, name="Freund", email="freund@example.com", role="user")
    r = post(client, "/fabriken/save", ADMIN, name="Stahlwerk", state=STATE)
    assert "Stahlwerk" in r.text and "hat den Plan erstellt" in r.text
    assert "Stahlwerk" in client.get("/fabriken/", headers=FRIEND).text

    r = post(client, "/fabriken/1/save", FRIEND, name="Stahlwerk 2", state=STATE)
    assert "Freund</strong> hat den Plan geändert" in r.text

    assert post(client, "/fabriken/1/delete", FRIEND).status_code == 403
    assert "Stahlwerk 2" not in post(client, "/fabriken/1/delete", ADMIN).text.split("<tbody>")[-1]
    deleted = client.get("/fabriken/?show=deleted", headers=FRIEND).text
    assert "Stahlwerk 2" in deleted and "fa-undo" not in deleted
    r = post(client, "/fabriken/1/restore", ADMIN)
    assert "hat den Plan wiederhergestellt" in r.text and "hat den Plan gelöscht" in r.text


def test_plan_survives_deleted_user(client):
    post(client, "/admin/add", ADMIN, name="Freund", email="freund@example.com", role="user")
    post(client, "/fabriken/save", FRIEND, name="Fremd", state=STATE)
    post(client, "/admin/2/delete", ADMIN)
    assert "Freund" in client.get("/fabriken/", headers=ADMIN).text


def test_bad_state_is_rejected(client):
    assert post(client, "/fabriken/save", ADMIN, name="x", state="[]").status_code == 400
    assert post(client, "/fabriken/save", ADMIN, name="x", state="kein json").status_code == 400
    assert post(client, "/fabriken/save", ADMIN, name="", state=STATE).status_code == 200
    assert client.get("/fabriken/99", headers=ADMIN).status_code == 404
