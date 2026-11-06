/* Karte der Spielwelt (eigene Seite). Gezeichnet wird auf einem Canvas und nur, wenn sich etwas ändert.
   Neue Ebenen kommen aus layers.py, hier muss dafür nichts geändert werden.
   Dazu kommen die Zeichnungen (Planung): Sie liegen in Spielkoordinaten auf dem Server und alle sehen sie. */
(function () {
  /* Geladene Welt bleibt beim Seitenwechsel im Speicher, solange der Stand gleich ist */
  const cache = { at: null, world: null };
  let current = null;  // Karte auf der aktuellen Seite

  const ICON_BASE = "/static/icons/";
  /* Ältere world.json (vor den Icons) haben kein Feld "icon", dann hilft der Name weiter */
  const NODE_ICONS = {
    "Iron Ore": "iron", "Copper Ore": "copper", Limestone: "stone", Coal: "coal", "Caterium Ore": "gold",
    "Crude Oil": "oil", Sulfur: "sulfur", Bauxite: "bauxite", "Raw Quartz": "quartz", Uranium: "uranium",
    SAM: "sam", "Nitrogen Gas": "nitrogen", Water: "water", Geysir: "geyser", "Crude Oil Well": "oil", LiquidOilWell: "oil",
  };
  const WORLD_ICONS = { drop_closed: "harddrive", drop_open: "harddrive", somersloops: "somersloop", mercer: "mercer" };
  /* Reinheit wie auf den üblichen Satisfactory-Karten: rot unrein, gelb normal, grün rein */
  const PURITIES = [[2, "Rein", "#5fd068"], [1, "Normal", "#f2b33d"], [0.5, "Unrein", "#e8564a"]];
  const PURITY_COLOR = { 2: "#5fd068", 1: "#f2b33d", 0.5: "#e8564a" };
  const PLAYER_COLORS = ["#00d2ff", "#2ecc71", "#f39c12", "#e74c3c", "#9b59b6", "#1abc9c", "#f1c40f"];
  const DRAW_COLORS = ["#ff4d4d", "#ff9f1a", "#ffe14d", "#5fd068", "#2fb8ff", "#b36bff", "#ffffff"];
  const DRAW_WIDTHS = [[2, "Dünn"], [4, "Mittel"], [8, "Dick"]];
  const GROUP_ORDER = ["Planung", "Vorkommen", "Welt", "Produktion", "Strom", "Logistik", "Verkehr", "Bauwerke"];

  function iconName(l) {
    if (!l) return "";
    if (l.icon !== undefined) return l.icon;
    if (l.id && l.id.startsWith("node:")) return NODE_ICONS[l.label] ? `items/${NODE_ICONS[l.label]}.png` : "";
    if (WORLD_ICONS[l.id]) return `items/${WORLD_ICONS[l.id]}.png`;
    return l.id === "players" || l.id === "marks" ? "" : `buildings/${l.id}.png`;
  }

  function init(root) {
    let alive = true;  // Nach dem Seitenwechsel laufen keine alten Abrufe mehr weiter
    const canvas = root.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const panel = root.querySelector(".s-map-layers");
    const info = root.querySelector(".s-map-info");
    const status = root.querySelector("#s-map-status") || document.getElementById("s-map-status");
    const DEFAULT_BOUNDS = { x: -324698.832031, y: -375000.0, size: 750000.0 };
    const STRIDE = { rect: 6, dot: 3, node: 5, player: 4 };
    const STORE = "satis.karte.ebenen";

    const icons = new Map();
    function icon(l) {
      const name = iconName(l);
      if (!name) return null;
      if (!icons.has(name)) {
        const img = new Image();
        img.onload = () => redraw();
        img.src = ICON_BASE + name;
        icons.set(name, img);
      }
      const img = icons.get(name);
      return img.complete && img.naturalWidth > 0 ? img : null;
    }

    let world = null;
    let image = null;

    /* Schärfere Karten als Kacheln: beim Reinzoomen wird nur der sichtbare Bereich in der passenden Stufe
       nachgeladen. Bis die feinere Stufe da ist, bleibt die gröbere stehen. */
    let tileLevels = {};
    try { tileLevels = JSON.parse(root.dataset.tiles || "{}"); } catch (e) { tileLevels = {}; }
    const BASES = [["game", "Spielkarte"], ["ground", "Gelände"], ["relief", "Relief"]].filter(([id]) => id in tileLevels);
    const tiles = new Map();  // "karte/z/x/y" -> Image oder "fehlt"
    const TILE_CACHE = 900;
    let view = { x: 0, y: 0, s: 0.001 };
    let queued = false;
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { saved = {}; }
    const keep = () => { try { localStorage.setItem(STORE, JSON.stringify(saved)); } catch (e) { /* voll oder gesperrt */ } };
    const filter = {
      purity: new Set(Array.isArray(saved.purity) ? saved.purity : [0.5, 1, 2]),
      free: !!saved.free,
    };
    const closed = new Set(Array.isArray(saved.closed) ? saved.closed : []);
    let base = saved.base in tileLevels ? saved.base : ("game" in tileLevels ? "game" : (BASES[0] || [null])[0]);

    /* Planung */
    let marks = [];
    let me = null;
    let tool = "move";
    let color = DRAW_COLORS.includes(saved.color) ? saved.color : DRAW_COLORS[0];
    let width = DRAW_WIDTHS.some(([v]) => v === saved.width) ? saved.width : 4;
    let draft = null;

    const size = () => ({ w: canvas.clientWidth, h: canvas.clientHeight });
    const shown = (l) => (l.id in saved ? saved[l.id] : l.on);
    const marksLayer = { id: "marks", label: "Zeichnungen", group: "Planung", color: "#ff4d4d", on: true };
    const bounds = () => (world ? world.bounds : DEFAULT_BOUNDS);

    function redraw() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; draw(); });
    }

    function fit() {
      const { w, h } = size();
      if (w <= 0 || h <= 0) return;
      const b = bounds();
      view = { x: b.x + b.size / 2, y: b.y + b.size / 2, s: Math.min(w, h) / b.size };
      redraw();
    }

    function zoom(factor, px, py) {
      const { w, h } = size();
      if (w <= 0 || h <= 0) return;
      const minScale = Math.min(w, h) / bounds().size / 2;
      const curScale = (view.s && !isNaN(view.s) && view.s > 0) ? view.s : minScale;
      const s = Math.min(0.5, Math.max(minScale, curScale * factor));
      view.x += (px - w / 2) / curScale - (px - w / 2) / s;
      view.y += (py - h / 2) / curScale - (py - h / 2) / s;
      view.s = s;
      redraw();
    }

    function tile(name, z, x, y, load) {
      const key = `${name}/${z}/${x}/${y}`;
      let img = tiles.get(key);
      if (img === undefined) {
        if (!load) return null;
        img = new Image();
        img.onload = () => redraw();
        img.onerror = () => tiles.set(key, "fehlt");
        img.src = `${root.dataset.tileUrl}/${key}.jpg`;
        if (tiles.size >= TILE_CACHE) tiles.delete(tiles.keys().next().value);  // älteste raus
      } else {
        tiles.delete(key);  // zuletzt benutzt nach hinten
      }
      tiles.set(key, img);
      return img !== "fehlt" && img.complete && img.naturalWidth > 0 ? img : null;
    }

    function drawTiles(name, z, sx, sy, w, h, load) {
      const b = bounds();
      const n = 2 ** z, size = b.size / n, px = size * view.s;
      const [x0, y0] = toWorld(0, 0), [x1, y1] = toWorld(w, h);
      const ax = Math.max(0, Math.floor((x0 - b.x) / size)), bx = Math.min(n - 1, Math.floor((x1 - b.x) / size));
      const ay = Math.max(0, Math.floor((y0 - b.y) / size)), by = Math.min(n - 1, Math.floor((y1 - b.y) / size));
      for (let x = ax; x <= bx; x++) {
        for (let y = ay; y <= by; y++) {
          const img = tile(name, z, x, y, load);
          // 1 px überlappen, sonst blitzen feine Fugen zwischen den Kacheln
          if (img) ctx.drawImage(img, Math.floor(sx(b.x + x * size)), Math.floor(sy(b.y + y * size)), Math.ceil(px) + 1, Math.ceil(px) + 1);
        }
      }
    }

    function drawBase(sx, sy, w, h) {
      const b = bounds();
      const max = base ? tileLevels[base] : undefined;
      const whole = () => image && ctx.drawImage(image, sx(b.x), sy(b.y), b.size * view.s, b.size * view.s);
      if (max === undefined) { whole(); return; }
      const ratio = window.devicePixelRatio || 1;
      const z = Math.max(0, Math.min(max, Math.ceil(Math.log2((b.size * view.s * ratio) / 256))));
      // Untergrund: das ganze Bild (Spielkarte) bzw. eine grobe Stufe, dann was schon geladen ist, dann die passende Stufe
      if (base === "game" && image) whole();
      else drawTiles(base, Math.min(z, 2), sx, sy, w, h, true);
      for (let k = Math.min(z, 2) + 1; k < z; k++) drawTiles(base, k, sx, sy, w, h, false);
      if (z > 2 || base !== "game" || !image) drawTiles(base, z, sx, sy, w, h, true);
    }

    function toWorld(px, py) {
      const { w, h } = size();
      return [(px - w / 2) / view.s + view.x, (py - h / 2) / view.s + view.y];
    }

    /* Wie groß Marker gerade sind: ganz rausgezoomt klein, damit sich die Vorkommen nicht stapeln */
    function markerRadius(w, h) {
      const base = Math.min(w, h) / bounds().size;
      return Math.max(6.5, Math.min(16, 8 + Math.log2(Math.max(1, view.s / base)) * 2.2));
    }

    /* Ein Marker wie im Spiel: dunkle Scheibe, Item-Textur, farbiger Rand */
    function badge(x, y, r, img, ring, dim) {
      ctx.globalAlpha = dim ? 0.6 : 1;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(14, 20, 26, 0.92)";
      ctx.fill();
      ctx.lineWidth = Math.max(1.5, r * 0.18);
      ctx.strokeStyle = ring;
      ctx.stroke();
      if (img) {
        const s = r * 1.55;
        ctx.drawImage(img, x - s / 2, y - s / 2, s, s);
      }
      ctx.globalAlpha = 1;
    }

    function check(x, y, r) {
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = "#101820";
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x - r * 0.5, y);
      ctx.lineTo(x - r * 0.1, y + r * 0.45);
      ctx.lineTo(x + r * 0.55, y - r * 0.4);
      ctx.lineWidth = Math.max(1.2, r * 0.3);
      ctx.stroke();
    }

    /* Flächen wie auf den bekannten Satisfactory-Karten: dunkle Füllung, Rand in der Farbe der Ebene.
       Strommasten sind kleine blaue Rauten in fester Größe, damit man die Kabel-Knoten sieht. */
    const WIRE_COLOR = "#c9d1da";  // auch für ältere Welten, in denen die Kabel noch gelb gespeichert sind
    const LINE_WIDTH = { belts: 130, pipes: 160, hyper: 220, rails: 300, roads: 500 };  // echte Breite in cm
    function drawPoles(l, sx, sy, w, h) {
      const it = l.items;
      const r = Math.max(3.5, Math.min(7, view.s * 120));
      ctx.beginPath();
      for (let i = 0; i < it.length; i += 6) {
        const x = sx(it[i]), y = sy(it[i + 1]);
        if (x < -10 || y < -10 || x > w + 10 || y > h + 10) continue;
        ctx.moveTo(x, y - r);
        ctx.lineTo(x + r, y);
        ctx.lineTo(x, y + r);
        ctx.lineTo(x - r, y);
        ctx.closePath();
      }
      ctx.fillStyle = "rgba(10, 20, 60, .55)";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#2f5cff";
      ctx.stroke();
    }

    /* Echte Umrisse aus den Spielmodellen (layers.py: world.shapes / labelClass). Ohne Umriss: Rechteck. */
    function shapeOf(labelIdx) {
      const cls = world && world.labelClass && world.labelClass[labelIdx];
      return (cls && world.shapes && world.shapes[cls]) || null;
    }
    function classOf(labelIdx) {
      return (world && world.labelClass && world.labelClass[labelIdx]) || "";
    }
    const buildingIcons = new Map();
    function buildingIcon(cls) {
      if (!cls) return null;
      let img = buildingIcons.get(cls);
      if (!img) {
        img = new Image();
        img.onload = () => redraw();
        img.src = `${ICON_BASE}building/${cls.replace(/^Build_/, "Desc_")}.png`;
        buildingIcons.set(cls, img);
      }
      return img.complete && img.naturalWidth > 0 ? img : null;
    }

    // Pfad eines Gebäudes: Umriss oder Rechteck, gedreht und an seiner Stelle
    function buildingPath(it, i, x, y) {
      const a = it[i + 2] * Math.PI / 180, c = Math.cos(a) * view.s, sn = Math.sin(a) * view.s;
      const shape = shapeOf(it[i + 5]);
      if (shape) {
        ctx.moveTo(x + shape[0] * c - shape[1] * sn, y + shape[0] * sn + shape[1] * c);
        for (let k = 2; k < shape.length; k += 2) ctx.lineTo(x + shape[k] * c - shape[k + 1] * sn, y + shape[k] * sn + shape[k + 1] * c);
        ctx.closePath();
        return;
      }
      const lx = it[i + 3] / 2, ly = it[i + 4] / 2;
      ctx.moveTo(x + c * lx - sn * ly, y + sn * lx + c * ly);
      ctx.lineTo(x + c * lx + sn * ly, y + sn * lx - c * ly);
      ctx.lineTo(x - c * lx + sn * ly, y - sn * lx - c * ly);
      ctx.lineTo(x - c * lx - sn * ly, y - sn * lx + c * ly);
      ctx.closePath();
    }

    // Mitte des Umrisses auf dem Bildschirm (Umrisse liegen nicht immer mittig um den Ursprung)
    function buildingCenter(it, i, x, y) {
      const shape = shapeOf(it[i + 5]);
      if (!shape) return [x, y];
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (let k = 0; k < shape.length; k += 2) {
        minX = Math.min(minX, shape[k]); maxX = Math.max(maxX, shape[k]);
        minY = Math.min(minY, shape[k + 1]); maxY = Math.max(maxY, shape[k + 1]);
      }
      const mx = (minX + maxX) / 2, my = (minY + maxY) / 2, a = it[i + 2] * Math.PI / 180;
      return [x + (mx * Math.cos(a) - my * Math.sin(a)) * view.s, y + (mx * Math.sin(a) + my * Math.cos(a)) * view.s];
    }

    function drawRects(l, sx, sy, w, h) {
      if (l.id === "power_poles") { drawPoles(l, sx, sy, w, h); return; }
      const it = l.items;
      const s = view.s;
      const withIcon = [];
      let big = false;
      ctx.fillStyle = l.color;
      ctx.beginPath();
      for (let i = 0; i < it.length; i += 6) {
        const x = sx(it[i]), y = sy(it[i + 1]);
        const r = Math.max(it[i + 3], it[i + 4]) * s;
        if (x < -r || y < -r || x > w + r || y > h + r) continue;
        if (r < 3) { ctx.rect(x - 1, y - 1, 2, 2); continue; }
        if (r >= 10) big = true;
        buildingPath(it, i, x, y);
        // Icon drauf, sobald das Gebäude groß genug ist (Fundamente, Wände usw. nicht, das wäre nur Gewimmel)
        if (r >= 26 && ICON_LAYERS.has(l.id)) withIcon.push(i);
      }
      if (!big) { ctx.fill(); return; }
      // Nah dran: dunkle Füllung mit Farbe der Ebene drüber und kräftigem Rand
      ctx.fillStyle = "#34495e";
      ctx.fill();
      ctx.globalAlpha = 0.35;
      ctx.fillStyle = l.color;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.lineJoin = "round";
      ctx.lineWidth = 2;
      ctx.strokeStyle = l.color;
      ctx.stroke();
      ctx.lineJoin = "miter";
      withIcon.forEach((i) => {
        const img = buildingIcon(classOf(it[i + 5]));
        if (!img) return;
        const [cx, cy] = buildingCenter(it, i, sx(it[i]), sy(it[i + 1]));
        const size = Math.min(72, Math.min(it[i + 3], it[i + 4]) * s * 0.7);
        if (size < 14) return;
        ctx.drawImage(img, cx - size / 2, cy - size / 2, size, size);
      });
    }
    const ICON_LAYERS = new Set(["factories", "miners", "generators", "storage", "base", "stations", "pipe_parts",
      "attachments", "vehicles", "lifts"]);

    function outline(it, i, sx, sy) {
      const x = sx(it[i]), y = sy(it[i + 1]);
      ctx.save();
      ctx.lineWidth = 3;
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#ffffff";
      ctx.shadowColor = "rgba(0, 0, 0, .8)";
      ctx.shadowBlur = 4;
      ctx.beginPath();
      if (Math.max(it[i + 3], it[i + 4]) * view.s < 8) ctx.arc(x, y, 6, 0, Math.PI * 2);
      else buildingPath(it, i, x, y);
      ctx.stroke();
      ctx.restore();
    }

    function drawLines(l, sx, sy) {
      if (l.id === "wires") {
        ctx.beginPath();
        for (const line of l.items) {
          ctx.moveTo(sx(line[0]), sy(line[1]));
          for (let i = 2; i < line.length; i += 2) ctx.lineTo(sx(line[i]), sy(line[i + 1]));
        }
        ctx.strokeStyle = WIRE_COLOR;
        ctx.lineWidth = lineWidth(l);
        ctx.stroke();
        return;
      }
      ctx.strokeStyle = l.color;
      // Rausgezoomt dünne Striche, nah dran so breit wie im Spiel
      ctx.lineWidth = lineWidth(l);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      for (const line of l.items) {
        ctx.moveTo(sx(line[0]), sy(line[1]));
        for (let i = 2; i < line.length; i += 2) ctx.lineTo(sx(line[i]), sy(line[i + 1]));
      }
      ctx.stroke();
      ctx.lineCap = "butt";
      ctx.lineJoin = "miter";
    }

    function lineWidth(l) {
      if (l.id === "wires") return Math.min(2, Math.max(1, view.s * 25));
      return Math.min(40, Math.max(view.s * (LINE_WIDTH[l.id] || 150), Math.min(4, Math.max(1, view.s * 150))));
    }

    const visibleNode = (it, i) => filter.purity.has(it[i + 3]) && !(filter.free && it[i + 4]);

    function drawNodes(l, sx, sy, w, h) {
      const it = l.items;
      const img = icon(l);
      const base = markerRadius(w, h);
      for (let i = 0; i < it.length; i += 5) {
        if (!visibleNode(it, i)) continue;
        const x = sx(it[i]), y = sy(it[i + 1]);
        const r = base * (it[i + 3] === 2 ? 1.12 : it[i + 3] === 1 ? 1 : 0.9);
        if (x < -r || y < -r || x > w + r || y > h + r) continue;
        const used = !!it[i + 4];
        badge(x, y, r, img, PURITY_COLOR[it[i + 3]] || l.color, used);
        if (!img) {  // Icon fehlt oder lädt noch: Rohstoff-Farbe als Füllung
          ctx.beginPath();
          ctx.arc(x, y, r * 0.55, 0, Math.PI * 2);
          ctx.fillStyle = l.color;
          ctx.fill();
        }
        if (used && r > 7) check(x + r * 0.72, y + r * 0.72, Math.max(3.5, r * 0.38));
      }
    }

    function drawDots(l, sx, sy, w, h) {
      const it = l.items;
      const img = icon(l);
      const r = markerRadius(w, h) * 0.95;
      for (let i = 0; i < it.length; i += 3) {
        const x = sx(it[i]), y = sy(it[i + 1]);
        if (x < -r || y < -r || x > w + r || y > h + r) continue;
        badge(x, y, r, img, l.color, l.id === "drop_open");
        if (!img) {
          ctx.beginPath();
          ctx.arc(x, y, r * 0.5, 0, Math.PI * 2);
          ctx.fillStyle = l.color;
          ctx.fill();
        }
      }
    }

    /* Laufrichtung der Bänder: kleine Pfeile entlang der Linie, sobald man nah genug dran ist */
    function drawArrows(l, sx, sy, w, h) {
      if (view.s < 0.012) return;
      const gap = 46;  // Abstand der Pfeile in Pixeln
      const size = Math.min(12, Math.max(3, lineWidth(l) * 0.45, view.s * 120 > 5 ? 5 : view.s * 120));
      ctx.fillStyle = "rgba(20, 16, 8, .85)";
      ctx.beginPath();
      for (const line of l.items) {
        let carry = gap / 2;
        for (let i = 2; i < line.length; i += 2) {
          const x1 = sx(line[i - 2]), y1 = sy(line[i - 1]), x2 = sx(line[i]), y2 = sy(line[i + 1]);
          const len = Math.hypot(x2 - x1, y2 - y1);
          if ((x1 < -20 && x2 < -20) || (y1 < -20 && y2 < -20) || (x1 > w + 20 && x2 > w + 20) || (y1 > h + 20 && y2 > h + 20)) {
            carry = (carry - len) % gap;
            if (carry < 0) carry += gap;
            continue;
          }
          const ux = (x2 - x1) / (len || 1), uy = (y2 - y1) / (len || 1);
          for (let d = carry; d < len; d += gap) {
            const px = x1 + ux * d, py = y1 + uy * d;
            ctx.moveTo(px + ux * size, py + uy * size);
            ctx.lineTo(px - ux * size - uy * size, py - uy * size + ux * size);
            ctx.lineTo(px - ux * size * 0.3, py - uy * size * 0.3);
            ctx.lineTo(px - ux * size + uy * size, py - uy * size - ux * size);
            ctx.closePath();
          }
          carry = ((carry - len) % gap + gap) % gap;
        }
      }
      ctx.fill();
    }

    /* Spieler wie auf der Karte im Spiel: runder Marker mit Pionier, Stiel zur genauen Position,
       dort ein kleiner Kegel in Blickrichtung */
    const PLAYER_HEAD = { dx: -18, dy: -30, r: 15 };
    // Das Pionier-Symbol kommt aus Font Awesome, die Schrift lädt evtl. erst nach dem ersten Zeichnen
    if (document.fonts && document.fonts.load) document.fonts.load('900 15px "Font Awesome 5 Free"').then(() => redraw()).catch(() => {});
    function drawPlayers(l, sx, sy, w, h) {
      const it = l.items;
      const stride = it.length % 4 === 0 ? 4 : 3;
      for (let i = 0, n = 0; i < it.length; i += stride, n++) {
        const px = sx(it[i]), py = sy(it[i + 1]);
        if (px < -80 || py < -80 || px > w + 80 || py > h + 80) continue;
        const a = ((stride === 4 ? it[i + 2] : 0) * Math.PI) / 180;
        const name = (world.labels && world.labels[it[i + stride - 1]]) || "Spieler";
        const color = PLAYER_COLORS[n % PLAYER_COLORS.length];
        const active = hovered && hovered.type === "player" && hovered.i === i;
        const { dx, dy, r } = PLAYER_HEAD;
        ctx.save();
        ctx.translate(px, py);

        // Blickrichtung
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, 26, a - 0.45, a + 0.45);
        ctx.closePath();
        const grad = ctx.createRadialGradient(0, 0, 2, 0, 0, 26);
        grad.addColorStop(0, color + "aa");
        grad.addColorStop(1, color + "00");
        ctx.fillStyle = grad;
        ctx.fill();

        // Stiel und Punkt
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(dx * 0.6, dy * 0.6);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(0, 0, 4, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(0, 0, 2.2, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Kopf: dunkle Scheibe, weißer Ring, Pionier
        ctx.shadowColor = "rgba(0, 0, 0, .55)";
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(dx, dy, r, 0, Math.PI * 2);
        ctx.fillStyle = "#4b5258";
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.lineWidth = active ? 4 : 3;
        ctx.strokeStyle = active ? color : "#ffffff";
        ctx.stroke();
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = '900 15px "Font Awesome 5 Free"';
        ctx.fillText("", dx, dy + 1);  // fa-user-astronaut

        // Name
        ctx.font = "bold 12px Lato, sans-serif";
        const bw = ctx.measureText(name).width + 12;
        const bx = dx + r + 4, by = dy - 9;
        ctx.fillStyle = "rgba(16, 24, 32, .88)";
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(bx, by, bw, 18, 4); else ctx.rect(bx, by, bw, 18);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "left";
        ctx.fillText(name, bx + 6, by + 9.5);
        ctx.restore();
      }
    }

    /* ------------------------------------------------------------ Zeichnungen */
    function markPath(m, sx, sy) {
      const p = m.points;
      ctx.beginPath();
      if (m.kind === "rect") {
        const x = sx(Math.min(p[0], p[2])), y = sy(Math.min(p[1], p[3]));
        ctx.rect(x, y, Math.abs(p[2] - p[0]) * view.s, Math.abs(p[3] - p[1]) * view.s);
        return;
      }
      ctx.moveTo(sx(p[0]), sy(p[1]));
      if (p.length === 2) ctx.lineTo(sx(p[0]) + 0.1, sy(p[1]));  // einzelner Punkt mit dem Stift
      for (let i = 2; i < p.length; i += 2) ctx.lineTo(sx(p[i]), sy(p[i + 1]));
    }

    function drawPin(m, sx, sy) {
      const x = sx(m.points[0]), y = sy(m.points[1]);
      ctx.save();
      ctx.translate(x, y);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.bezierCurveTo(-3, -8, -10, -12, -10, -20);
      ctx.arc(0, -20, 10, Math.PI, 0);
      ctx.bezierCurveTo(10, -12, 3, -8, 0, 0);
      ctx.closePath();
      ctx.fillStyle = m.color;
      ctx.strokeStyle = "#101820";
      ctx.lineWidth = 1.5;
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, -20, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = "#101820";
      ctx.fill();
      if (m.text) {
        ctx.font = "bold 12px Lato, sans-serif";
        const tw = ctx.measureText(m.text).width;
        const bw = tw + 12, bh = 19, bx = 14, by = -30;
        ctx.fillStyle = "rgba(16, 24, 32, 0.9)";
        ctx.strokeStyle = m.color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(bx, by, bw, bh, 4); else ctx.rect(bx, by, bw, bh);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(m.text, bx + 6, by + bh / 2);
      }
      ctx.restore();
    }

    function drawMark(m, sx, sy) {
      if (m.kind === "pin") { drawPin(m, sx, sy); return; }
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      // Dunkler Saum, damit die Linie auf hellem und dunklem Gelände lesbar bleibt
      markPath(m, sx, sy);
      if (m.kind === "rect") {
        ctx.fillStyle = m.color + "26";
        ctx.fill();
      }
      ctx.strokeStyle = "rgba(0, 0, 0, 0.55)";
      ctx.lineWidth = m.width + 2;
      ctx.stroke();
      ctx.strokeStyle = m.color;
      ctx.lineWidth = m.width;
      ctx.stroke();
      ctx.lineCap = "butt";
      ctx.lineJoin = "miter";
    }

    function draw() {
      const { w, h } = size();
      if (w <= 0 || h <= 0) return;
      if (!view.s || isNaN(view.s) || view.s <= 0 || isNaN(view.x) || isNaN(view.y)) fit();
      const ratio = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
        canvas.width = Math.round(w * ratio);
        canvas.height = Math.round(h * ratio);
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.fillStyle = "#1b2a33";
      ctx.fillRect(0, 0, w, h);

      const b = bounds();
      const sx = (x) => (x - view.x) * view.s + w / 2;
      const sy = (y) => (y - view.y) * view.s + h / 2;
      ctx.imageSmoothingQuality = "high";
      drawBase(sx, sy, w, h);

      const painters = { rect: drawRects, line: drawLines, node: drawNodes, dot: drawDots, player: drawPlayers };
      const order = { rect: 0, line: 1, node: 2, dot: 3, player: 5 };
      const layers = world ? [...world.layers].sort((a, c) => order[a.kind] - order[c.kind]) : [];
      layers.forEach((l) => {
        if (l.kind === "player" || !shown(l) || !painters[l.kind]) return;
        painters[l.kind](l, sx, sy, w, h);
        if (l.id === "belts") drawArrows(l, sx, sy, w, h);
      });
      // Planung über der Welt, Spieler ganz oben
      if (shown(marksLayer)) marks.forEach((m) => drawMark(m, sx, sy));
      if (draft) drawMark(draft, sx, sy);
      highlight(sx, sy);
      layers.forEach((l) => { if (l.kind === "player" && shown(l)) drawPlayers(l, sx, sy, w, h); });
    }

    function segment(px, py, x1, y1, x2, y2) {
      const dx = x2 - x1, dy = y2 - y1;
      const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy || 1)));
      return Math.hypot(px - x1 - t * dx, py - y1 - t * dy);
    }

    /* Welche Zeichnung liegt unter dem Zeiger (Abstand in Bildschirmpixeln)? Die neueste gewinnt. */
    function markAt(px, py) {
      if (!shown(marksLayer)) return null;
      const [wx, wy] = toWorld(px, py);
      for (let k = marks.length - 1; k >= 0; k--) {
        const m = marks[k], p = m.points;
        const reach = (Math.max(6, m.width / 2 + 4)) / view.s;
        if (m.kind === "pin") {
          if (Math.hypot(p[0] - wx, p[1] - 20 / view.s - wy) < 13 / view.s) return m;
          continue;
        }
        if (m.kind === "rect") {
          const x1 = Math.min(p[0], p[2]), x2 = Math.max(p[0], p[2]), y1 = Math.min(p[1], p[3]), y2 = Math.max(p[1], p[3]);
          if (wx > x1 - reach && wx < x2 + reach && wy > y1 - reach && wy < y2 + reach) return m;
          continue;
        }
        if (p.length === 2 && Math.hypot(p[0] - wx, p[1] - wy) < reach) return m;
        for (let i = 2; i < p.length; i += 2) {
          if (segment(wx, wy, p[i - 2], p[i - 1], p[i], p[i + 1]) < reach) return m;
        }
      }
      return null;
    }

    /* Was liegt unter dem Klick? Punkte gehen vor Gebäuden, Gebäude vor Linien. */
    function pick(px, py) {
      if (!world) return "";
      const [wx, wy] = toWorld(px, py);
      const reach = Math.max(10, markerRadius(size().w, size().h)) / view.s;
      let best = "", score = Infinity;
      for (const l of world.layers) {
        if (!shown(l)) continue;
        const isPlayer = l.kind === "player";
        const rank = (isPlayer ? 0 : { node: 0, dot: 0, rect: 1, line: 2 }[l.kind]) * reach;
        if (l.kind === "line") {
          for (const line of l.items) {
            for (let i = 2; i < line.length; i += 2) {
              const d = segment(wx, wy, line[i - 2], line[i - 1], line[i], line[i + 1]);
              if (d < reach && d + rank < score) { score = d + rank; best = l.label; }
            }
          }
          continue;
        }
        const playerStride = isPlayer && (l.items.length % 4 === 0) ? 4 : 3;
        const step = isPlayer ? playerStride : STRIDE[l.kind];
        const it = l.items;
        const at = l.kind === "rect" ? 5 : isPlayer ? playerStride - 1 : 2;
        for (let i = 0; i < it.length; i += step) {
          if (l.kind === "node" && !visibleNode(it, i)) continue;
          const pad = l.kind === "rect" ? Math.max(it[i + 3], it[i + 4]) / 2 : isPlayer ? 18 / view.s : 0;
          const d = Math.max(0, Math.hypot(it[i] - wx, it[i + 1] - wy) - pad);
          if (d < reach && d + rank < score) { score = d + rank; best = world.labels[it[i + at]]; }
        }
      }
      return best;
    }

    function showInfo(text) {
      info.textContent = text;
      info.hidden = !text;
    }

    function describeMark(m) {
      const what = { pen: "Skizze", line: "Linie", rect: "Bereich", pin: "Markierung" }[m.kind];
      return `${what}${m.text ? ` „${m.text}“` : ""} von ${m.by}`;
    }

    /* ------------------------------------------------------------ Zeichnungen laden und speichern */
    function api(url, options) {
      return fetch(url, Object.assign({ credentials: "same-origin", cache: "no-store" }, options)).then((res) =>
        res.json().catch(() => ({})).then((data) => {
          if (!res.ok) throw new Error(data.error || "Das hat nicht geklappt.");
          return data;
        }));
    }

    function loadMarks() {
      if (!root.dataset.marks) return Promise.resolve();
      return api(root.dataset.marks).then((data) => {
        if (!alive) return;
        // Eigene, noch nicht bestätigte Zeichnungen bleiben stehen
        marks = data.marks.concat(marks.filter((m) => m.pending));
        me = data.me;
        updateMarkCount();
        redraw();
      }).catch(() => {});
    }

    function saveMark(m) {
      m.pending = true;
      m.by = "dir";
      marks.push(m);
      redraw();
      api(root.dataset.marks, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf },
        body: JSON.stringify({ kind: m.kind, color: m.color, width: m.width, points: m.points, text: m.text || "" }),
      }).then((saved) => {
        const i = marks.indexOf(m);
        if (i >= 0) marks[i] = saved; else marks.push(saved);
        updateMarkCount();
        redraw();
      }).catch((err) => {
        marks = marks.filter((x) => x !== m);
        showInfo(err.message);
        redraw();
      });
    }

    function deleteMark(m) {
      if (m.pending) return;
      if (me !== null && m.byId !== me && !window.confirm(`${describeMark(m)} löschen?`)) return;
      marks = marks.filter((x) => x !== m);
      updateMarkCount();
      redraw();
      api(`${root.dataset.marks}/${m.id}`, { method: "DELETE", headers: { "X-CSRF-Token": root.dataset.csrf } })
        .then(() => showInfo(`${describeMark(m)} gelöscht.`))
        .catch((err) => { showInfo(err.message); loadMarks(); });
    }

    /* ------------------------------------------------------------ Hover
       Maschinen, Bänder, Rohre, Vorkommen und Spieler zeigen beim Drüberfahren, was los ist.
       Am Handy reicht Antippen. Daten kommen aus layers.py ("details"). */
    const tip = document.createElement("div");
    tip.className = "s-map-tip";
    tip.hidden = true;
    canvas.parentNode.append(tip);
    let hovered = null;  // { type, l, i } = Art, Ebene und Startindex im items-Array
    const HOLDS = new Set(["factories", "miners", "generators", "storage", "stations", "vehicles"]);  // haben ein Inventar
    const BACKDROP = new Set(["foundations", "walls", "beams", "walkways"]);  // Untergrund: alles andere darauf geht vor
    const PARTS = { in: "Eingang", out: "Ausgang", fuel: "Brennstoff", store: "Lager", boost: "Shards und Somersloops" };
    const PURITY_NAME = { 2: "Rein", 1: "Normal", 0.5: "Unrein" };
    const effColor = (e) => (e >= 95 ? "#5fd068" : e >= 50 ? "#f2b33d" : "#e8564a");
    const detail = (h) => (h.l.details && h.l.details[String(h.i / (h.type === "line" ? 1 : STRIDE_OF[h.type]))]) || null;
    const STRIDE_OF = { rect: 6, player: 4, node: 5, dot: 3 };

    // Punkt im Umriss? Umrisse sind konvex: liegt der Punkt links von jeder Kante (mit etwas Spielraum)
    function insideShape(shape, x, y, pad) {
      let sign = 0;
      for (let k = 0; k < shape.length; k += 2) {
        const ax = shape[k], ay = shape[k + 1];
        const bx = shape[(k + 2) % shape.length], by = shape[(k + 3) % shape.length];
        const len = Math.hypot(bx - ax, by - ay) || 1;
        const d = ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / len;
        if (!sign) sign = d >= 0 ? 1 : -1;
        if (d * sign < -pad) return false;
      }
      return true;
    }

    /* Was liegt unter dem Zeiger? Spieler vor Vorkommen vor Gebäuden vor Linien. */
    function hitAt(px, py) {
      if (!world) return null;
      const [wx, wy] = toWorld(px, py);
      const { w, h } = size();
      for (const l of world.layers) {
        if (l.kind !== "player" || !shown(l) || l.items.length % 4) continue;
        for (let i = 0; i < l.items.length; i += 4) {
          const x = (l.items[i] - view.x) * view.s + w / 2, y = (l.items[i + 1] - view.y) * view.s + h / 2;
          const { dx, dy, r } = PLAYER_HEAD;
          if (Math.hypot(px - x - dx, py - y - dy) <= r + 3 || Math.hypot(px - x, py - y) <= 7) return { type: "player", l, i };
        }
      }
      const radius = markerRadius(w, h);
      let best = null, dist = Infinity;
      for (const l of world.layers) {
        if (l.kind !== "node" || !shown(l)) continue;
        for (let i = 0; i < l.items.length; i += 5) {
          if (!visibleNode(l.items, i)) continue;
          const d = Math.hypot(l.items[i] - wx, l.items[i + 1] - wy) * view.s;
          if (d <= radius * 1.1 && d < dist) { dist = d; best = { type: "node", l, i }; }
        }
      }
      const node = best;
      best = null;
      for (const l of world.layers) {
        if (l.kind !== "dot" || !shown(l)) continue;
        for (let i = 0; i < l.items.length; i += 3) {
          const d = Math.hypot(l.items[i] - wx, l.items[i + 1] - wy) * view.s;
          if (d <= radius && d < dist) { dist = d; best = { type: "dot", l, i }; }
        }
      }
      if (best) return best;
      dist = Infinity;
      const rectAt = (backdrop) => {
        let found = null, area = Infinity;
        for (const l of world.layers) {
          if (l.kind !== "rect" || BACKDROP.has(l.id) !== backdrop || !shown(l)) continue;
          const it = l.items;
          const pad = (l.id === "power_poles" ? 7 : 3) / view.s;  // Masten sind größer gezeichnet, als sie sind
          for (let i = 0; i < it.length; i += 6) {
            const dx = wx - it[i], dy = wy - it[i + 1], reach = it[i + 3] + it[i + 4] + pad;
            if (Math.abs(dx) > reach || Math.abs(dy) > reach) continue;
            const a = it[i + 2] * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
            const lx = dx * c + dy * s, ly = -dx * s + dy * c;
            const shape = shapeOf(it[i + 5]);
            if (shape ? insideShape(shape, lx, ly, pad) : Math.abs(lx) <= it[i + 3] / 2 + pad && Math.abs(ly) <= it[i + 4] / 2 + pad) {
              const sz = it[i + 3] * it[i + 4];  // übereinander (Lager auf Pfeiler): das kleinere gewinnt
              if (sz < area) { area = sz; found = { type: "rect", l, i }; }
            }
          }
        }
        return found;
      };
      best = rectAt(false);
      // Ein Miner steht auf seinem Vorkommen: dann zeigt der Hover den Miner, sonst das Vorkommen
      if (best && (!node || best.l.id === "miners")) return best;
      if (node) return node;
      for (const l of world.layers) {
        if (l.kind !== "line" || !shown(l)) continue;
        const reach = (l.id === "wires" ? 5 : 6) / view.s;
        l.items.forEach((line, n) => {
          for (let i = 2; i < line.length; i += 2) {
            const x1 = line[i - 2], y1 = line[i - 1], x2 = line[i], y2 = line[i + 1];
            if (wx < Math.min(x1, x2) - reach || wx > Math.max(x1, x2) + reach
                || wy < Math.min(y1, y2) - reach || wy > Math.max(y1, y2) + reach) continue;
            const d = segment(wx, wy, x1, y1, x2, y2);
            if (d < reach && d < dist) { dist = d; best = { type: "line", l, i: n }; }
          }
        });
      }
      return best || rectAt(true);  // Fundamente und Wände zuletzt, sonst wären Bänder darauf nicht erreichbar
    }

    const el = (tag, cls, text) => {
      const e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text !== undefined) e.textContent = text;
      return e;
    };
    function iconImg(src, cls, fallback) {
      const img = el("img", cls);
      img.alt = "";
      img.onerror = () => {
        if (fallback && img.getAttribute("src") !== fallback) img.src = fallback;
        else img.style.visibility = "hidden";
      };
      img.src = src;
      return img;
    }
    const itemName = (cls) => ((world.items && world.items[cls]) || [cls.replace(/^(Desc_|BP_EquipmentDescriptor)|_C$/g, ""), false]);
    const amount = (n, liquid) => (liquid ? `${n.toLocaleString("de-DE", { maximumFractionDigits: 1 })} m³` : n.toLocaleString("de-DE"));

    function header(icon, title, sub, fallback) {
      const head = el("div", "s-map-tip-head");
      if (icon) head.append(iconImg(icon, "", fallback));
      const t = el("div");
      t.append(el("strong", "", title));
      if (sub) t.append(el("div", "s-map-tip-sub", sub));
      head.append(t);
      tip.append(head);
    }
    function facts(list) {
      if (!list.length) return;
      const row = el("div", "s-map-tip-facts");
      list.forEach(([text, c]) => {
        const f = el("span", "", text);
        f.style.borderColor = c;
        f.style.color = c;
        row.append(f);
      });
      tip.append(row);
    }
    function itemRows(title, rows) {
      tip.append(el("div", "s-map-tip-part", title));
      rows.forEach(([cls, n]) => {
        const [name, liquid] = itemName(cls);
        const r = el("div", "s-map-tip-row");
        r.append(iconImg(`${ICON_BASE}item/${cls}.png`), el("span", "", name), el("span", "s-map-tip-n", amount(n, liquid)));
        tip.append(r);
      });
    }
    /* Slots wie im Spiel: Kästchen mit Icon und Anzahl unten rechts */
    function grid(title, cells, columns) {
      tip.append(el("div", "s-map-tip-part", title));
      const g = el("div", "s-map-tip-grid");
      g.style.gridTemplateColumns = `repeat(${columns}, 1fr)`;
      cells.forEach((c) => {
        const cell = el("div", "s-map-tip-slot");
        if (c) {
          cell.title = c.title;
          cell.append(iconImg(c.icon));
          if (c.n > 1) cell.append(el("span", "", c.n.toLocaleString("de-DE")));
        }
        g.append(cell);
      });
      tip.append(g);
    }

    const RUNS = new Set(["factories", "miners", "generators"]);  // Maschinen mit Takt
    const MINER_RATE = [[/Miner Mk\.?1|MinerMk1/i, 60], [/Miner Mk\.?2|MinerMk2/i, 120], [/Miner Mk\.?3|MinerMk3/i, 240],
      [/Oil (Extractor|Pump)|OilPump/i, 120], [/Water Extractor|WaterPump/i, 120]];  // pro Minute auf normalem Vorkommen

    function fillRect(h, d) {
      const { l, i } = h;
      const label = world.labels[l.items[i + 5]] || l.label;
      const [name, recipeFromLabel] = label.includes(": ") ? label.split(/: (.*)/s) : [label, ""];
      d = d || {};
      const recipe = d.recipe || recipeFromLabel;
      const clock = d.clock !== undefined ? d.clock : 100;  // 100 % stehen nicht im Spielstand
      const shards = {}, slots = (d.inv || []).find(([part]) => part === "boost");
      if (slots) slots[1].forEach(([cls, n]) => { shards[cls] = n; });

      let sub = recipe || l.label;
      if (!recipe && l.id === "factories") sub = "Kein Rezept eingestellt";
      if (d.mines) sub = `baut ab: ${itemName(d.mines[0])[0]} (${PURITY_NAME[d.mines[1]] || "?"})`;
      const cls = classOf(l.items[i + 5]);
      const layerIcon = ICON_BASE + iconName(l);
      header(cls ? `${ICON_BASE}building/${cls.replace(/^Build_/, "Desc_")}.png` : layerIcon, name, sub, layerIcon);
      if (!recipe && l.id === "factories") tip.querySelector(".s-map-tip-sub").style.color = "#e8564a";

      const list = [];
      if (d.paused) list.push(["Pausiert", "#f2b33d"]);
      if (RUNS.has(l.id)) {
        const c = clock > 100.05 ? "#d070ff" : clock < 99.95 ? "#2fb8ff" : "#aaaaaa";
        const word = clock > 100.05 ? " übertaktet" : clock < 99.95 ? " gedrosselt" : "";
        list.push([`Takt ${clock.toLocaleString("de-DE")} %${word}`, c]);
      }
      if (shards.Desc_CrystalShard_C) list.push([`${shards.Desc_CrystalShard_C} × Power Shard`, "#d070ff"]);
      if (shards.Desc_WAT1_C) list.push([`${shards.Desc_WAT1_C} × Somersloop`, "#d040d0"]);
      if (d.boost !== undefined) list.push([`Ausgabe ×${d.boost.toLocaleString("de-DE")}`, "#d040d0"]);
      if (d.eff !== undefined) list.push([d.eff === 0 && !d.paused ? "Steht still" : `Auslastung ${d.eff} %`, effColor(d.eff)]);
      if (d.prog !== undefined) list.push([`Fortschritt ${d.prog} %`, "#aaaaaa"]);
      if (d.power) {
        const mw = d.power * (clock / 100) ** 1.321928 * (d.boost ? d.boost ** 2 : 1);
        list.push([`≈ ${mw.toLocaleString("de-DE", { maximumFractionDigits: 1 })} MW`, "#f2c94c"]);
      }
      facts(list);
      if (d.eff !== undefined) {
        const bar = el("div", "s-map-tip-bar");
        const fill = el("span");
        fill.style.width = `${Math.max(0, Math.min(100, d.eff))}%`;
        fill.style.backgroundColor = effColor(d.eff);
        bar.append(fill);
        tip.append(bar);
      }

      // Soll pro Minute beim eingestellten Takt (Somersloop verdoppelt nur die Ausgabe)
      const scale = clock / 100;
      const perMin = [];
      if (d.rates) {
        d.rates.in.forEach(([cls, n]) => perMin.push([cls, -n * scale]));
        d.rates.out.forEach(([cls, n]) => perMin.push([cls, n * scale * (d.boost || 1)]));
      } else if (d.mines) {
        const base = (MINER_RATE.find(([re]) => re.test(name)) || [null, 0])[1];
        if (base) perMin.push([d.mines[0], base * d.mines[1] * scale]);
      }
      if (perMin.length) {
        tip.append(el("div", "s-map-tip-part", `Pro Minute bei ${clock.toLocaleString("de-DE")} %`));
        perMin.forEach(([cls, n]) => {
          const [itemLabel, liquid] = itemName(cls);
          const r = el("div", "s-map-tip-row");
          const v = el("span", "s-map-tip-n", `${n > 0 ? "+" : "−"}${amount(Math.round(Math.abs(n) * 100) / 100, liquid)}`);
          v.style.color = n > 0 ? "#5fd068" : "#e8564a";
          r.append(iconImg(`${ICON_BASE}item/${cls}.png`), el("span", "", itemLabel), v);
          tip.append(r);
        });
      }
      (d.inv || []).filter(([part]) => part !== "boost").forEach(([part, rows]) => itemRows(PARTS[part] || part, rows));
      if (HOLDS.has(l.id) && !(d.inv || []).some(([part]) => part !== "boost")) tip.append(el("div", "s-map-tip-empty", "Inventar leer"));
      const about = world.about && world.about[cls];
      if (about) tip.append(el("div", "s-map-tip-about", about));
      const m = (v) => (v / 100).toLocaleString("de-DE", { maximumFractionDigits: 1 });
      facts([[`${shapeOf(l.items[i + 5]) ? "" : "≈ "}${m(l.items[i + 3])} × ${m(l.items[i + 4])} m`, "#aaaaaa"], [place(l.items, i), "#aaaaaa"]]);
    }

    const place = (it, i) => `X ${Math.round(it[i] / 100).toLocaleString("de-DE")} m · Y ${Math.round(it[i + 1] / 100).toLocaleString("de-DE")} m`;

    /* Sammelsachen in der Welt: Drop Pods, Somersloops, Mercer-Kugeln */
    function fillDot(h) {
      const { l, i } = h;
      header(ICON_BASE + iconName(l), world.labels[l.items[i + 2]] || l.label, l.label);
      facts([[place(l.items, i), "#aaaaaa"]]);
    }

    function fillWire(d) {
      header(ICON_BASE + "buildings/wires.png", d.name, `${d.len.toLocaleString("de-DE")} m lang`);
      d.ends.forEach(([name, cls], k) => {
        tip.append(el("div", "s-map-tip-part", k ? "Nach" : "Von"));
        const r = el("div", "s-map-tip-row");
        r.append(iconImg(`${ICON_BASE}building/${cls}.png`), el("span", "", name));
        tip.append(r);
      });
    }

    function fillLine(h, d) {
      if (h.l.id === "wires" && d && d.ends) { fillWire(d); return; }
      d = d || { name: h.l.label };
      header(ICON_BASE + iconName(h.l), d.name, h.l.id === "belts" ? "Laufrichtung: siehe Pfeile auf dem Band" : "");
      const list = [];
      if (d.len !== undefined) list.push([`${d.len.toLocaleString("de-DE")} m lang`, "#aaaaaa"]);
      if (d.speed) list.push([`max. ${d.speed.toLocaleString("de-DE")} / min`, "#2fb8ff"]);
      if (d.flow) list.push([`max. ${d.flow} m³/min`, "#2fb8ff"]);
      facts(list);
      if (d.items) itemRows("Gerade auf dem Band", d.items);
      else if (d.fluid !== undefined) {
        tip.append(el("div", "s-map-tip-part", "Im Rohr"));
        tip.append(el("div", "s-map-tip-row s-map-tip-n", `${d.fluid.toLocaleString("de-DE")} m³`));
      } else if (h.l.id === "belts" || h.l.id === "pipes") tip.append(el("div", "s-map-tip-empty", "Leer"));
    }

    function fillNode(h) {
      const { l, i } = h;
      const it = l.items;
      const purity = it[i + 3];
      header(ICON_BASE + iconName(l), `${l.label} (${PURITY_NAME[purity] || "?"})`, it[i + 4] ? "belegt" : "frei");
      facts([[place(it, i), "#aaaaaa"]]);
      const clocks = [50, 100, 150, 200, 250];
      let rows = null, unit = "/ min";
      if (l.node === "ore") rows = [["Miner Mk.1", 30], ["Miner Mk.2", 60], ["Miner Mk.3", 120]];
      else if (l.node === "oil") { rows = [["Ölpumpe", 60]]; unit = "m³/min"; }
      else if (l.node === "well") { rows = [["Druck-Satellit", 30]]; unit = "m³/min"; }
      if (l.node === "geyser") {
        facts([[`Geothermie ≈ ${{ 0.5: 100, 1: 200, 2: 400 }[purity] || 200} MW`, "#5fd068"]]);
        return;
      }
      if (!rows) return;
      const table = el("table", "s-map-tip-table");
      const head = el("tr");
      head.append(el("th", "", ""));
      clocks.forEach((c) => head.append(el("th", "", `${c} %`)));
      table.append(head);
      rows.forEach(([name, base]) => {
        const tr = el("tr");
        tr.append(el("th", "", name));
        clocks.forEach((c) => tr.append(el("td", "", `${(base * purity * 2 * c / 100).toLocaleString("de-DE")}`)));
        table.append(tr);
      });
      tip.append(table);
      tip.append(el("div", "s-map-tip-empty", unit));
    }

    function fillPlayer(h, d) {
      const name = world.labels[h.l.items[h.i + 3]] || "Spieler";
      d = d || {};
      header("", name, d.health !== undefined ? `Gesundheit ${d.health}` : "");
      tip.firstChild.prepend(el("span", "s-map-tip-avatar fas fa-user-astronaut"));
      if (d.equip && d.equip.length) {
        grid("Ausrüstung", d.equip.map((c) => ({ icon: `${ICON_BASE}item/${c}.png`, title: itemName(c)[0], n: 1 })), 6);
      }
      if (d.hotbar) {
        grid("Hotbar", d.hotbar.map((s) => (s ? { icon: `${ICON_BASE}building/${s[1]}.png`, title: s[0], n: 1 } : null)), 10);
      }
      if (d.inv) {
        grid("Inventar", d.inv.map((s) => (s ? { icon: `${ICON_BASE}item/${s[0]}.png`, title: `${itemName(s[0])[0]} × ${s[1]}`, n: s[1] } : null)), 8);
      }
      if (!d.equip && !d.hotbar && !d.inv) tip.append(el("div", "s-map-tip-empty", "Keine Daten zum Inventar im Spielstand"));
    }

    function fillTip(h) {
      tip.replaceChildren();
      tip.classList.toggle("is-wide", h.type === "player" || h.type === "node");
      const d = detail(h);
      if (h.type === "rect") fillRect(h, d);
      else if (h.type === "line") fillLine(h, d);
      else if (h.type === "node") fillNode(h);
      else if (h.type === "dot") fillDot(h);
      else fillPlayer(h, d);
    }

    function placeTip(px, py) {
      const { w, h } = size();
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let x = px + 16, y = py + 16;
      if (x + tw > w - 6) x = Math.max(6, px - tw - 16);
      if (y + th > h - 6) y = Math.max(6, h - th - 6);
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
    }

    const sameHit = (a, b) => a && b && a.type === b.type && a.l === b.l && a.i === b.i;
    function hover(px, py) {
      const hit = hitAt(px, py);
      if (!hit) { hideTip(); return; }
      if (!sameHit(hit, hovered)) { hovered = hit; fillTip(hit); redraw(); }
      placeTip(px, py);
    }

    function hideTip() {
      if (!hovered && tip.hidden) return;
      hovered = null;
      tip.hidden = true;
      redraw();
    }

    /* Hervorhebung des Ziels unter dem Zeiger */
    function highlight(sx, sy) {
      if (!hovered || !shown(hovered.l)) return;
      const { type, l, i } = hovered;
      if (type === "rect") outline(l.items, i, sx, sy);
      else if (type === "line") {
        const line = l.items[i];
        ctx.save();
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(sx(line[0]), sy(line[1]));
        for (let k = 2; k < line.length; k += 2) ctx.lineTo(sx(line[k]), sy(line[k + 1]));
        ctx.strokeStyle = "rgba(255, 255, 255, .9)";
        ctx.lineWidth = lineWidth(l) + 5;
        ctx.stroke();
        ctx.strokeStyle = l.id === "wires" ? WIRE_COLOR : l.color;
        ctx.lineWidth -= 4;
        ctx.stroke();
        ctx.restore();
        if (l.id === "belts") drawArrows({ id: "belts", items: [line] }, sx, sy, Infinity, Infinity);
        if (l.id === "wires") {
          [[line[0], line[1]], [line[line.length - 2], line[line.length - 1]]].forEach(([x, y]) => {
            ctx.beginPath();
            ctx.arc(sx(x), sy(y), 5, 0, Math.PI * 2);
            ctx.fillStyle = "#2f5cff";
            ctx.fill();
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#ffffff";
            ctx.stroke();
          });
        }
      } else if (type === "node" || type === "dot") {
        const r = markerRadius(size().w, size().h) * (type === "dot" ? 0.95 : 1.25);
        ctx.beginPath();
        ctx.arc(sx(l.items[i]), sy(l.items[i + 1]), r + 3, 0, Math.PI * 2);
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();
      }
    }

    let hoverAt = null;
    function queueHover(px, py) {
      const pending = hoverAt;
      hoverAt = [px, py];
      if (pending) return;
      requestAnimationFrame(() => { const [x, y] = hoverAt; hoverAt = null; if (alive) hover(x, y); });
    }
    canvas.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") hideTip(); });

    /* ------------------------------------------------------------ Maus und Finger
       Werkzeug „Verschieben“: ein Zeiger verschiebt, zwei zoomen, ein kurzer Klick zeigt, was dort steht.
       Zeichenwerkzeuge: ein Zeiger zeichnet, zwei Finger verschieben und zoomen weiterhin, die mittlere
       oder rechte Maustaste verschiebt immer. */
    const pointers = new Map();
    let moved = 0, spread = 0, panning = false;
    const local = (e) => {
      const box = canvas.getBoundingClientRect();
      return [e.clientX - box.left, e.clientY - box.top];
    };

    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, e);
      moved = 0;
      spread = 0;
      if (e.pointerType !== "mouse") hideTip();
      if (pointers.size > 1) { draft = null; redraw(); return; }  // zweiter Finger: zoomen statt zeichnen
      panning = tool === "move" || (e.pointerType === "mouse" && e.button !== 0);
      if (panning || tool === "erase" || tool === "pin") return;
      const [wx, wy] = toWorld(...local(e));
      draft = { kind: tool, color, width, points: tool === "pen" ? [wx, wy] : [wx, wy, wx, wy] };
      redraw();
    });
    canvas.addEventListener("pointermove", (e) => {
      const last = pointers.get(e.pointerId);
      if (!last) {
        if (tool === "erase") canvas.classList.toggle("s-map-hit", !!markAt(...local(e)));
        else if (tool === "move" && e.pointerType === "mouse") queueHover(...local(e));
        return;
      }
      pointers.set(e.pointerId, e);
      const dx = e.clientX - last.clientX, dy = e.clientY - last.clientY;
      if (pointers.size === 1) {
        moved += Math.abs(dx) + Math.abs(dy);
        if (draft) {
          const [wx, wy] = toWorld(...local(e));
          const p = draft.points;
          if (draft.kind === "pen") {
            // Nur neue Punkte, wenn sich der Stift merklich bewegt hat (spart Platz)
            if (Math.hypot(wx - p[p.length - 2], wy - p[p.length - 1]) * view.s >= 3 && p.length < 3998) p.push(wx, wy);
          } else {
            p[2] = wx;
            p[3] = wy;
          }
          redraw();
        } else if (panning) {
          if (moved > 6) hideTip();
          view.x -= dx / view.s;
          view.y -= dy / view.s;
          redraw();
        }
      } else if (pointers.size === 2) {
        moved = 99;
        const [a, b] = [...pointers.values()];
        const now = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        const box = canvas.getBoundingClientRect();
        if (spread) zoom(now / spread, (a.clientX + b.clientX) / 2 - box.left, (a.clientY + b.clientY) / 2 - box.top);
        view.x -= dx / 2 / view.s;
        view.y -= dy / 2 / view.s;
        spread = now;
      }
    });

    function finishDraft() {
      const m = draft;
      draft = null;
      if (!m) return;
      const p = m.points;
      if (m.kind !== "pen" && Math.hypot(p[2] - p[0], p[3] - p[1]) * view.s < 4) { redraw(); return; }  // nur geklickt
      m.points = p.map((v) => Math.round(v * 10) / 10);
      saveMark(m);
    }

    const release = (e) => {
      if (!pointers.delete(e.pointerId)) return;
      spread = 0;
      if (e.type !== "pointerup") { draft = null; redraw(); return; }
      if (draft) { finishDraft(); return; }
      if (moved >= 6 || pointers.size) return;
      const [px, py] = local(e);
      if (tool === "erase") {
        const m = markAt(px, py);
        if (m) deleteMark(m); else showInfo("Hier liegt keine Zeichnung.");
      } else if (tool === "pin" && !panning) {
        const text = window.prompt("Text für die Markierung (leer lassen geht auch):", "");
        if (text === null) return;
        const [wx, wy] = toWorld(px, py);
        saveMark({ kind: "pin", color, width, points: [Math.round(wx * 10) / 10, Math.round(wy * 10) / 10], text: text.trim().slice(0, 120) });
      } else {
        const m = markAt(px, py);
        showInfo(m ? describeMark(m) : pick(px, py));
        if (!m && e.pointerType !== "mouse") hover(px, py);
      }
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const [px, py] = local(e);
      zoom(e.deltaY < 0 ? 1.25 : 0.8, px, py);
      if (tool === "move") queueHover(px, py);
    }, { passive: false });

    /* ------------------------------------------------------------ Werkzeugleiste */
    const toolbar = root.querySelector(".s-map-tools");
    function setTool(next) {
      tool = next;
      draft = null;
      root.dataset.tool = next;
      canvas.classList.remove("s-map-hit");
      if (toolbar) toolbar.querySelectorAll("[data-tool]").forEach((b) => {
        b.classList.toggle("active", b.dataset.tool === next);
        b.setAttribute("aria-pressed", String(b.dataset.tool === next));
      });
      // Wer zeichnet, will die Zeichnungen auch sehen
      if (next !== "move" && !shown(marksLayer)) { saved.marks = true; keep(); buildPanel(); }
      redraw();
    }
    if (toolbar) {
      toolbar.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
      const colors = toolbar.querySelector(".s-map-colors");
      DRAW_COLORS.forEach((c) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "s-map-swatch";
        b.style.backgroundColor = c;
        b.title = "Farbe";
        b.setAttribute("aria-label", "Farbe " + c);
        b.classList.toggle("active", c === color);
        b.addEventListener("click", () => {
          color = c;
          saved.color = c;
          keep();
          colors.querySelectorAll(".s-map-swatch").forEach((x) => x.classList.toggle("active", x === b));
          if (tool === "move" || tool === "erase") setTool("pen");
        });
        colors.append(b);
      });
      const widths = toolbar.querySelector("[data-map-width]");
      DRAW_WIDTHS.forEach(([v, text]) => {
        const o = document.createElement("option");
        o.value = v;
        o.textContent = text;
        o.selected = v === width;
        widths.append(o);
      });
      widths.addEventListener("change", () => { width = Number(widths.value); saved.width = width; keep(); });
    }
    setTool("move");

    /* ------------------------------------------------------------ Ebenen-Menü */
    let markCount = null;
    function updateMarkCount() {
      if (markCount) markCount.textContent = marks.filter((m) => !m.pending).length.toLocaleString("de-DE");
    }

    function picture(l, fallback) {
      const name = iconName(l);
      if (name) {
        const img = document.createElement("img");
        img.src = ICON_BASE + name;
        img.alt = "";
        img.className = "s-map-icon";
        img.loading = "lazy";
        return img;
      }
      const span = document.createElement("span");
      span.className = "s-map-icon s-map-icon-fa";
      if (fallback) {
        const i = document.createElement("i");
        i.className = fallback;
        span.append(i);
      }
      span.style.color = l.color;
      return span;
    }

    /* Eine Zeile pro Ebene: Icon aus dem Spiel, Name, Anzahl. Antippen schaltet um. */
    function row(l, onToggle, fallback) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "s-map-row";
      const set = (on) => { b.classList.toggle("is-off", !on); b.setAttribute("aria-pressed", String(on)); };
      set(shown(l));
      const name = document.createElement("span");
      name.className = "s-map-name";
      name.textContent = l.label;
      const n = document.createElement("span");
      n.className = "s-map-count";
      n.textContent = l.count !== undefined ? l.count.toLocaleString("de-DE") : "";
      b.append(picture(l, fallback), name, n);
      b.addEventListener("click", () => {
        saved[l.id] = !shown(l);
        keep();
        set(saved[l.id]);
        if (onToggle) onToggle();
        redraw();
      });
      b.refresh = () => set(shown(l));
      return { el: b, count: n };
    }

    function chip(text, dot, on, change) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "s-map-chip";
      if (dot) {
        const d = document.createElement("span");
        d.className = "s-map-dot";
        d.style.backgroundColor = dot;
        b.append(d);
      }
      b.append(text);
      const set = (v) => { b.classList.toggle("is-off", !v); b.setAttribute("aria-pressed", String(v)); };
      set(on);
      b.addEventListener("click", () => { set(change()); redraw(); });
      return b;
    }

    function section(name, layers, extra) {
      const box = document.createElement("details");
      box.className = "s-map-section";
      box.open = !closed.has(name);
      box.addEventListener("toggle", () => {
        if (box.open) closed.delete(name); else closed.add(name);
        saved.closed = [...closed];
        keep();
      });
      const head = document.createElement("summary");
      head.className = "s-map-group";
      const title = document.createElement("span");
      title.textContent = name;
      head.append(title);
      const rows = [];
      if (layers.length > 1) {
        const all = document.createElement("button");
        all.type = "button";
        all.className = "s-map-all";
        const label = () => { all.textContent = layers.some(shown) ? "alle aus" : "alle an"; };
        label();
        all.addEventListener("click", (e) => {
          e.preventDefault();
          const on = !layers.some(shown);
          layers.forEach((l) => { saved[l.id] = on; });
          keep();
          rows.forEach((r) => r.el.refresh());
          label();
          redraw();
        });
        head.append(all);
        box.refreshAll = label;
      }
      box.append(head);
      const list = document.createElement("div");
      list.className = "s-map-list";
      layers.forEach((l) => {
        const r = row(l, () => box.refreshAll && box.refreshAll(), l.kind === "player" ? "fas fa-user-astronaut" : "");
        rows.push(r);
        list.append(r.el);
      });
      box.append(list);
      if (extra) box.append(extra);
      return box;
    }

    function buildPanel() {
      panel.replaceChildren();
      const groups = new Map();
      (world ? world.layers : []).forEach((l) => {
        if (!groups.has(l.group)) groups.set(l.group, []);
        groups.get(l.group).push(l);
      });

      // Planung: eigene Zeichnungen, gibt es auch ohne Spielstand
      const plan = section("Planung", []);
      const r = row(Object.assign(marksLayer, { count: marks.filter((m) => !m.pending).length }), null, "fas fa-pencil-alt");
      markCount = r.count;
      plan.querySelector(".s-map-list").append(r.el);
      const hint = document.createElement("div");
      hint.className = "s-map-hint";
      hint.textContent = "Oben ein Werkzeug wählen und auf der Karte zeichnen. Alle sehen die Zeichnungen.";
      plan.append(hint);
      panel.append(plan);

      if (BASES.length > 1) {
        const pickBase = section("Karte", []);
        const chips = document.createElement("div");
        chips.className = "s-map-chips";
        const buttons = BASES.map(([id, text]) => chip(text, "", id === base, () => {
          base = id;
          saved.base = id;
          keep();
          buttons.forEach((x) => { x.classList.toggle("is-off", x.dataset.base !== id); x.setAttribute("aria-pressed", String(x.dataset.base === id)); });
          return true;
        }));
        buttons.forEach((x, k) => { x.dataset.base = BASES[k][0]; });
        chips.append(...buttons);
        pickBase.append(chips);
        panel.append(pickBase);
      }

      const names = [...groups.keys()].sort((a, c) => {
        const ia = GROUP_ORDER.indexOf(a), ic = GROUP_ORDER.indexOf(c);
        return (ia < 0 ? 99 : ia) - (ic < 0 ? 99 : ic);
      });
      names.forEach((name) => {
        let extra = null;
        if (name === "Vorkommen") {
          extra = document.createElement("div");
          extra.className = "s-map-chips";
          PURITIES.forEach(([value, text, dot]) => extra.append(chip(text, dot, filter.purity.has(value), () => {
            if (filter.purity.has(value)) filter.purity.delete(value); else filter.purity.add(value);
            saved.purity = [...filter.purity];
            keep();
            return filter.purity.has(value);
          })));
          extra.append(chip("Nur freie", "", filter.free, () => {
            filter.free = !filter.free;
            saved.free = filter.free;
            keep();
            return filter.free;
          }));
        }
        panel.append(section(name, groups.get(name), extra));
      });
    }

    function describe() {
      status.replaceChildren();
      if (!world) {
        status.textContent = "Noch kein Spielstand hochgeladen.";
        return;
      }
      const m = world.meta;
      const fn = m.filename || (m.name ? (m.name.endsWith(".sav") ? m.name : m.name + ".sav") : "");
      if (fn) {
        const badge = document.createElement("span");
        badge.className = "badge badge-dark border border-secondary text-light mr-1";
        badge.title = "Zuletzt hochgeladene Datei";
        const icon = document.createElement("i");
        icon.className = "fas fa-file-alt mr-1 text-warning";
        badge.append(icon, fn);
        status.append(badge);
      }
      const totalSec = Math.max(0, Math.round(m.seconds || 0));
      const h = Math.floor(totalSec / 3600);
      const min = Math.floor((totalSec % 3600) / 60);
      let playTimeStr = "";
      if (h > 0 && min > 0) playTimeStr = `${h} Std. ${min} Min. Spielzeit`;
      else if (h > 0) playTimeStr = `${h} Std. Spielzeit`;
      else playTimeStr = `${min} Min. Spielzeit`;

      const when = m.savedAt ? new Date(m.savedAt).toLocaleDateString("de-DE") : "";
      const parts = [];
      if (m.session && (!fn || !fn.toLowerCase().startsWith(m.session.toLowerCase()))) parts.push(m.session);
      parts.push(playTimeStr);
      if (when) parts.push("gespeichert am " + when);
      if (m.by) parts.push("von " + m.by);
      const text = document.createElement("span");
      text.className = "text-muted";
      text.textContent = parts.filter(Boolean).join(" · ");
      status.append(text);
    }

    let loadedAt = null;  // Stand der geladenen Welt, für das Live-Nachladen

    function load(keepView) {
      const at = loadedAt;
      const got = at !== null && cache.at === at ? Promise.resolve(cache.world) : fetch(root.dataset.world, { cache: "no-store" }).then((res) => {
        if (res.status === 404) return null;
        if (!res.ok) throw new Error(res.status);
        return res.json();
      });
      return got.then((data) => {
        cache.at = at;
        cache.world = data;
        if (!alive) return;
        world = data;
        describe();
        buildPanel();
        if (world && !keepView) fit();
        redraw();
      });
    }

    let watching = false;
    function watch(live) {
      if (watching) return;
      watching = true;
      fetch(root.dataset.status, { cache: "no-store" }).then((res) => res.json()).then((s) => {
        watching = false;
        if (!alive) return;
        if (s.state === "running") {
          status.replaceChildren();
          const txt = document.createElement("span");
          txt.className = "text-muted";
          txt.textContent = s.filename ? `Lese ${s.filename} ein, das kann eine Minute dauern…` : "Spielstand wird gelesen, das kann eine Minute dauern.";
          status.append(txt);
          setTimeout(() => { if (alive) watch(); }, 2000);
        } else if (s.state === "failed") {
          status.replaceChildren();
          const err = document.createElement("span");
          err.className = "text-danger";
          err.textContent = s.error;
          status.append(err);
        } else if (!live || s.at !== loadedAt) {
          loadedAt = s.at;
          load(live && world);
        } else {
          describe();
        }
      }).catch(() => { watching = false; if (alive) status.textContent = "Der Stand ließ sich nicht abrufen."; });
    }

    root.querySelector("#s-map-file").addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;
      status.replaceChildren();
      const txt = document.createElement("span");
      txt.className = "text-muted";
      txt.textContent = `Lade ${file.name} hoch…`;
      status.append(txt);
      const body = new FormData();
      body.append("save", file);
      fetch(root.dataset.upload, { method: "POST", headers: { "X-CSRF-Token": root.dataset.csrf }, body })
        .then((res) => res.json().then((data) => {
          if (res.ok) watch(); else {
            status.replaceChildren();
            const err = document.createElement("span");
            err.className = "text-danger";
            err.textContent = data.error;
            status.append(err);
          }
        }))
        .catch(() => {
          status.replaceChildren();
          const err = document.createElement("span");
          err.className = "text-danger";
          err.textContent = "Das Hochladen hat nicht geklappt. Lade die Seite neu und versuch es noch einmal.";
          status.append(err);
        });
      e.target.value = "";
    });
    root.querySelector("[data-map-zoom-in]").addEventListener("click", () => { const { w, h } = size(); zoom(1.5, w / 2, h / 2); });
    root.querySelector("[data-map-zoom-out]").addEventListener("click", () => { const { w, h } = size(); zoom(1 / 1.5, w / 2, h / 2); });
    root.querySelector("[data-map-fit]").addEventListener("click", () => { fit(); });
    root.querySelector("[data-map-full]").addEventListener("click", () => { root.classList.toggle("s-map-full"); stretch(); });
    root.querySelector("[data-map-panel]").addEventListener("click", () => { panel.hidden = !panel.hidden; });

    /* Die Karte reicht bis zum unteren Fensterrand, egal wie hoch Kopfzeile und Leiste gerade sind */
    function stretch() {
      if (root.classList.contains("s-map-full")) { root.style.height = ""; return; }
      const top = root.getBoundingClientRect().top + window.scrollY;
      root.style.height = Math.max(352, window.innerHeight - top - 12) + "px";
    }
    window.addEventListener("resize", stretch);

    let started = false;
    function start() {
      if (started) return;
      started = true;
      stretch();
      if (window.innerWidth < 768) panel.hidden = true; // Am Handy bleibt die Karte frei, die Ebenen klappt man auf
      fit();
      buildPanel();
      const img = new Image();
      img.onload = () => { image = img; redraw(); };
      img.onerror = () => redraw();
      img.src = root.dataset.image;
      watch();
      loadMarks();
    }
    start();
    let fitted = false;
    const resize = new ResizeObserver(() => {
      const { w, h } = size();
      if (w > 0 && h > 0 && (!fitted || !view.s || view.s <= 0 || isNaN(view.s))) {
        fit();
        fitted = true;
      } else {
        redraw();
      }
    });
    resize.observe(canvas);
    return {
      root,
      live() { if (started) { watch(true); loadMarks(); } },
      stop() { alive = false; resize.disconnect(); window.removeEventListener("resize", stretch); },
    };
  }

  function check() {
    const root = document.querySelector("[data-karte]");
    if (root && (!current || current.root !== root)) current = init(root);
  }

  // Direkt beim Starten initialisieren, falls das Element schon im DOM ist:
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", check);
  } else {
    check();
  }

  // Seitenwechsel ohne Neuladen (satis.js): Karte auf der neuen Seite starten, die alte anhalten
  document.addEventListener("satis:load", (e) => {
    const root = (e.target && e.target.matches && e.target.matches("[data-karte]"))
      ? e.target
      : (e.target && e.target.querySelector && e.target.querySelector("[data-karte]"));
    if (root && (!current || current.root !== root)) current = init(root);
  });
  document.addEventListener("satis:unload", (e) => {
    if (current && e.target && e.target.contains && e.target.contains(current.root)) {
      current.stop();
      current = null;
    }
  });
  // Hat jemand anderes einen Spielstand hochgeladen, kommt die neue Welt von selbst (satis.js meldet jede Änderung)
  document.addEventListener("satis:live", () => { if (current) current.live(); });
})();
