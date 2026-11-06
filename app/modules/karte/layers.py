"""Macht aus dem Rohauszug eines Spielstands (extract/extract.mjs) die Ebenen der Karte.

Neue Ebene = ein Eintrag in LAYERS und eine Regel in RULES. Die erste passende Regel gewinnt.
Klassen, die keine Regel trifft: Build_* landet unter „Sonstiges“, alles andere (Pflanzen, Tiere) fällt weg.
"""
import json
import re
from pathlib import Path

from ..fabriken.solver import ITEMS, RECIPES

DATA = json.loads((Path(__file__).parent / "data.json").read_text(encoding="utf-8"))
BOUNDS = {"x": -324698.832031, "y": -375000.0, "size": 750000.0}  # Bereich der Karte in Spielkoordinaten (cm)
PURITY = {0.5: "Unrein", 1.0: "Normal", 2.0: "Rein"}

# id, Name, Gruppe, Farbe, Art, an?, Standardgröße (Länge, Breite in cm)
LAYERS = [
    ("foundations", "Fundamente", "Bauwerke", "#5a6470", "rect", True, (800, 800)),
    ("walls", "Wände und Zäune", "Bauwerke", "#77808a", "rect", False, (800, 60)),
    ("pillars", "Pfeiler", "Bauwerke", "#c9b458", "rect", True, (200, 200)),
    ("beams", "Träger", "Bauwerke", "#9a8c6a", "rect", False, (400, 40)),
    ("walkways", "Laufstege und Treppen", "Bauwerke", "#8a7a9a", "rect", False, (400, 200)),
    ("other", "Sonstiges", "Bauwerke", "#a0a0a0", "rect", False, (200, 200)),
    ("belts", "Förderbänder", "Logistik", "#e0a030", "line", True, None),
    ("lifts", "Aufzüge", "Logistik", "#e0c030", "rect", True, (200, 200)),
    ("attachments", "Splitter und Merger", "Logistik", "#f0d060", "rect", True, (300, 300)),
    ("belt_poles", "Bandhalter", "Logistik", "#8c7a4a", "rect", False, (120, 120)),
    ("pipes", "Rohre", "Logistik", "#30a0e0", "line", True, None),
    ("pipe_parts", "Pumpen und Rohrteile", "Logistik", "#60c0f0", "rect", True, (200, 200)),
    ("pipe_poles", "Rohrhalter", "Logistik", "#4a7a8c", "rect", False, (120, 120)),
    ("hyper", "Hypertubes", "Logistik", "#c060e0", "line", True, None),
    ("storage", "Lager", "Logistik", "#d08050", "rect", True, (1000, 500)),
    ("rails", "Schienen", "Verkehr", "#d0d0d0", "line", True, None),
    ("stations", "Bahnhöfe und Stationen", "Verkehr", "#40c0a0", "rect", True, (1600, 800)),
    ("signals", "Signale", "Verkehr", "#80e0c0", "rect", False, (150, 150)),
    ("roads", "Straßen", "Verkehr", "#6a6a6a", "line", True, None),
    ("vehicles", "Fahrzeuge und Züge", "Verkehr", "#ff6090", "rect", True, (800, 400)),
    ("factories", "Fabriken", "Produktion", "#f39c12", "rect", True, (1000, 800)),
    ("miners", "Miner und Extraktoren", "Produktion", "#e74c3c", "rect", True, (1400, 600)),
    ("base", "HUB und Basis", "Produktion", "#ffffff", "rect", True, (1000, 1000)),
    ("generators", "Kraftwerke", "Strom", "#00bc8c", "rect", True, (2000, 1000)),
    ("power_poles", "Strommasten", "Strom", "#70d0b0", "rect", True, (120, 120)),
    ("wires", "Stromkabel", "Strom", "#f2c94c", "line", True, None),
    ("players", "Spieler", "Welt", "#00d2ff", "player", True, None),
    ("drop_closed", "Drop Pods, zu", "Welt", "#ff5050", "dot", True, None),
    ("drop_open", "Drop Pods, offen", "Welt", "#885050", "dot", False, None),
    ("somersloops", "Somersloops", "Welt", "#d040d0", "dot", False, None),
    ("mercer", "Mercer-Kugeln", "Welt", "#8060ff", "dot", False, None),
]

