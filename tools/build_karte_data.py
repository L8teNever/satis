"""Baut app/modules/karte/data.json.

Aufruf: python tools/build_karte_data.py <SatisfactoryTools data.json> <resource_nodes.json> <Auszug eines Spielstands> app/modules/karte/data.json
Quellen: greeny/SatisfactoryTools (Namen, Maße), Fade97/satisfactory-logistics-map (Sorte, Reinheit), beide MIT.
Die Positionen kommen aus dem Auszug (extract.mjs). Mit ihnen finden sich Vorkommen wieder, deren ID sich geändert hat.
"""
import json
import sys

tools = json.load(open(sys.argv[1], encoding="utf-8"))
nodes = json.load(open(sys.argv[2], encoding="utf-8"))
places = {n["id"]: n for n in json.load(open(sys.argv[3], encoding="utf-8"))["nodes"]}

classes = {}
for cls, b in tools["buildings"].items():
    size = b.get("size") or {}
    classes[cls.replace("Desc_", "Build_", 1)] = [b["name"], size.get("width") or 0, size.get("length") or 0]
items = {k: v["name"] for k, v in tools["items"].items()}
out = {
    "classes": classes,
    "items": items,
    "nodes": {k: [v["item"], v["purity"], places[k]["x"], places[k]["y"]] for k, v in nodes.items()},
}
json.dump(out, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
print(len(classes), "Klassen,", len(out["nodes"]), "Vorkommen")
