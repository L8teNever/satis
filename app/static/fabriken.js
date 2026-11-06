/* Produktionsgraph mit Cytoscape. Die Daten stehen im Attribut data-graph. */
(function () {
  const COLORS = { step: "#444", raw: "#375a7f", target: "#F39C12", surplus: "#E74C3C" };

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
          shape: "round-rectangle", width: "label", height: "label", padding: 10, label: "data(label)",
          "text-wrap": "wrap", "text-valign": "center", "text-halign": "center", color: "#fff", "font-size": 12,
          "font-family": "Lato, sans-serif", "background-color": (n) => COLORS[n.data("kind")],
        } },
        { selector: 'node[kind = "target"]', style: { color: "#444", "font-weight": "bold" } },
        { selector: "edge", style: {
          width: 2, "curve-style": "bezier", "target-arrow-shape": "triangle", "line-color": "#888", "target-arrow-color": "#888",
          label: "data(label)", "font-size": 10, color: "#fff", "text-background-color": "#222", "text-background-opacity": 1,
          "text-background-padding": 2,
        } },
      ],
    });
    $('a[href="#graph"]').on("shown.bs.tab", () => { cy.resize(); cy.fit(undefined, 20); });
    return cy;
  }

  window.satisGraph = function (root) {
    root.querySelectorAll("[data-graph]").forEach(draw);
  };
  window.satisGraph(document);
})();
