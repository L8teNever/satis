"""Baut app/modules/karte/shapes.json: Umriss jedes Gebäudes von oben, aus den 3D-Modellen des Spiels.

Aufruf: python tools/build_karte_shapes.py <models.json> <models.bin> app/modules/karte/shapes.json
Quelle: gamedata/models.json und models.bin aus Tunefish92/SatisfactoryMapRenderer (Modelle gehören Coffee Stain).

Pro Gebäude-Klasse werden alle Mesh-Teile mit ihrer Lage (t, r, s) zusammengesetzt, von oben betrachtet und als
konvexe Hülle gespeichert, vereinfacht auf wenige Punkte. Koordinaten in cm relativ zum Ursprung des Gebäudes,
x nach vorn, y nach rechts, wie im Spielstand. Ergebnis: {"Build_X_C": [x, y, x, y, ...]}.
"""
import json
import math
import struct
import sys

STRIDE = 20  # Bytes pro Vertex: 3 × int16 Position, 3 × int8 Normale, 2 × float UV
TOLERANCE = 12.0  # cm, so genau bleibt der Umriss beim Vereinfachen


def rotate(q, v):
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def simplify(poly):
    """Punkte weglassen, solange sich die Kante um weniger als TOLERANCE verschiebt."""
    poly = list(poly)
    changed = True
    while changed and len(poly) > 4:
        changed = False
        for i in range(len(poly)):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % len(poly)]
            base = math.dist(a, c) or 1
            height = abs((c[0] - a[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (c[1] - a[1])) / base
            if height < TOLERANCE:
                del poly[i]
                changed = True
                break
    return poly


def main(models_json, models_bin, out_path):
    meta = json.load(open(models_json, encoding="utf-8"))
    data = open(models_bin, "rb").read()
    mesh_points = {}

    def points_of(name):
        """Grundriss-Punkte eines Meshes (nur die Hülle, damit die Klassen schnell zusammengesetzt sind)."""
        if name not in mesh_points:
            m = meta["meshes"][name]
            lo, size, off = m["min"], m["size"], m["vertexOffset"]
            pts = []
            for k in range(m["v"]):
                vx, vy, vz = struct.unpack_from("<hhh", data, off + k * STRIDE)
                pts.append((lo[0] + (vx + 32768) / 65535 * size[0], lo[1] + (vy + 32768) / 65535 * size[1],
                            lo[2] + (vz + 32768) / 65535 * size[2]))
            # Für die Hülle reicht ein Raster von 5 cm, das spart viel Rechenzeit
            flat = {(round(p[0] / 5) * 5, round(p[1] / 5) * 5, p[2]) for p in pts}
            keep = hull([(p[0], p[1]) for p in flat])
            zs = {}
            for p in flat:
                zs.setdefault((p[0], p[1]), p[2])
            mesh_points[name] = [(x, y, zs.get((x, y), 0)) for x, y in keep]
        return mesh_points[name]

    shapes = {}
    for cls, parts in meta["classes"].items():
        if not cls.startswith("Build_"):
            continue
        pts = []
        for part in parts:
            if part["mesh"] not in meta["meshes"]:
                continue
            s, t, r = part.get("s", [1, 1, 1]), part.get("t", [0, 0, 0]), part.get("r", [0, 0, 0, 1])
            for p in points_of(part["mesh"]):
                v = rotate(r, (p[0] * s[0], p[1] * s[1], p[2] * s[2]))
                pts.append((round(t[0] + v[0], 1), round(t[1] + v[1], 1)))
        if len(pts) < 3:
            continue
        poly = simplify(hull(pts))
        if len(poly) >= 3:
            shapes[cls] = [round(c) for p in poly for c in p]
    json.dump(shapes, open(out_path, "w", encoding="utf-8"), separators=(",", ":"), sort_keys=True)
    print(len(shapes), "Umrisse, Ø", round(sum(len(v) for v in shapes.values()) / 2 / max(1, len(shapes)), 1), "Punkte")


if __name__ == "__main__":
    main(*sys.argv[1:4])