RULES = [(layer, re.compile(pattern, re.I)) for layer, pattern in [
    ("drop_closed", r"^BP_DropPod_C$"),
    ("somersloops", r"^BP_WAT1_C$"),
    ("mercer", r"^BP_WAT2_C$"),
    ("vehicles", r"^BP_(Tractor|Truck|Explorer|Golfcart|GolfcartGold|Locomotive|FreightWagon|DroneTransport)_C$"),
    ("generators", r"^Build_(Generator|PowerStorage|AlienPowerBuilding)"),
    ("power_poles", r"^Build_Power(Pole|Tower)"),
    ("miners", r"^Build_(Miner|WaterPump|OilPump|Fracking)"),
    ("factories", r"^Build_(Constructor|Smelter|Foundry|Assembler|Manufacturer|OilRefinery|Packager|Blender"
                  r"|HadronCollider|Converter|QuantumEncoder)"),
    ("base", r"^Build_(TradingPost|HubTerminal|WorkBench|Workshop|Mam|SpaceElevator|ResourceSink|RadarTower|StoragePlayer"
             r"|BlueprintDesigner|LookoutTower|StorageIntegrated)"),
    ("stations", r"^Build_(Train(Station|DockingStation|PlatformEmpty)|TruckStation|DroneStation)"),
    ("signals", r"^Build_Railroad(BlockSignal|SwitchControl|EndStop|Signal)"),
    ("storage", r"^Build_(Storage|IndustrialTank|PipeStorageTank|CentralStorage|ContainerScreen)"),
    ("attachments", r"^Build_(ConveyorAttachment|RatioSplitter|RatioMerger)"),
    ("lifts", r"^(Build_ConveyorLift|Lift_mk)"),
    ("belt_poles", r"^Build_Conveyor(Pole|CeilingAttachment|SupportWall|WallHole)"),
    ("pipe_poles", r"^Build_(PipeSupport|PipelineSupport|PipeHyperSupport|HyperPole|HyperTubeWall)"),
    ("pipe_parts", r"^Build_(Pipeline(Pump|Junction|FlowIndicator)|Valve|PipeHyperStart|HypertubeTJunction)"),
    ("pillars", r"Pillar"),
    ("beams", r"Beam"),
    ("walkways", r"(Catwalk|Walkway|Stair|Ladder)"),
    ("walls", r"(Wall|Fence|Barrier|Railing|Gate)"),
    ("foundations", r"(Foundation|Ramp|QuarterPipe|Concrete_(Block|Cylinder|Trigon)|MetalF_|MetalG_Floor|Found_)"),
]]
LINE_RULES = [(layer, re.compile(pattern, re.I)) for layer, pattern in [
    ("belts", r"(ConveyorBelt|Beltmk)"),
    ("pipes", r"^Build_Pipeline"),
    ("hyper", r"^Build_PipeHyper"),
    ("rails", r"^Build_RailroadTrack"),
    ("roads", r"Road"),
]]
# Grundflächen in cm (Länge, Breite), ungefähr nach den Gebäudemaßen im Spiel
SIZES = [(re.compile(pattern, re.I), size) for pattern, size in [
    (r"Constructor", (1000, 800)), (r"Smelter", (900, 600)), (r"Foundry", (900, 1000)), (r"Assembler", (1500, 1000)),
    (r"Manufacturer", (2000, 1800)), (r"OilRefinery", (2000, 1000)), (r"Packager", (800, 800)), (r"Blender", (1600, 1800)),
    (r"HadronCollider", (3800, 2400)), (r"GeneratorCoal", (2600, 1000)), (r"GeneratorFuel", (2000, 2000)),
    (r"GeneratorNuclear", (4300, 3600)), (r"GeneratorBiomass", (800, 800)), (r"Miner", (1400, 600)), (r"WaterPump", (2000, 2000)),
    (r"OilPump", (2000, 1000)), (r"StorageContainerMk1", (1000, 500)), (r"StorageContainerMk2", (1000, 500)),
    (r"IndustrialTank", (1200, 1200)), (r"PipeStorageTank", (600, 600)), (r"Pillar.*Small", (100, 100)),
]]


