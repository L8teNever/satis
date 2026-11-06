import io
import json
import re
import time
from pathlib import Path

import pytest

from app import create_app
from app.modules.karte import routes as karte_routes
from app.modules.karte.layers import DATA, LAYERS, _icon, _node_info, build
from app.modules.fabriken.solver import BY_ITEM, EXTERNAL, ITEMS, RECIPES, SolveError, default_recipe, solve

ADMIN = {"Cf-Access-Authenticated-User-Email": "Simon@example.com"}
FRIEND = {"Cf-Access-Authenticated-User-Email": "freund@example.com"}
ICONS = Path(__file__).parent.parent / "app" / "static" / "icons"


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


JSON = {**ADMIN, "Accept": "application/json"}
INGOT = "Recipe_IngotIron_C"


def tick(client, headers=JSON, **data):
    return post(client, "/fabriken/1/step", headers, recipe=INGOT, **data)


def test_steps_can_be_done_and_assigned(client):
    post(client, "/admin/add", ADMIN, name="Freund", email="freund@example.com", role="user")
    post(client, "/fabriken/save", ADMIN, name="Stahlwerk", state=STATE)
    assert 'data-recipe="' + INGOT in client.get("/fabriken/1", headers=ADMIN).text

    data = tick(client, {**FRIEND, "Accept": "application/json"}, done="1").json
    assert data["done"] and data["tag"] == "Erledigt: Freund" and data["finished"] == 1 and "Freund" in data["html"]
    assert tick(client, done="1").json["tag"] == "Erledigt: Freund"  # Veraltete Seite überschreibt nichts

    assert not tick(client, done="0").json["done"]
    assert tick(client, assignee_id="2").json["tag"] == "Zuständig: Freund"
    assert 'value="2" data-icon="fa-hard-hat" selected' in client.get("/fabriken/1", headers=ADMIN).text
    assert tick(client, assignee_id="").json["tag"] == ""


def test_step_needs_more_after_target_grows(client):
    post(client, "/fabriken/save", ADMIN, name="Stahlwerk", state=STATE)
    tick(client, done="1")
    bigger = json.loads(STATE)
    bigger["targets"] = {k: v * 2 for k, v in bigger["targets"].items()}
    r = post(client, "/fabriken/1/save", ADMIN, name="Stahlwerk", state=json.dumps(bigger))
    assert "jetzt braucht es mehr" in r.text and "s-row-done" not in r.text


def test_steps_only_on_saved_plan(client):
    post(client, "/fabriken/save", ADMIN, name="Stahlwerk", state=STATE)
    assert post(client, "/fabriken/1/step", ADMIN, recipe="Recipe_Gibtsnicht_C", done="1").status_code == 409
    assert "data-step-url" not in client.get("/fabriken/rechner?item=Desc_IronPlate_C&rate=20", headers=ADMIN).text
    assert "data-step-url" not in client.get("/fabriken/1?item=Desc_IronPlate_C&rate=999", headers=ADMIN).text
    post(client, "/fabriken/1/delete", ADMIN)
    assert post(client, "/fabriken/1/step", ADMIN, recipe=INGOT, done="1").status_code == 409


RAW = {
    "meta": {"session": "Welt", "seconds": 3600, "savedAt": 0},
    "things": {
        "Build_ConstructorMk1_C": [[100, 200, 0, 90, "Recipe_IronPlate_C"]],
        "Build_PillarMiddle_C": [[1, 2, 0, 0, ""]],
        "BP_DropPod_C": [[5, 6, 0, 0, "open"]],
        "BP_BerryBush_C": [[9, 9, 0, 0, ""]],
        "Build_GibtsNicht_C": [[3, 4, 0, 0, ""]],
    },
    "lines": {"Build_ConveyorBeltMk1_C": [[0, 0, 0, 10, 20, 30]]},
    "wires": [[0, 0, 0, 1, 1, 1]],
    "players": [{"name": "Simon", "x": 7, "y": 8, "z": 0}],
    "nodes": [{"id": "BP_FrackingSatellite10", "x": 1, "y": 1, "z": 0, "used": True}],
}


def test_world_layers():
    world = build(RAW, "Simon")
    layers = {l["id"]: l for l in world["layers"]}
    plate = world["labels"][layers["factories"]["items"][5]]
    assert plate == "Constructor: Iron Plate" and layers["factories"]["items"][3:5] == [1000, 800]
    assert layers["pillars"]["count"] == 1 and layers["other"]["count"] == 1
    assert layers["belts"]["items"] == [[0, 0, 10, 20]] and layers["wires"]["items"] == [[0, 0, 1, 1]]
    assert "drop_open" in layers and "drop_closed" not in layers
    assert layers["drop_open"]["icon"] == "items/harddrive.png" and layers["pillars"]["icon"] == "buildings/pillars.png"
    assert all((ICONS / l["icon"]).exists() for l in world["layers"] if l["icon"])
    assert layers["players"]["kind"] == "player"
    assert layers["players"]["items"] == [7, 8, 0, world["labels"].index("Simon")]
    assert sum(l["count"] for l in world["layers"]) == 8  # Die Beere zählt nicht
    assert world["meta"]["by"] == "Simon"


