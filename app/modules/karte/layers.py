"""Macht aus dem Rohauszug eines Spielstands (extract/extract.mjs) die Ebenen der Karte.

Neue Ebene = ein Eintrag in LAYERS und eine Regel in RULES. Die erste passende Regel gewinnt.
Klassen, die keine Regel trifft: Build_* landet unter „Sonstiges“, alles andere (Pflanzen, Tiere) fällt weg.
"""
import json
import re
from pathlib import Path

from ..fabriken.solver import RECIPES

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
    ("wires", "Stromkabel", "Strom", "#3a8f78", "line", False, None),
    ("players", "Spieler", "Welt", "#ffffff", "dot", True, None),
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


def build(raw, by=""):
    labels, index = [], {}

    def label(text):
        if text not in index:
            index[text] = len(labels)
            labels.append(text)
        return index[text]

    defaults = {row[0]: row[6] for row in LAYERS}
    items = {row[0]: [] for row in LAYERS}
    counts = dict.fromkeys(items, 0)

    for cls, rows in raw["things"].items():
        layer = layer_of(cls)
        if not layer:
            continue
        name = DATA["classes"].get(cls, [_pretty(cls)])[0]
        for x, y, _z, yaw, extra in rows:
            target = layer
            if cls == "BP_DropPod_C":
                target = "drop_closed" if extra == "closed" else "drop_open"
            text = name
            if extra in RECIPES:
                text = f"{name}: {RECIPES[extra]['name']}"
            counts[target] += 1
            if defaults[target]:
                length, width = _size(cls, defaults[target])
                items[target] += [x, y, yaw, length, width, label(text)]
            else:
                items[target] += [x, y, label(text)]

    for cls, lines in raw["lines"].items():
        layer = _line_layer(cls)
        if layer:
            items[layer] += [_flat(line) for line in lines]
            counts[layer] += len(lines)
    items["wires"] = [[w[0], w[1], w[3], w[4]] for w in raw["wires"]]
    counts["wires"] = len(raw["wires"])
    for p in raw["players"]:
        items["players"] += [p["x"], p["y"], label(p["name"] or "Spieler")]
        counts["players"] += 1

    layers = [{"id": i, "label": name, "group": group, "color": color, "kind": kind, "on": on,
               "count": counts[i], "items": items[i]}
              for i, name, group, color, kind, on, _size_ in LAYERS if counts[i]]
    return {
        "meta": {**raw["meta"], "by": by},
        "bounds": BOUNDS,
        "labels": labels,
        "layers": _node_layers(raw["nodes"], label) + layers,
    }


NODE_COLORS = {
    "Desc_OreIron_C": "#c8765a", "Desc_OreCopper_C": "#e08a4a", "Desc_Stone_C": "#c8c0b0", "Desc_Coal_C": "#505050",
    "Desc_OreGold_C": "#ffd24a", "Desc_LiquidOil_C": "#a040a0", "Desc_LiquidOilWell_C": "#a040a0", "Desc_Sulfur_C": "#e8e040",
    "Desc_OreBauxite_C": "#d05050", "Desc_RawQuartz_C": "#f090c0", "Desc_OreUranium_C": "#60e060", "Desc_SAM_C": "#9040ff",
    "Desc_NitrogenGas_C": "#a0d0ff", "Desc_Water_C": "#4080ff", "Desc_Geyser_C": "#ff8040",
}


def _node_info(node):
    """Sorte und Reinheit. Manche Spielversionen benennen Vorkommen um, dann hilft die Position weiter."""
    known = DATA["nodes"].get(node["id"]) or next(
        (v for v in DATA["nodes"].values() if abs(v[2] - node["x"]) < 200 and abs(v[3] - node["y"]) < 200), None)
    return known[:2] if known else (None, None)


def _node_layers(nodes, label):
    """Eine Ebene pro Rohstoff. Sorte und Reinheit stehen nicht im Spielstand, sondern in data.json."""
    found = {}
    for n in nodes:
        item, purity = _node_info(n)
        name = DATA["items"].get(item, _pretty(item or "Unbekannt")) if item != "Desc_Geyser_C" else "Geysir"
        row = found.setdefault(name, {"item": item, "items": [], "count": 0})
        state = "belegt" if n["used"] else "frei"
        text = ", ".join(x for x in (name, PURITY.get(purity), state) if x)
        row["items"] += [n["x"], n["y"], label(text), purity or 1, int(n["used"])]
        row["count"] += 1
    return [{"id": "node:" + name, "label": name, "group": "Vorkommen", "color": NODE_COLORS.get(row["item"], "#ffffff"),
             "kind": "node", "on": True, "count": row["count"], "items": row["items"]}
            for name, row in sorted(found.items())]