def _pretty(cls):
    return re.sub(r"^(Build|BP|Desc)_|_C$", "", cls).replace("_", " ")


def _size(cls, default):
    return next((size for pattern, size in SIZES if pattern.search(cls)), default)


def layer_of(cls):
    for layer, pattern in RULES:
        if pattern.search(cls):
            return layer
    return "other" if cls.lower().startswith("build") else None


def _line_layer(cls):
    return next((layer for layer, pattern in LINE_RULES if pattern.search(cls)), None)


def _flat(line):
    """[x, y, z, ...] -> [x, y, ...]"""
    return [v for i, v in enumerate(line) if i % 3 != 2]


def build(raw, by="", filename=""):
    labels, index = [], {}

    def label(text):
        if text not in index:
            index[text] = len(labels)
            labels.append(text)
        return index[text]

    defaults = {row[0]: row[6] for row in LAYERS}
    items = {row[0]: [] for row in LAYERS}
    counts = dict.fromkeys(items, 0)
    # Hover: Inventar und Zustand pro Gebäude. Schlüssel ist die laufende Nummer in der Ebene.
    details = {row[0]: {} for row in LAYERS}
    seen_items = set()

    for cls, rows in raw["things"].items():
        layer = layer_of(cls)
        if not layer:
            continue
        name = DATA["classes"].get(cls, [_pretty(cls)])[0]
        for row in rows:
            x, y, _z, yaw, extra = row[:5]
            target = layer
            if cls == "BP_DropPod_C":
                target = "drop_closed" if extra == "closed" else "drop_open"
            text = name
            if extra in RECIPES:
                text = f"{name}: {RECIPES[extra]['name']}"
            if len(row) > 5 and row[5]:
                info = _details(row[5], extra, seen_items)
                if info:
                    details[target][str(counts[target])] = info
            counts[target] += 1
            if defaults[target]:
                length, width = _size(cls, defaults[target])
                items[target] += [x, y, yaw, length, width, label(text)]
            else:
                items[target] += [x, y, label(text)]

    for cls, lines in raw["lines"].items():
        layer = _line_layer(cls)
        if layer:
            extra = raw.get("lineInfo", {}).get(cls) or []
            for n, line in enumerate(lines):
                info = _line_details(cls, line, extra[n] if n < len(extra) else None, seen_items)
                if info:
                    details[layer][str(counts[layer])] = info
                items[layer].append(_flat(line))
                counts[layer] += 1
    items["wires"] = [[w[0], w[1], w[3], w[4]] for w in raw["wires"]]
    counts["wires"] = len(raw["wires"])
    for n, w in enumerate(raw["wires"]):
        if len(w) >= 9:  # ältere Auszüge kennen die Enden nicht
            details["wires"][str(n)] = {"name": "Stromkabel", "len": round(w[8] / 100, 1),
                                        "ends": [_end(w[6]), _end(w[7])]}
    for idx, p in enumerate(raw["players"]):
        name = p.get("name") or (f"Spieler {idx + 1}" if len(raw["players"]) > 1 else "Spieler")
        yaw = p.get("yaw", 0)
        info = _player_details(p, seen_items)
        if info:
            details["players"][str(counts["players"])] = info
        items["players"] += [p["x"], p["y"], yaw, label(name)]
        counts["players"] += 1

    layers = [{"id": i, "label": name, "group": group, "color": color, "kind": kind, "on": on,
               "count": counts[i], "items": items[i], "icon": _icon(i), **({"details": details[i]} if details[i] else {})}
              for i, name, group, color, kind, on, _size_ in LAYERS if counts[i]]
    return {
        "meta": {**raw["meta"], "by": by, "filename": filename or raw.get("meta", {}).get("filename", "")},
        "bounds": BOUNDS,
        "labels": labels,
        # Namen der Items, die in Inventaren vorkommen: Klasse -> [Name, flüssig?]
        "items": {c: [DATA["items"].get(c) or _pretty(c), bool(ITEMS.get(c, {}).get("liquid"))] for c in sorted(seen_items)},
        "layers": _node_layers(raw["nodes"], label) + layers,
    }


