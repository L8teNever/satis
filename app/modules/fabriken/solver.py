"""Rechenkern: Produktionsziele -> Rezept-Raten, Gebäude, Strom, Rohstoffe.

Pro Item ist genau ein Rezept aktiv. Die Raten werden so lange angepasst, bis jedes Item gedeckt ist.
Das löst auch Kreisläufe und rechnet Nebenprodukte an. Was übrig bleibt, steht als Überschuss im Ergebnis.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data.json").read_text(encoding="utf-8"))
ITEMS, RECIPES, BUILDINGS, RAW = DATA["items"], DATA["recipes"], DATA["buildings"], set(DATA["raw"])
EXTERNAL = "raw"  # Auswahl "Item nicht bauen, sondern anliefern"
EPS = 1e-7

BY_ITEM = defaultdict(list)
for _cls, _r in RECIPES.items():
    for _item, _ in _r["out"]:
        BY_ITEM[_item].append(_cls)
for _list in BY_ITEM.values():
    _list.sort(key=lambda c: (RECIPES[c]["alternate"], RECIPES[c]["name"]))


class SolveError(Exception):
    pass


def recipes_for(item):
    return BY_ITEM.get(item, [])


def default_recipe(item):
    """Standardrezept. Rohstoffe, Item ohne Rezept und reine Nebenprodukte werden angeliefert."""
    if item in RAW:
        return None

    def rank(cls):
        r = RECIPES[cls]
        return (r["name"].startswith("Unpackage"), r["alternate"], r["name"])

    usable = [c for c in recipes_for(item) if RECIPES[c]["out"][0][0] == item]
    return min(usable, key=rank) if usable else None


def _active(targets, choices):
    """Sucht von den Zielen aus alle nötigen Rezepte: {item: rezept}."""
    active, todo, seen = {}, list(targets), set()
    while todo:
        item = todo.pop()
        if item in seen:
            continue
        seen.add(item)
        choice = choices.get(item)
        cls = None if choice == EXTERNAL else choice or default_recipe(item)
        if cls:
            active[item] = cls
            todo += [i for i, _ in RECIPES[cls]["in"]]
    return active


def _amount(rows, item):
    return sum(a for i, a in rows if i == item)


def _rates(targets, active):
    """Raten in Durchläufen pro Minute je Rezept."""
    served = defaultdict(list)
    for item, cls in active.items():
        served[cls].append(item)
    rates = dict.fromkeys(served, 0.0)
    for _ in range(5000):
        delta = 0.0
        for cls in served:
            r, need = RECIPES[cls], 0.0
            for item in served[cls]:
                per_run = _amount(r["out"], item) - _amount(r["in"], item)
                if per_run <= 0:
                    raise SolveError(f"{r['name']} verbraucht mehr {ITEMS[item]['name']}, als es herstellt.")
                demand = targets.get(item, 0.0)
                for other, rate in rates.items():
                    if other != cls:
                        demand += rate * (_amount(RECIPES[other]["in"], item) - _amount(RECIPES[other]["out"], item))
                need = max(need, demand / per_run)
            delta = max(delta, abs(need - rates[cls]))
            rates[cls] = need
        if delta < 1e-9:
            return rates
        if max(rates.values()) > 1e9:
            break
    raise SolveError("Diese Rezepte ergeben einen Kreislauf ohne Lösung. Wähl für eines davon ein anderes Rezept.")


def _depths(targets, active):
    """Abstand jedes Rezepts vom Ziel, für eine sinnvolle Reihenfolge."""
    depth = {}
    todo = [(i, 0) for i in targets]
    while todo:
        item, d = todo.pop()
        cls = active.get(item)
        if cls and depth.get(cls, -1) < d and d < len(active) + 1:
            depth[cls] = d
            todo += [(i, d + 1) for i, _ in RECIPES[cls]["in"]]
    return depth


def _graph(steps, raw, targets, surplus, made, used):
    nodes, edges = [], []
    for s in steps:
        nodes.append({"id": s["recipe"], "label": f"{s['building']} x{s['count']:.2f}\n{s['name']}", "kind": "step"})
    for row in raw:
        nodes.append({"id": "raw:" + row["item"], "label": f"{row['name']}\n{row['rate']:.2f}/min", "kind": "raw"})
    for item, rate in targets.items():
        nodes.append({"id": "out:" + item, "label": f"{ITEMS[item]['name']}\n{rate:.2f}/min", "kind": "target"})
    for row in surplus:
        nodes.append({"id": "left:" + row["item"], "label": f"Überschuss\n{row['name']}", "kind": "surplus"})

    extra = {r["item"]: r["rate"] for r in raw}
    leftover = {r["item"]: r["rate"] for r in surplus}
    for item, consumers in used.items():
        sources = dict(made.get(item, {}))
        if item in extra:
            sources["raw:" + item] = extra[item]
        sinks = dict(consumers)
        if item in targets:
            sinks["out:" + item] = targets[item]
        if item in leftover:
            sinks["left:" + item] = leftover[item]
        total = sum(sources.values())
        for src, rate_out in sources.items():
            for dst, rate_in in sinks.items():
                flow = rate_in * rate_out / total if total else 0
                if flow > EPS:
                    edges.append({"source": src, "target": dst, "label": f"{flow:.2f}"})
    return {"nodes": nodes, "edges": edges}


def solve(targets, choices=None):
    """targets {item: pro Minute}, choices {item: rezept oder EXTERNAL}."""
    choices = choices or {}
    active = _active(targets, choices)
    rates = _rates(targets, active)
    depth = _depths(targets, active)

    made, used = defaultdict(dict), defaultdict(dict)
    steps = []
    for cls, rate in rates.items():
        if rate <= EPS:
            continue
        r = RECIPES[cls]
        count = rate * r["time"] / 60
        for item, amount in r["out"]:
            made[item][cls] = amount * rate
        for item, amount in r["in"]:
            used[item][cls] = amount * rate
        steps.append({
            "recipe": cls, "name": r["name"], "building": BUILDINGS[r["building"]], "count": count,
            "machines": math.ceil(count - EPS), "power": count * r["power"],
            "item": next(i for i, c in active.items() if c == cls),
            "inputs": [{"item": i, "name": ITEMS[i]["name"], "rate": a * rate} for i, a in r["in"]],
            "outputs": [{"item": i, "name": ITEMS[i]["name"], "rate": a * rate} for i, a in r["out"]],
        })
    steps.sort(key=lambda s: (depth.get(s["recipe"], 99), s["name"]))

    raw, surplus = [], []
    for item in sorted(set(made) | set(used) | set(targets), key=lambda i: ITEMS[i]["name"]):
        balance = sum(made[item].values()) - sum(used[item].values()) - targets.get(item, 0.0)
        row = {"item": item, "name": ITEMS[item]["name"], "rate": abs(balance), "liquid": ITEMS[item]["liquid"]}
        if balance < -EPS:
            raw.append(row)
        elif balance > EPS:
            surplus.append(row)

    buildings = defaultdict(lambda: {"count": 0, "power": 0.0})
    for s in steps:
        buildings[s["building"]]["count"] += s["machines"]
        buildings[s["building"]]["power"] += s["power"]
    return {
        "steps": steps, "raw": raw, "surplus": surplus,
        "buildings": [{"name": k, **v} for k, v in sorted(buildings.items())],
        "power": sum(s["power"] for s in steps),
        "graph": _graph(steps, raw, targets, surplus, made, used),
    }
