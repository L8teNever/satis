"""Baut app/modules/fabriken/data.json aus der data.json von greeny/SatisfactoryTools (MIT).

Aufruf: python tools/build_fabriken_data.py <data.json> app/modules/fabriken/data.json
"""
import json
import sys

src = json.load(open(sys.argv[1], encoding="utf-8"))


def amounts(rows):
    return [[r["item"], r["amount"]] for r in rows]  # Flüssigkeiten stehen schon in m³ in der Quelle


def machine(recipe):
    for cls in recipe["producedIn"]:
        b = src["buildings"].get(cls)
        if b and b["metadata"].get("manufacturingSpeed"):
            return cls, b
    return None, None


recipes, buildings = {}, {}
for cls, r in src["recipes"].items():
    building, b = machine(r)
    if not r["inMachine"] or r["forBuilding"] or not building or not r["products"]:
        continue
    power = b["metadata"].get("powerConsumption", 0)
    if r.get("isVariablePower"):
        power = (r["minPower"] + r["maxPower"]) / 2
    buildings[building] = b["name"]
    recipes[cls] = {"name": r["name"], "alternate": r["alternate"] or r["name"].startswith("Alternate"), "time": r["time"], "building": building,
                    "power": power, "in": amounts(r["ingredients"]), "out": amounts(r["products"])}

used = {i for r in recipes.values() for i, _ in r["in"] + r["out"]}
items = {k: {"name": v["name"], "liquid": v["liquid"]} for k, v in src["items"].items() if k in used}
out = {"items": items, "recipes": recipes, "buildings": buildings, "raw": sorted(src["resources"])}
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
print(len(items), "Items,", len(recipes), "Rezepte,", len(buildings), "Gebäude")