INVENTORY_PARTS = ("in", "out", "fuel", "store", "boost")
BELT_SPEED = {"1": 60, "2": 120, "3": 270, "4": 480, "5": 780, "6": 1200}  # Items pro Minute
PIPE_FLOW = {"Build_Pipeline_C": 300, "Build_PipelineNoIndicator_C": 300, "Build_PipelineMK2_C": 600,
             "Build_PipelineMK2_NoIndicator_C": 600}  # m³ pro Minute


def _length(line):
    """Länge einer Linie [x, y, z, ...] in Metern."""
    return round(sum(((line[i] - line[i - 3]) ** 2 + (line[i + 1] - line[i - 2]) ** 2 + (line[i + 2] - line[i - 1]) ** 2) ** .5
                     for i in range(3, len(line) - 2, 3)) / 100, 1)


def _line_details(cls, line, info, seen):
    """Hover für Bänder und Rohre: Name, Länge, Tempo, was gerade drauf bzw. drin ist."""
    name = DATA["classes"].get(cls, [_pretty(cls)])[0]
    out = {"name": name, "len": _length(line)}
    belt = re.search(r"ConveyorBeltMk(\d)", cls)
    if belt:
        out["speed"] = BELT_SPEED.get(belt.group(1))
    if cls in PIPE_FLOW:
        out["flow"] = PIPE_FLOW[cls]
    info = info or {}
    if info.get("items"):
        rows = sorted(info["items"].items(), key=lambda kv: -kv[1])
        seen.update(item for item, _n in rows)
        out["items"] = [list(r) for r in rows]
    if info.get("fluid"):
        out["fluid"] = info["fluid"]
    return out


def _end(cls):
    """Ende eines Stromkabels: [Name, Gebäude-Klasse fürs Icon (static/icons/building/Desc_….png)]."""
    if not cls:
        return ["?", ""]
    return [DATA["classes"].get(cls, [_pretty(cls)])[0], cls.replace("Build_", "Desc_", 1)]


def _player_details(p, seen):
    """Hover für Spieler: Inventar (Slots in Spielreihenfolge, leer = null), Ausrüstung, Hotbar."""
    out = {}
    if p.get("inventory"):
        out["inv"] = p["inventory"]
        seen.update(s[0] for s in p["inventory"] if s)
    if p.get("equipment"):
        out["equip"] = p["equipment"]
        seen.update(p["equipment"])
    bar = [DATA.get("shortcuts", {}).get(r) if r else None for r in p.get("hotbar") or []]
    if any(bar):
        out["hotbar"] = bar
    if p.get("health") is not None:
        out["health"] = round(p["health"])
    return out


def _details(info, recipe, seen):
    """Rohdaten aus extract.mjs -> Hover: {"recipe": Name, "inv": [[Teil, [[Klasse, Menge], ...]], ...], ...}.
    Flüssigkeiten stehen im Spielstand in Litern, angezeigt werden m³."""
    out = {k: info[k] for k in ("eff", "clock", "boost", "prog", "paused") if k in info}
    if recipe in RECIPES:
        out["recipe"] = RECIPES[recipe]["name"]
    inv = info.get("inv") or {}
    parts = []
    for part in INVENTORY_PARTS:
        stacks = inv.get(part) or {}
        rows = []
        for item, n in sorted(stacks.items(), key=lambda kv: -kv[1]):
            seen.add(item)
            amount = round(n / 1000, 1) if ITEMS.get(item, {}).get("liquid") else n
            rows.append([item, amount])
        if rows:
            parts.append([part, rows])
    if parts:
        out["inv"] = parts
    return out if (parts or len(out) > ("recipe" in out)) else None


