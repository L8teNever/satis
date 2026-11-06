// Liest eine .sav-Datei und schreibt alles, was die Karte braucht, als JSON.
// Aufruf: node extract.mjs <spielstand.sav> <ausgabe.json>
// Hier wird nur gesammelt. Was daraus für Ebenen werden, entscheidet app/modules/karte/layers.py.
import fs from 'node:fs';
import { Parser } from '@etothepii/satisfactory-file-parser';

const [input, output] = process.argv.slice(2);
const file = fs.readFileSync(input);
const save = Parser.ParseSave('save', file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength), {
  throwErrors: false,
});

const classOf = (path) => (path || '').split('.').pop();
const tail = (path) => (path || '').split('.').pop();
const round = Math.round;

function yaw(q) {
  return round((Math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)) * 180) / Math.PI);
}

function rotate(q, v) {
  const tx = 2 * (q.y * v.z - q.z * v.y), ty = 2 * (q.z * v.x - q.x * v.z), tz = 2 * (q.x * v.y - q.y * v.x);
  return {
    x: v.x + q.w * tx + (q.y * tz - q.z * ty),
    y: v.y + q.w * ty + (q.z * tx - q.x * tz),
    z: v.z + q.w * tz + (q.x * ty - q.y * tx),
  };
}

const prop = (obj, name) => obj.properties?.[name];
const value = (obj, name) => prop(obj, name)?.value;

/** Spline als Punktliste in Weltkoordinaten; lange Abschnitte werden nach der Hermite-Kurve unterteilt. */
function spline(obj) {
  const rows = prop(obj, 'mSplineData')?.values;
  if (!rows?.length) return null;
  const { translation: t, rotation: q } = obj.transform;
  const pts = rows.map((r) => ({
    p: r.properties.Location.value, a: r.properties.ArriveTangent.value, l: r.properties.LeaveTangent.value,
  }));
  const line = [];
  const push = (v) => { const w = rotate(q, v); line.push(round(t.x + w.x), round(t.y + w.y), round(t.z + w.z)); };
  pts.forEach((cur, i) => {
    push(cur.p);
    const next = pts[i + 1];
    if (!next) return;
    const steps = Math.min(8, Math.floor(Math.hypot(next.p.x - cur.p.x, next.p.y - cur.p.y) / 1500));
    for (let s = 1; s <= steps; s++) {
      const u = s / (steps + 1), u2 = u * u, u3 = u2 * u;
      const h00 = 2 * u3 - 3 * u2 + 1, h10 = u3 - 2 * u2 + u, h01 = -2 * u3 + 3 * u2, h11 = u3 - u2;
      const at = (k) => h00 * cur.p[k] + h10 * cur.l[k] + h01 * next.p[k] + h11 * next.a[k];
      push({ x: at('x'), y: at('y'), z: at('z') });
    }
  });
  return line;
}

const things = {};  // Klasse -> [x, y, z, yaw, Zusatz]
const lines = {};   // Klasse -> [[x, y, z, ...], ...]
const nodes = [];   // Vorkommen mit Namen, Sorte und Reinheit stehen nicht im Spielstand
const players = [];
const wires = [];
const removed = new Set();
const used = new Set();

function thing(cls, t, q, extra = '') {
  (things[cls] ||= []).push([round(t.x), round(t.y), round(t.z), yaw(q), extra]);
}

for (const level of Object.values(save.levels)) {
  for (const ref of level.collectables || []) removed.add(ref.pathName);
  for (const list of Object.values(level.destroyedActorsMap || {})) {
    for (const ref of list || []) removed.add(ref.pathName);
  }
}

for (const level of Object.values(save.levels)) {
  for (const obj of level.objects) {
    if (obj.type !== 'SaveEntity' || removed.has(obj.instanceName)) continue;
    const cls = classOf(obj.typePath);
    const sp = obj.specialProperties;

    if (sp?.type === 'BuildableSubsystemSpecialProperties') {
      for (const group of sp.buildables) {
        const name = classOf(group.typeReference.pathName);
        for (const inst of group.instances) thing(name, inst.transform.translation, inst.transform.rotation);
      }
      continue;
    }

    const extractable = value(obj, 'mExtractableResource');
    if (extractable?.pathName) used.add(tail(extractable.pathName));

    const { translation: t, rotation: q } = obj.transform;
    if (/^BP_(ResourceNode|ResourceNodeGeyser|FrackingSatellite)/.test(cls)) {
      nodes.push({ id: tail(obj.instanceName), x: round(t.x), y: round(t.y), z: round(t.z) });
      continue;
    }
    if (cls === 'Char_Player_C') {
      players.push({ name: value(obj, 'mCachedPlayerName') || '', x: round(t.x), y: round(t.y), z: round(t.z) });
      continue;
    }
    if (sp?.type === 'PowerLineSpecialProperties') {
      const loc = prop(obj, 'mWireInstances')?.values?.[0]?.properties?.Locations;
      if (loc?.length === 2) {
        const [a, b] = loc.map((l) => l.value);
        wires.push([round(a.x), round(a.y), round(a.z), round(b.x), round(b.y), round(b.z)]);
      }
      continue;
    }
    const line = spline(obj);
    if (line) {
      (lines[cls] ||= []).push(line);
      continue;
    }
    if (t.x === 0 && t.y === 0 && t.z === 0) continue;
    let extra = classOf(value(obj, 'mCurrentRecipe')?.pathName);
    if (cls === 'BP_DropPod_C') extra = value(obj, 'mHasBeenOpened') ? 'open' : 'closed';
    thing(cls, t, q, extra);
  }
}

const h = save.header;
fs.writeFileSync(output, JSON.stringify({
  meta: {
    session: h.sessionName, name: h.saveName || '', map: h.mapName, saveVersion: h.saveVersion, build: h.buildVersion,
    seconds: h.playDurationSeconds, savedAt: Number(h.saveDateTime), creative: !!h.creativeModeEnabled,
    modded: !!h.isModdedSave,
  },
  things, lines, wires, players, used: [...used],
  nodes: nodes.map((n) => ({ ...n, used: used.has(n.id) })),
}));
