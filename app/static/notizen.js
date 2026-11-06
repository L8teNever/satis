/* Notizen: speichert beim Tippen von selbst und rechnet aus, sobald man nach einer Rechnung "=" tippt.
   Alles hängt am document, damit es nach Seitenwechsel und Live-Tausch weiter greift. */
(function () {
  "use strict";
  if (window.satisNotes) return;
  window.satisNotes = true;

  /* ---------------------------------------------------------------- Rechner
     Kann + - * / ^ %, Klammern, Komma oder Punkt als Dezimalzeichen, x × · : ÷ als Mal/Geteilt. */
  function calc(src) {
    const s = src.replace(/[×x·]/g, "*").replace(/[÷:]/g, "/").replace(/,/g, ".").replace(/\s+/g, "");
    let i = 0;
    const peek = () => s[i];
    function num() {
      const m = /^\d*\.?\d+(e[+-]?\d+)?/i.exec(s.slice(i)) || /^\d+\./.exec(s.slice(i));
      if (!m) throw new Error("Zahl");
      i += m[0].length;
      return parseFloat(m[0]);
    }
    function atom() {
      if (peek() === "-") { i++; return -atom(); }
      if (peek() === "+") { i++; return atom(); }
      let v;
      if (peek() === "(") {
        i++;
        v = sum();
        if (peek() !== ")") throw new Error("Klammer");
        i++;
      } else v = num();
      if (peek() === "%") { i++; v /= 100; }
      return v;
    }
    function power() {
      const b = atom();
      if (peek() === "^") { i++; return Math.pow(b, power()); }
      return b;
    }
    function product() {
      let v = power();
      while (peek() === "*" || peek() === "/") {
        const op = s[i++];
        const r = power();
        v = op === "*" ? v * r : v / r;
      }
      return v;
    }
    function sum() {
      let v = product();
      while (peek() === "+" || peek() === "-") {
        const op = s[i++];
        const r = product();
        v = op === "+" ? v + r : v - r;
      }
      return v;
    }
    const v = sum();
    if (i !== s.length || !isFinite(v)) throw new Error("Rest");
    return v;
  }

  function format(v, comma) {
    const out = String(parseFloat(v.toPrecision(12)));
    return comma ? out.replace(".", ",") : out;
  }

  /* Die Rechnung steht direkt vor dem "=", am Zeilenende. Text davor ("Eisen: 4*5=") bleibt außen vor. */
  function solve(line) {
    const m = /([\d\s.,+\-*/×x·:÷^%()]+)$/.exec(line);
    if (!m) return null;
    const expr = m[1].replace(/^[\s+*/:÷^%)]+/, "").trim();
    if (!/\d/.test(expr) || !/[+\-*/×x·:÷^%]/.test(expr.replace(/^-/, ""))) return null;  // nur eine Zahl: nichts tun
    try {
      return format(calc(expr), expr.includes(",") && !expr.includes("."));
    } catch (e) {
      return null;
    }
  }

  document.addEventListener("input", (e) => {
    const ta = e.target;
    if (!ta.matches || !ta.matches(".s-note-body") || e.inputType !== "insertText" || e.data !== "=") return;
    const pos = ta.selectionStart;
    const before = ta.value.slice(0, pos - 1);
    const after = ta.value.slice(pos);
    if (after && !/^\n/.test(after)) return;  // nur am Zeilenende rechnen
    const res = solve(before.slice(before.lastIndexOf("\n") + 1));
    if (res === null) return;
    ta.value = before + "=" + res + after;
    ta.selectionStart = ta.selectionEnd = pos + res.length;
  });

  /* ---------------------------------------------------------------- Automatisch speichern */
  const WAIT_MS = 800;
  const timers = new WeakMap();

  function state(form, text) {
    const el = form.querySelector("[data-note-state]");
    if (el) el.textContent = text;
  }

  function save(form) {
    clearTimeout(timers.get(form));
    timers.delete(form);
    state(form, "speichert …");
    return fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Satis-Autosave": "1" },
      credentials: "same-origin",
    })
      .then((res) => {
        if (!res.ok || res.redirected) throw new Error(res.status);
        state(form, "gespeichert");
        delete form.dataset.noteDirty;
        // Wer nicht mehr in der Liste tippt, bekommt wieder die Änderungen der anderen
        const region = form.closest("[data-live]");
        const a = document.activeElement;
        if (region && !(a && region.contains(a) && a.form) && !region.querySelector("[data-note-dirty]")) delete region.dataset.liveDirty;
      })
      .catch(() => state(form, "nicht gespeichert!"));
  }

  document.addEventListener("input", (e) => {
    const form = e.target.closest && e.target.closest("form[data-note]");
    if (!form) return;
    form.dataset.noteDirty = "1";
    state(form, "");
    clearTimeout(timers.get(form));
    timers.set(form, setTimeout(() => save(form), WAIT_MS));
  });

  // Feld verlassen: sofort speichern, nicht erst nach der Pause
  document.addEventListener("focusout", (e) => {
    const form = e.target.closest && e.target.closest("form[data-note]");
    if (form && form.dataset.noteDirty) save(form);
  });

  // Enter im Titel oder in der Kategorie speichert, ohne die Seite zu wechseln
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form.matches || !form.matches("form[data-note]")) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    save(form);
  }, true);

  // Ungespeichertes nicht verlieren: beim Seitenwechsel in der App und beim Schließen
  document.addEventListener("satis:unload", (e) => {
    e.target.querySelectorAll("form[data-note][data-note-dirty]").forEach(save);
  });
  window.addEventListener("pagehide", () => {
    document.querySelectorAll("form[data-note][data-note-dirty]").forEach((f) => {
      const data = new FormData(f);
      data.append("autosave", "1");
      if (navigator.sendBeacon) navigator.sendBeacon(f.action, data);
    });
  });
})();