NODE_COLORS = {
    "Desc_OreIron_C": "#c8765a", "Desc_OreCopper_C": "#e08a4a", "Desc_Stone_C": "#c8c0b0", "Desc_Coal_C": "#505050",
    "Desc_OreGold_C": "#ffd24a", "Desc_LiquidOil_C": "#a040a0", "Desc_LiquidOilWell_C": "#a040a0", "Desc_Sulfur_C": "#e8e040",
    "Desc_OreBauxite_C": "#d05050", "Desc_RawQuartz_C": "#f090c0", "Desc_OreUranium_C": "#60e060", "Desc_SAM_C": "#9040ff",
    "Desc_NitrogenGas_C": "#a0d0ff", "Desc_Water_C": "#4080ff", "Desc_Geyser_C": "#ff8040",
}

# Icons aus dem Spiel (static/icons, aus greeny/SatisfactoryTools, MIT). Gebäude-Ebenen heißen wie ihre Datei.
NODE_ICONS = {
    "Desc_OreIron_C": "iron", "Desc_OreCopper_C": "copper", "Desc_Stone_C": "stone", "Desc_Coal_C": "coal",
    "Desc_OreGold_C": "gold", "Desc_LiquidOil_C": "oil", "Desc_LiquidOilWell_C": "oil", "Desc_Sulfur_C": "sulfur",
    "Desc_OreBauxite_C": "bauxite", "Desc_RawQuartz_C": "quartz", "Desc_OreUranium_C": "uranium", "Desc_SAM_C": "sam",
    "Desc_NitrogenGas_C": "nitrogen", "Desc_Water_C": "water", "Desc_Geyser_C": "geyser",
}
WORLD_ICONS = {"drop_closed": "harddrive", "drop_open": "harddrive", "somersloops": "somersloop", "mercer": "mercer"}


def _icon(layer):
    if layer in WORLD_ICONS:
        return f"items/{WORLD_ICONS[layer]}.png"
    return "" if layer == "players" else f"buildings/{layer}.png"


def _node_info(node):
    """Sorte und Reinheit. Manche Spielversionen benennen Vorkommen um, dann hilft die Position weiter."""
    known = DATA["nodes"].get(node["id"]) or next(
        (v for v in DATA["nodes"].values() if abs(v[2] - node["x"]) < 200 and abs(v[3] - node["y"]) < 200), None)
    return known[:2] if known else (None, None)


def _node_kind(item):
    """Wie abgebaut wird: Miner (ore), Ölpumpe (oil), Druckextraktor (well) oder Geothermie (geyser)."""
    if item == "Desc_Geyser_C":
        return "geyser"
    if item == "Desc_LiquidOil_C":
        return "oil"
    if item in ("Desc_Water_C", "Desc_NitrogenGas_C", "Desc_LiquidOilWell_C"):
        return "well"
    return "ore"


def _node_layers(nodes, label):
    """Eine Ebene pro Rohstoff. Sorte und Reinheit stehen nicht im Spielstand, sondern in data.json."""
    found = {}
    for n in nodes:
        item, purity = _node_info(n)
        name = ({"Desc_Geyser_C": "Geysir", "Desc_LiquidOilWell_C": "Crude Oil Well"}.get(item)
                or DATA["items"].get(item, _pretty(item or "Unbekannt")))
        row = found.setdefault(name, {"item": item, "items": [], "count": 0})
        state = "belegt" if n["used"] else "frei"
        text = ", ".join(x for x in (name, PURITY.get(purity), state) if x)
        row["items"] += [n["x"], n["y"], label(text), purity or 1, int(n["used"])]
        row["count"] += 1
    return [{"id": "node:" + name, "label": name, "group": "Vorkommen", "color": NODE_COLORS.get(row["item"], "#ffffff"),
             "kind": "node", "on": True, "count": row["count"], "items": row["items"], "node": _node_kind(row["item"]),
             "icon": f"items/{NODE_ICONS[row['item']]}.png" if row["item"] in NODE_ICONS else ""}
            for name, row in sorted(found.items())]