def test_renamed_node_is_found_by_position():
    name, x, y = next((k, v[2], v[3]) for k, v in DATA["nodes"].items() if v[0] == "Desc_Stone_C")
    assert _node_info({"id": "BP_ResourceNode_Neu", "x": x + 1, "y": y - 1}) == DATA["nodes"][name][:2]
    assert _node_info({"id": "BP_ResourceNode_Neu", "x": 9e9, "y": 9e9}) == (None, None)


def test_map_tab_and_upload(client, monkeypatch, tmp_path):
    monkeypatch.setattr(karte_routes, "_read_save", lambda folder, sav, by, *args, **kwargs: (
        karte_routes._write(folder / "world.json", build(RAW, by, filename=args[0] if args else kwargs.get("filename", ""))),
        karte_routes._write(folder / "status.json", {"state": "ok", "filename": args[0] if args else kwargs.get("filename", "")})))
    img_path = tmp_path / "karte" / "map.jpg"
    img_path.parent.mkdir(exist_ok=True)
    img_path.write_bytes(b"\xff\xd8\xff\xe0test")
    assert client.get("/karte/bild", headers=ADMIN).status_code == 200
    page = client.get("/karte/", headers=ADMIN).text
    assert "data-karte" in page
    assert "data-karte" not in client.get("/fabriken/rechner", headers=ADMIN).text
    assert "Karte</a>" in client.get("/", headers=ADMIN).text.split("</header>")[0]
    assert client.get("/karte/world.json", headers=ADMIN).status_code == 404
    token = re.search(r'data-csrf="([^"]+)"', page).group(1)
    send = {**ADMIN, "X-CSRF-Token": token}
    bad = client.post("/karte/upload", headers=send, data={"save": (io.BytesIO(b"x"), "bild.png")})
    assert bad.status_code == 400
    good = client.post("/karte/upload", headers=send, data={"save": (io.BytesIO(b"x"), "welt.sav")})
    assert good.status_code == 202
    for _ in range(50):
        if client.get("/karte/status", headers=ADMIN).json["state"] == "ok":
            break
        time.sleep(.02)
    assert client.get("/karte/world.json", headers=ADMIN).json["meta"]["by"] == "Simon"
    assert client.post("/karte/upload", data={}).status_code == 403


def test_failed_save_keeps_old_world(tmp_path, monkeypatch):
    sav = tmp_path / "upload.sav"
    sav.write_bytes(b"kein spielstand")
    (tmp_path / "world.json").write_text("alt")
    monkeypatch.setattr(karte_routes, "EXTRACT", tmp_path / "gibtsnicht.mjs")
    karte_routes._read_save(tmp_path, sav, "Simon")
    assert (tmp_path / "world.json").read_text() == "alt" and not sav.exists()
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "failed"


def test_every_layer_has_a_game_icon():
    assert all((ICONS / _icon(row[0])).exists() for row in LAYERS if row[0] != "players")


def test_map_drawings(client):
    page = client.get("/karte/", headers=ADMIN).text
    assert 'data-marks="/karte/zeichnungen"' in page and 'data-tool="pen"' in page
    send = {**ADMIN, "X-CSRF-Token": re.search(r'data-csrf="([^"]+)"', page).group(1)}
    assert client.get("/karte/zeichnungen", headers=ADMIN).json["marks"] == []
    for bad in ({"kind": "kreis", "color": "#ff0000", "points": [0, 0]},
                {"kind": "pin", "color": "rot", "points": [0, 0]},
                {"kind": "line", "color": "#ff0000", "points": [0, 0, 1]},
                {"kind": "pen", "color": "#ff0000", "points": [0, "x"]},
                {"kind": "pin", "color": "#ff0000", "points": [0, 1e9]}):
        assert client.post("/karte/zeichnungen", headers=send, json=bad).status_code == 400
    assert client.post("/karte/zeichnungen", json={"kind": "pin", "color": "#ff0000", "points": [0, 0]},
                       headers=ADMIN).status_code == 400  # ohne CSRF-Token
    r = client.post("/karte/zeichnungen", headers=send,
                    json={"kind": "pin", "color": "#FF0000", "points": [1.234, -5], "text": " Eisenfabrik ", "width": 99})
    assert r.status_code == 201
    mark = r.json
    assert mark["color"] == "#ff0000" and mark["text"] == "Eisenfabrik" and mark["width"] == 20 and mark["by"] == "Simon"
    assert mark["points"] == [1.2, -5]
    assert [m["id"] for m in client.get("/karte/zeichnungen", headers=ADMIN).json["marks"]] == [mark["id"]]
    assert client.delete(f"/karte/zeichnungen/{mark['id']}", headers=send).status_code == 200
    assert client.delete(f"/karte/zeichnungen/{mark['id']}", headers=send).status_code == 404
    assert client.get("/karte/zeichnungen", headers=ADMIN).json["marks"] == []


