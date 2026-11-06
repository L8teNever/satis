/* Karte der Spielwelt (eigene Seite). Gezeichnet wird auf einem Canvas und nur, wenn sich etwas ändert.
   Neue Ebenen kommen aus layers.py, hier muss dafür nichts geändert werden. */
(function () {
  /* Geladene Welt bleibt beim Seitenwechsel im Speicher, solange der Stand gleich ist */
  const cache = { at: null, world: null };
  let current = null;  // Karte auf der aktuellen Seite

  function init(root) {
    let alive = true;  // Nach dem Seitenwechsel laufen keine alten Abrufe mehr weiter
    const canvas = root.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const panel = root.querySelector(".s-map-layers");
    const info = root.querySelector(".s-map-info");
    const status = document.getElementById("s-map-status");
    const STRIDE = { rect: 6, dot: 3, node: 5 };
    const STORE = "satis.karte.ebenen";
    const PURITIES = [[2, "Rein"], [1, "Normal"], [0.5, "Unrein"]];

    let world = null;
    let image = null;
    let view = { x: 0, y: 0, s: 0.001 };
    let queued = false;
    const filter = { purity: new Set([0.5, 1, 2]), free: false };
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { saved = {}; }

    const size = () => ({ w: canvas.clientWidth, h: canvas.clientHeight });
    const shown = (l) => (l.id in saved ? saved[l.id] : l.on);

    function redraw() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; draw(); });
    }

    function fit() {
      const { w, h } = size();
      const b = world.bounds;
      view = { x: b.x + b.size / 2, y: b.y + b.size / 2, s: Math.min(w, h) / b.size };
      redraw();
    }

    function zoom(factor, px, py) {
      const { w, h } = size();
      const s = Math.min(0.5, Math.max(world ? Math.min(w, h) / world.bounds.size / 2 : 1e-4, view.s * factor));
      view.x += (px - w / 2) / view.s - (px - w / 2) / s;
      view.y += (py - h / 2) / view.s - (py - h / 2) / s;
      view.s = s;
      redraw();
    }

    function drawRects(l, sx, sy, w, h) {
      const it = l.items;
      const s = view.s;
      ctx.fillStyle = l.color;
      ctx.beginPath();
      for (let i = 0; i < it.length; i += 6) {
        const x = sx(it[i]), y = sy(it[i + 1]);
        const r = Math.max(it[i + 3], it[i + 4]) * s;
        if (x < -r || y < -r || x > w + r || y > h + r) continue;
        if (r < 3) { ctx.rect(x - 1, y - 1, 2, 2); continue; }
        const a = it[i + 2] * Math.PI / 180;
        const cx = Math.cos(a) * s / 2, cy = Math.sin(a) * s / 2;
        const lx = it[i + 3], ly = it[i + 4];
        ctx.moveTo(x + cx * lx - cy * ly, y + cy * lx + cx * ly);
        ctx.lineTo(x + cx * lx + cy * ly, y + cy * lx - cx * ly);
        ctx.lineTo(x - cx * lx + cy * ly, y - cy * lx - cx * ly);
        ctx.lineTo(x - cx * lx - cy * ly, y - cy * lx + cx * ly);
        ctx.closePath();
      }
      ctx.fill();
    }

    function drawLines(l, sx, sy) {
      ctx.strokeStyle = l.color;
      ctx.lineWidth = l.id === "wires" ? 1 : Math.min(4, Math.max(1, view.s * 150));
      ctx.beginPath();
      for (const line of l.items) {
        ctx.moveTo(sx(line[0]), sy(line[1]));
        for (let i = 2; i < line.length; i += 2) ctx.lineTo(sx(line[i]), sy(line[i + 1]));
      }
      ctx.stroke();
    }

    const visibleNode = (it, i) => filter.purity.has(it[i + 3]) && !(filter.free && it[i + 4]);

    function drawNodes(l, sx, sy) {
      const it = l.items;
      ctx.lineWidth = 2;
      for (let i = 0; i < it.length; i += 5) {
        if (!visibleNode(it, i)) continue;
        ctx.beginPath();
        ctx.arc(sx(it[i]), sy(it[i + 1]), it[i + 3] === 2 ? 7 : it[i + 3] === 1 ? 5.5 : 4, 0, 7);
        ctx.fillStyle = l.color;
        ctx.strokeStyle = it[i + 4] ? "#fff" : "#000";
        ctx.fill();
        ctx.stroke();
      }
    }

    function drawDots(l, sx, sy) {
      const it = l.items;
      ctx.font = "12px Lato, sans-serif";
      ctx.lineWidth = 1;
      for (let i = 0; i < it.length; i += 3) {
        const x = sx(it[i]), y = sy(it[i + 1]);
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, 7);
        ctx.fillStyle = l.color;
        ctx.strokeStyle = "#000";
        ctx.fill();
        ctx.stroke();
        if (l.id === "players") {
          ctx.fillStyle = "#fff";
          ctx.fillText(world.labels[it[i + 2]], x + 7, y + 4);
        }
      }
    }

    function draw() {
      const { w, h } = size();
      const ratio = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
        canvas.width = Math.round(w * ratio);
        canvas.height = Math.round(h * ratio);
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.fillStyle = "#1b2a33";
      ctx.fillRect(0, 0, w, h);
      if (!world) return;
      const sx = (x) => (x - view.x) * view.s + w / 2;
      const sy = (y) => (y - view.y) * view.s + h / 2;
      const b = world.bounds;
      if (image) ctx.drawImage(image, sx(b.x), sy(b.y), b.size * view.s, b.size * view.s);
      const painters = { rect: drawRects, line: drawLines, node: drawNodes, dot: drawDots };
      const order = { rect: 0, line: 1, node: 2, dot: 3 };
      [...world.layers].sort((a, c) => order[a.kind] - order[c.kind]).forEach((l) => {
        if (shown(l)) painters[l.kind](l, sx, sy, w, h);
      });
    }

    function segment(px, py, x1, y1, x2, y2) {
      const dx = x2 - x1, dy = y2 - y1;
      const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy || 1)));
      return Math.hypot(px - x1 - t * dx, py - y1 - t * dy);
    }

    /* Was liegt unter dem Klick? Punkte gehen vor Gebäuden, Gebäude vor Linien. */
    function pick(px, py) {
      if (!world) return "";
      const { w, h } = size();
      const wx = (px - w / 2) / view.s + view.x, wy = (py - h / 2) / view.s + view.y;
      const reach = 10 / view.s;
      let best = "", score = Infinity;
      for (const l of world.layers) {
        if (!shown(l)) continue;
        const rank = { node: 0, dot: 0, rect: 1, line: 2 }[l.kind] * reach;
        if (l.kind === "line") {
          for (const line of l.items) {
            for (let i = 2; i < line.length; i += 2) {
              const d = segment(wx, wy, line[i - 2], line[i - 1], line[i], line[i + 1]);
              if (d < reach && d + rank < score) { score = d + rank; best = l.label; }
            }
          }
          continue;
        }
        const step = STRIDE[l.kind], it = l.items;
        const at = l.kind === "rect" ? 5 : 2;
        for (let i = 0; i < it.length; i += step) {
          if (l.kind === "node" && !visibleNode(it, i)) continue;
          const pad = l.kind === "rect" ? Math.max(it[i + 3], it[i + 4]) / 2 : 0;
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

    /* Maus und Finger: ein Zeiger verschiebt, zwei zoomen, ein kurzer Klick zeigt, was dort steht */
    const pointers = new Map();
    let moved = 0, spread = 0;

    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, e);
      moved = 0;
      spread = 0;
    });
    canvas.addEventListener("pointermove", (e) => {
      const last = pointers.get(e.pointerId);
      if (!last) return;
      pointers.set(e.pointerId, e);
      if (pointers.size === 1) {
        moved += Math.abs(e.clientX - last.clientX) + Math.abs(e.clientY - last.clientY);
        view.x -= (e.clientX - last.clientX) / view.s;
        view.y -= (e.clientY - last.clientY) / view.s;
        redraw();
      } else if (pointers.size === 2) {
        moved = 99;
        const [a, b] = [...pointers.values()];
        const now = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        const box = canvas.getBoundingClientRect();
        if (spread) zoom(now / spread, (a.clientX + b.clientX) / 2 - box.left, (a.clientY + b.clientY) / 2 - box.top);
        spread = now;
      }
    });
    const release = (e) => {
      if (pointers.delete(e.pointerId) && e.type === "pointerup" && moved < 6) {
        const box = canvas.getBoundingClientRect();
        showInfo(pick(e.clientX - box.left, e.clientY - box.top));
      }
      spread = 0;
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const box = canvas.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.25 : 0.8, e.clientX - box.left, e.clientY - box.top);
    }, { passive: false });

    function control(text, color, count, checked, change) {
      const row = document.createElement("label");
      row.className = "s-map-row";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = checked;
      box.addEventListener("change", () => { change(box.checked); redraw(); });
      row.append(box);
      if (color) {
        const dot = document.createElement("span");
        dot.className = "s-map-dot";
        dot.style.backgroundColor = color;
        row.append(dot);
      }
      const name = document.createElement("span");
      name.className = "s-map-name";
      name.textContent = text;
      row.append(name);
      if (count !== undefined) {
        const n = document.createElement("span");
        n.className = "text-muted";
        n.textContent = count.toLocaleString("de-DE");
        row.append(n);
      }
      return row;
    }

    function heading(text) {
      const h = document.createElement("div");
      h.className = "s-map-group";
      h.textContent = text;
      return h;
    }

    function buildPanel() {
      panel.replaceChildren();
      const groups = new Map();
      world.layers.forEach((l) => {
        if (!groups.has(l.group)) groups.set(l.group, []);
        groups.get(l.group).push(l);
      });
      groups.forEach((layers, name) => {
        panel.append(heading(name));
        layers.forEach((l) => panel.append(control(l.label, l.color, l.count, shown(l), (on) => {
          saved[l.id] = on;
          localStorage.setItem(STORE, JSON.stringify(saved));
        })));
        if (name === "Vorkommen") {
          PURITIES.forEach(([value, text]) => panel.append(control(text, "", undefined, filter.purity.has(value), (on) => {
            if (on) filter.purity.add(value); else filter.purity.delete(value);
          })));
          panel.append(control("Nur freie", "", undefined, filter.free, (on) => { filter.free = on; }));
        }
      });
    }

    function describe() {
      if (!world) return "Noch kein Spielstand hochgeladen.";
      const m = world.meta;
      const hours = Math.round(m.seconds / 3600);
      const when = new Date(m.savedAt).toLocaleDateString("de-DE");
      return [m.session, hours + " Std.", "gespeichert " + when, m.by && "von " + m.by].filter(Boolean).join(" · ");
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
        status.textContent = describe();
        if (world) { buildPanel(); if (!keepView) fit(); }
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
          status.textContent = "Spielstand wird gelesen, das kann eine Minute dauern.";
          setTimeout(() => { if (alive) watch(); }, 2000);
        } else if (s.state === "failed") {
          status.textContent = s.error;
        } else if (!live || s.at !== loadedAt) {
          loadedAt = s.at;
          load(live && world);
        } else {
          status.textContent = describe();
        }
      }).catch(() => { watching = false; if (alive) status.textContent = "Der Stand ließ sich nicht abrufen."; });
    }

    root.querySelector("#s-map-file").addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;
      status.textContent = "Wird hochgeladen.";
      const body = new FormData();
      body.append("save", file);
      fetch(root.dataset.upload, { method: "POST", headers: { "X-CSRF-Token": root.dataset.csrf }, body })
        .then((res) => res.json().then((data) => {
          if (res.ok) watch(); else status.textContent = data.error;
        }))
        .catch(() => { status.textContent = "Das Hochladen hat nicht geklappt. Lade die Seite neu und versuch es noch einmal."; });
      e.target.value = "";
    });
    root.querySelector("[data-map-zoom-in]").addEventListener("click", () => { const { w, h } = size(); zoom(1.5, w / 2, h / 2); });
    root.querySelector("[data-map-zoom-out]").addEventListener("click", () => { const { w, h } = size(); zoom(1 / 1.5, w / 2, h / 2); });
    root.querySelector("[data-map-fit]").addEventListener("click", () => { if (world) fit(); });
    root.querySelector("[data-map-full]").addEventListener("click", () => { root.classList.toggle("s-map-full"); });
    root.querySelector("[data-map-panel]").addEventListener("click", () => { panel.hidden = !panel.hidden; });

    let started = false;
    function start() {
      if (started) return;
      started = true;
      if (window.innerWidth < 768) panel.hidden = true; // Am Handy bleibt die Karte frei, die Ebenen klappt man auf
      const img = new Image();
      img.onload = () => { image = img; redraw(); };
      img.src = root.dataset.image;
      watch();
    }
    start();
    const resize = new ResizeObserver(redraw);
    resize.observe(canvas);
    return {
      root,
      live() { if (started) watch(true); },
      stop() { alive = false; resize.disconnect(); },
    };
  }

  // Seitenwechsel ohne Neuladen (satis.js): Karte auf der neuen Seite starten, die alte anhalten
  document.addEventListener("satis:load", (e) => {
    const root = e.target.querySelector && e.target.querySelector("[data-karte]");
    if (root && (!current || current.root !== root)) current = init(root);
  });
  document.addEventListener("satis:unload", (e) => {
    if (current && e.target.contains(current.root)) { current.stop(); current = null; }
  });
  // Hat jemand anderes einen Spielstand hochgeladen, kommt die neue Welt von selbst (satis.js meldet jede Änderung)
  document.addEventListener("satis:live", () => { if (current) current.live(); });
})();
