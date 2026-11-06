/* Produktionsgraph mit Cytoscape, die Daten stehen im Attribut data-graph.
   In gespeicherten Plänen lassen sich Schritte im Graph und in der Tabelle abhaken und zuteilen.
   Die Tabelle kann live getauscht werden und die Seite wechselt ohne Neuladen (satis.js), darum hängen
   die Klicks am Dokument und das Skript läuft nur einmal. */
(function () {
  const COLORS = { step: "#444", done: "#00bc8c", raw: "#375a7f", target: "#F39C12", surplus: "#E74C3C" };
  const steps = () => document.querySelector("[data-step-url]");
  let graph = null;

  function apply(recipe, data) {
    const table = steps();
    if (!table) return;
    const row = table.querySelector('tr[data-recipe="' + CSS.escape(recipe) + '"]');
    if (!row) return;
    row.classList.toggle("s-row-done", data.done);
    row.querySelector(".s-step-cell").innerHTML = data.html;
    document.getElementById("s-finished").textContent = data.finished;
    if (graph) graph.getElementById(recipe).data({ done: data.done, tag: data.tag });
  }

  /* Klappt etwas nicht (Plan geändert, Login abgelaufen), zeigt das Neuladen den echten Stand. */
  function send(recipe, field, value) {
    const body = new FormData();
    body.append("recipe", recipe);
    body.append(field, value);
    const table = steps();
    fetch(table.dataset.stepUrl, { method: "POST", headers: { Accept: "application/json", "X-CSRF-Token": table.dataset.csrf }, body })
      .then((res) => { if (!res.ok) throw new Error(res.status); return res.json(); })
      .then((data) => apply(recipe, data))
      .catch(() => location.reload());
  }

  function toggle(recipe) {
    const row = steps().querySelector('tr[data-recipe="' + CSS.escape(recipe) + '"]');
    if (!row) return;
    send(recipe, "done", row.classList.contains("s-row-done") ? "0" : "1");
  }

  const inSteps = (e) => steps() && steps().contains(e.target);
  document.addEventListener("submit", (e) => {
    if (!inSteps(e) || !e.target.matches(".s-step")) return;
    e.preventDefault();
    toggle(e.target.elements.recipe.value);
  });
  document.addEventListener("change", (e) => {
    if (inSteps(e) && e.target.name === "assignee_id") send(e.target.form.elements.recipe.value, "assignee_id", e.target.value);
  });
  document.addEventListener("click", (e) => {
    const row = inSteps(e) && e.target.closest("tr[data-recipe]");
    if (row && !e.target.closest("a, button, input, select, form, .dropdown")) toggle(row.dataset.recipe);
  });

  function draw(box) {
    const data = JSON.parse(box.dataset.graph);
    const cy = cytoscape({
      container: box,
      elements: {
        nodes: data.nodes.map((n) => ({ data: n })),
        edges: data.edges.map((e, i) => ({ data: { ...e, id: "e" + i } })),
      },
      layout: { name: "dagre", rankDir: "LR", nodeSep: 25, rankSep: 90 },
      minZoom: 0.1,
      maxZoom: 2,
      style: [
        { selector: "node", style: {
          shape: "round-rectangle", width: "label", height: "label", padding: 10,
          label: (n) => n.data("label") + (n.data("tag") ? "\n" + n.data("tag") : ""),
          "text-wrap": "wrap", "text-valign": "center", "text-halign": "center", color: "#fff", "font-size": 12,
          "font-family": "Lato, sans-serif", "background-color": (n) => COLORS[n.data("done") ? "done" : n.data("kind")],
        } },
        { selector: 'node[kind = "target"]', style: { color: "#444", "font-weight": "bold" } },
        { selector: "edge", style: {
          width: 2, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#888", "target-arrow-color": "#888",
          label: "data(label)", "font-size": 10, color: "#fff", "text-background-color": "#222", "text-background-opacity": 1,
          "text-background-padding": 2,
        } },
      ],
    });
    if ("tracking" in box.dataset) {
      graph = cy;
      cy.on("tap", 'node[kind = "step"]', (e) => toggle(e.target.id()));
      cy.on("mouseover", 'node[kind = "step"]', () => { box.style.cursor = "pointer"; });
      cy.on("mouseout", "node", () => { box.style.cursor = ""; });
    }
    box.cy = cy;
    return cy;
  }

  const current = () => document.querySelector("[data-graph]");
  function refit() {
    const box = current();
    if (box && box.cy) { box.cy.resize(); box.cy.fit(undefined, 20); }
  }
  $(document).on("shown.bs.tab", 'a[href="#graph"]', refit);
  // Nur bei neuer Breite (Handy gedreht): Beim Scrollen löst die Adressleiste auch resize aus
  let width = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth !== width) { width = window.innerWidth; refit(); }
  });

  /* Live-Tausch: Gleicher Aufbau, dann nur Farben und Namen ändern, Zoom und Ausschnitt bleiben.
     Anderer Aufbau (Plan geändert), dann neu zeichnen. */
  const shape = (d) => JSON.stringify([d.nodes.map((n) => n.id), d.edges.map((e) => [e.source, e.target, e.label])]);
  if (window.satisLive) window.satisLive.swap.graph = (region, next) => {
    const box = region.querySelector("[data-graph]");
    const nextBox = next.querySelector("[data-graph]");
    if (!box || !nextBox || !box.cy) return false;
    const old = JSON.parse(box.dataset.graph), data = JSON.parse(nextBox.dataset.graph);
    if (shape(old) !== shape(data) || ("tracking" in box.dataset) !== ("tracking" in nextBox.dataset)) return false;  // satis:unload räumt auf
    box.dataset.graph = nextBox.dataset.graph;
    data.nodes.forEach((n) => box.cy.getElementById(n.id).data(n));
    return true;
  };

  /* satis.js meldet neue Inhalte (Seitenwechsel, Live-Tausch) mit satis:load und alte mit satis:unload */
  document.addEventListener("satis:load", (e) => {
    e.target.querySelectorAll("[data-graph]").forEach((box) => { if (!box.cy) draw(box); });
  });
  document.addEventListener("satis:unload", (e) => {
    e.target.querySelectorAll("[data-graph]").forEach((box) => {
      if (!box.cy) return;
      if (graph === box.cy) graph = null;
      box.cy.destroy();
      box.cy = null;
    });
  });
})();