def test_machine_details_for_hover():
    raw = json.loads(json.dumps(RAW))
    raw["things"]["Build_SmelterMk1_C"] = [[0, 0, 0, 0, "Recipe_IngotIron_C",
                                           {"inv": {"in": {"Desc_OreIron_C": 50}, "out": {"Desc_IronIngot_C": 7}},
                                            "eff": 87, "clock": 150}]]
    raw["things"]["Build_WaterPump_C"] = [[0, 0, 0, 0, "", {"inv": {"out": {"Desc_Water_C": 48500}}, "eff": 100}]]
    raw["things"]["Build_ConstructorMk1_C"].append([1, 1, 0, 0, "Recipe_IronPlate_C", {}])  # nichts zu zeigen
    world = build(raw, "Simon")
    layers = {l["id"]: l for l in world["layers"]}
    smelter = next(v for v in layers["factories"]["details"].values() if v.get("clock"))
    assert smelter == {"eff": 87, "clock": 150, "recipe": RECIPES["Recipe_IngotIron_C"]["name"],
                       "inv": [["in", [["Desc_OreIron_C", 50]]], ["out", [["Desc_IronIngot_C", 7]]]]}
    assert len(layers["factories"]["details"]) == 1  # der leere Constructor bekommt keinen Eintrag
    assert layers["miners"]["details"]["0"]["inv"] == [["out", [["Desc_Water_C", 48.5]]]]  # Liter -> m³
    assert world["items"]["Desc_Water_C"] == ["Water", True] and world["items"]["Desc_OreIron_C"][1] is False
    assert all((ICONS / "item" / f"{c}.png").exists() for c in world["items"])
    assert "details" not in layers["pillars"]


def test_belt_pipe_player_and_node_details():
    raw = json.loads(json.dumps(RAW))
    raw["lines"]["Build_PipelineMK2_C"] = [[0, 0, 0, 300, 400, 0]]
    raw["lineInfo"] = {"Build_ConveyorBeltMk1_C": [{"items": {"Desc_OreIron_C": 3, "Desc_Coal_C": 5}}],
                       "Build_PipelineMK2_C": [{"fluid": 12.5}]}
    raw["players"][0].update(inventory=[["Desc_OreIron_C", 20], None], equipment=["Desc_Chainsaw_C"],
                             hotbar=["Recipe_ConstructorMk1_C", ""], health=None)
    raw["nodes"] = [{"id": k, "x": v[2], "y": v[3], "z": 0, "used": False}
                    for k, v in DATA["nodes"].items() if v[0] in ("Desc_OreIron_C", "Desc_LiquidOil_C", "Desc_Water_C")][:400]
    world = build(raw, "Simon")
    layers = {l["id"]: l for l in world["layers"]}
    belt = layers["belts"]["details"]["0"]
    assert belt["speed"] == 60 and belt["items"] == [["Desc_Coal_C", 5], ["Desc_OreIron_C", 3]]
    assert belt["len"] == round((10 ** 2 + 20 ** 2 + 30 ** 2) ** .5 / 100, 1)
    assert layers["pipes"]["details"]["0"] == {"name": layers["pipes"]["details"]["0"]["name"], "len": 5.0, "flow": 600,
                                                "fluid": 12.5}
    player = layers["players"]["details"]["0"]
    assert player["inv"] == [["Desc_OreIron_C", 20], None] and player["equip"] == ["Desc_Chainsaw_C"]
    assert player["hotbar"][0][1] == "Desc_ConstructorMk1_C" and player["hotbar"][1] is None and "health" not in player
    assert (ICONS / "building" / "Desc_ConstructorMk1_C.png").exists()
    assert all((ICONS / "item" / f"{c}.png").exists() for c in world["items"])
    kinds = {l["id"]: l["node"] for l in world["layers"] if l["kind"] == "node"}
    assert kinds["node:Iron Ore"] == "ore" and kinds.get("node:Crude Oil") == "oil" and kinds.get("node:Water") == "well"
