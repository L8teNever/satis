/* Eigene Bedienelemente im Bootstrap-Stil. Jedes Element bleibt im Kern das normale Formularfeld,
   ohne JavaScript funktioniert die Seite also weiter mit den Browser-Feldern.
     <select>            -> Dropdown wie bootstrap-select; <option data-icon="fa-..."> zeigt ein Icon,
                            <select data-search> bekommt ein Suchfeld
     <input type="date"> -> Kalender, gesendet wird weiter JJJJ-MM-TT
     <form data-confirm> -> Bestätigungsdialog vor dem Absenden */
(function () {
  const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
  const DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function icon(name, cls) {
    return el("i", "fas " + name + (cls ? " " + cls : ""));
  }

  /* Gemeinsames Gerüst: Button + Menü. Menüs sind fixed positioniert, damit sie nicht in .table-responsive abgeschnitten werden. */
  function dropdown(field, wrapClass, menuClass) {
    const wrap = el("div", "dropdown " + wrapClass);
    const small = field.classList.contains("form-control-sm");
    const btn = el("button", "btn btn-light dropdown-toggle s-toggle" + (small ? " btn-sm" : ""));
    const menu = el("div", "dropdown-menu " + menuClass);
    btn.type = "button";
    btn.setAttribute("data-toggle", "dropdown");
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    if (field.id) { btn.id = field.id; field.removeAttribute("id"); }
    if (field.getAttribute("aria-label")) btn.setAttribute("aria-label", field.getAttribute("aria-label"));
    wrap.append(btn, menu);
    field.after(wrap);
    wrap.prepend(field);
    field.hidden = true;
    $(btn).dropdown({ boundary: "viewport", popperConfig: { positionFixed: true } });
    return { wrap, btn, menu };
  }

  function label(target, iconName, text) {
    const span = el("span", "s-label", text);
    target.replaceChildren(span);
    if (iconName) span.prepend(icon(iconName, "mr-1"));
  }

  function enhanceSelect(sel) {
    const { wrap, btn, menu } = dropdown(sel, "s-select", "s-menu");
    let search = null;
    if ("search" in sel.dataset) {
      search = el("input", "form-control form-control-sm s-search");
      search.placeholder = "Suchen";
      search.setAttribute("aria-label", "Suchen");
      search.addEventListener("input", () => {
        const q = search.value.toLowerCase();
        items.forEach((it) => { it.hidden = !it.textContent.toLowerCase().includes(q); });
      });
      search.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault(); // Enter wählt den ersten Treffer, statt das Formular abzuschicken
        const hit = items.find((it) => !it.hidden);
        if (hit) hit.click();
      });
      menu.append(search);
    }
    const items = [...sel.options].map((opt) => {
      const item = el("button", "dropdown-item", opt.text);
      item.type = "button";
      if (opt.dataset.icon) item.prepend(icon(opt.dataset.icon, "mr-1"));
      item.addEventListener("click", () => {
        sel.value = opt.value;
        sync();
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      });
      menu.append(item);
      return item;
    });
    function sync() {
      const i = Math.max(sel.selectedIndex, 0);
      items.forEach((it, n) => it.classList.toggle("active", n === i));
      label(btn, sel.options[i] && sel.options[i].dataset.icon, sel.options[i] ? sel.options[i].text : "");
    }
    sync();
    // Bei position: fixed würde sich min-width: 100% auf den Bildschirm beziehen, nicht auf den Button
    $(wrap).on("show.bs.dropdown", () => {
      menu.style.minWidth = btn.offsetWidth + "px";
      // Niedrige Bildschirme: Das Menü darf nur so hoch sein wie der Platz über oder unter dem Button
      const box = btn.getBoundingClientRect();
      menu.style.maxHeight = Math.min(288, Math.max(box.top, innerHeight - box.bottom) - 16) + "px";
    });
    $(wrap).on("shown.bs.dropdown", () => {
      const a = menu.querySelector(".active");
      if (a) a.scrollIntoView({ block: "nearest" });
      (search || a || btn).focus();
    });
  }

  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  const german = (s) => s.split("-").reverse().join(".");

  function enhanceDate(input) {
    input.type = "hidden";
    const { wrap, btn, menu } = dropdown(input, "s-select", "s-cal");
    let view = new Date();

    function show() {
      label(btn, "fa-calendar-alt", input.value ? german(input.value) : "Kein Datum");
    }

    function pick(value) {
      input.value = value;
      show();
      $(btn).dropdown("hide");
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function navButton(iconName, title, step) {
      const b = el("button", "btn btn-sm btn-secondary");
      b.type = "button";
      b.title = title;
      b.setAttribute("aria-label", title);
      b.append(icon(iconName));
      b.addEventListener("click", () => {
        view = new Date(view.getFullYear(), view.getMonth() + step, 1);
        render();
      });
      return b;
    }

    function render() {
      const today = iso(new Date());
      const head = el("div", "s-cal-head");
      head.append(navButton("fa-chevron-left", "Vorheriger Monat", -1),
        el("strong", "", MONTHS[view.getMonth()] + " " + view.getFullYear()),
        navButton("fa-chevron-right", "Nächster Monat", 1));

      const grid = el("div", "s-cal-grid");
      DAYS.forEach((d) => grid.append(el("span", "s-cal-day text-muted", d)));
      const first = (new Date(view.getFullYear(), view.getMonth(), 1).getDay() + 6) % 7; // Woche beginnt am Montag
      for (let i = 0; i < first; i++) grid.append(el("span"));
      const last = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
      for (let n = 1; n <= last; n++) {
        const value = iso(new Date(view.getFullYear(), view.getMonth(), n));
        const b = el("button", "btn btn-sm " + (value === input.value ? "btn-warning" : value === today ? "btn-outline-warning" : "btn-dark"), String(n));
        b.type = "button";
        b.addEventListener("click", () => pick(value));
        grid.append(b);
      }

      const foot = el("div", "s-cal-foot");
      const todayBtn = el("button", "btn btn-sm btn-secondary", "Heute");
      const clearBtn = el("button", "btn btn-sm btn-secondary", "Löschen");
      todayBtn.type = clearBtn.type = "button";
      todayBtn.addEventListener("click", () => pick(today));
      clearBtn.addEventListener("click", () => pick(""));
      foot.append(todayBtn, clearBtn);
      menu.replaceChildren(head, grid, foot);
    }

    menu.addEventListener("click", (e) => e.stopPropagation()); // Blättern lässt den Kalender offen
    $(wrap).on("show.bs.dropdown", () => {
      view = input.value ? new Date(input.value + "T12:00:00") : new Date();
      render();
    });
    show();
  }

  function confirmDialog() {
    let dialog = document.getElementById("s-confirm");
    if (dialog) return dialog;
    dialog = el("div", "modal fade");
    dialog.id = "s-confirm";
    dialog.tabIndex = -1;
    dialog.innerHTML = '<div class="modal-dialog modal-dialog-centered modal-sm"><div class="modal-content">' +
      '<div class="modal-body"></div><div class="modal-footer">' +
      '<button type="button" class="btn btn-secondary" data-dismiss="modal">Abbrechen</button>' +
      '<button type="button" class="btn btn-danger s-ok"><i class="fas fa-trash-alt mr-1"></i>Löschen</button>' +
      "</div></div></div>";
    document.body.append(dialog);
    return dialog;
  }

  function enhanceConfirm(form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const dialog = confirmDialog();
      dialog.querySelector(".modal-body").textContent = form.dataset.confirm;
      dialog.querySelector(".s-ok").onclick = () => { $(dialog).modal("hide"); submit(form); };
      $(dialog).modal("show");
    });
  }

  function enhance(root) {
    root.querySelectorAll("select:not([hidden])").forEach(enhanceSelect);
    root.querySelectorAll('input[type="date"]').forEach(enhanceDate);
    root.querySelectorAll("form[data-confirm]").forEach(enhanceConfirm);
    if (location.hash) $(root).find('a[data-toggle="tab"][href="' + location.hash + '"]').tab("show");
  }


  /* Sync-Kachel auf der Startseite: Meldet sich ein Skript nicht mehr, gibt es kein Ereignis vom Server.
     Darum steht die Frist im HTML (data-offline-at) und hier wird nach Ablauf auf offline geschaltet. */
  setInterval(() => {
    const now = Date.now() / 1000;
    document.querySelectorAll("[data-offline-at]").forEach((el) => {
      if (Number(el.dataset.offlineAt) > now) return;
      el.removeAttribute("data-offline-at");
      el.classList.replace("is-online", "is-offline");
      const state = el.querySelector(".s-sync-state");
      if (state) state.textContent = "offline";
      const tile = el.closest(".s-sync-tile");
      const icon = tile && tile.querySelector("[data-sync-icon]");
      if (icon && !tile.querySelector(".s-sync.is-online")) icon.classList.replace("text-success", "text-danger");
    });
  }, 10000);

  /* Lebenszyklus für Seitenskripte: satis:load meldet neue Inhalte (beim Start, nach Seitenwechsel und Live-Tausch),
     satis:unload kommt vorher für Inhalte, die gleich verschwinden. event.target ist der Bereich. */
  const signal = (target, name) => target.dispatchEvent(new CustomEvent(name, { bubbles: true }));
  const part = (root, name) => root.querySelector('[data-part="' + name + '"]');

  /* Live: Ändert jemand etwas, holt sich jede offene Seite den neuen Stand, ohne Neuladen.
     Getauscht werden nur Bereiche mit data-live="name", deren HTML sich wirklich geändert hat.
     Wer gerade tippt oder ein Menü offen hat, behält seinen Bereich, bis er fertig ist.
     Gefragt wird nur, solange die Seite sichtbar ist, das schont den Akku am Handy. */
  const POLL_MS = 4000;
  const live = { swap: {}, last: {} };  // swap[name](alt, neu): eigener Tausch, z. B. für den Graph
  window.satisLive = live;

  function regions(root) {
    const out = {};
    root.querySelectorAll("[data-live]").forEach((r) => { out[r.dataset.live] = r; });
    if (root.matches && root.matches("[data-live]")) out[root.dataset.live] = root;
    return out;
  }

  const TYPING = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not(.s-search), textarea';
  document.addEventListener("input", (e) => {
    const r = e.target.closest && e.target.matches(TYPING) && e.target.closest("[data-live]");
    if (r) r.dataset.liveDirty = "1";
  });

  function busy(r) {
    if (r.dataset.liveDirty) return true;
    if (r.querySelector(".dropdown-menu.show, .modal.show")) return true;
    const a = document.activeElement;
    return Boolean(a && r.contains(a) && a.matches(TYPING));
  }

  /* force: nach eigenem Klick oder Absenden, dann wird auch getauscht, wo man gerade tippt */
  function apply(doc, force) {
    let pending = false;
    const fresh = regions(doc);
    Object.entries(regions(document)).forEach(([name, r]) => {
      const next = fresh[name];
      if (!next || next.innerHTML === live.last[name]) return;
      if (!force && busy(r)) { pending = true; return; }
      live.last[name] = next.innerHTML;
      delete r.dataset.liveDirty;
      if (live.swap[name] && live.swap[name](r, next)) return;
      signal(r, "satis:unload");
      r.replaceChildren(...next.childNodes);
      enhance(r);
      signal(r, "satis:load");
    });
    return pending;
  }

  const body = document.body;
  let rev = body.dataset.liveRev;
  let pending = false;
  let running = false;
  let timer = null;

  function refresh() {
    const url = location.href;
    return fetch(url, { headers: { "X-Satis-Live": "1" }, credentials: "same-origin" })
      .then((res) => (res.ok && !res.redirected ? res.text() : null))
      .then((html) => {
        // Inzwischen auf eine andere Seite gewechselt: Die Antwort passt nicht mehr
        if (html !== null && url === location.href && !nav.busy) pending = apply(new DOMParser().parseFromString(html, "text/html"));
      });
  }

  /* Neues Update, aber der Tab läuft noch mit den alten Skripten? Dann einmal neu laden, nur nicht mitten im Tippen. */
  function outdated(version) {
    const meta = document.querySelector('meta[name="satis-assets"]');
    const active = document.activeElement;
    if (!version || !meta || meta.content === version || (active && active.matches(TYPING))) return false;
    if (sessionStorage.getItem("satis-reloaded") === version) return false;  // nie im Kreis laden
    sessionStorage.setItem("satis-reloaded", version);
    return true;
  }

  function poll() {
    if (running || document.hidden || nav.busy) return;
    running = true;
    fetch(body.dataset.liveUrl, { cache: "no-store", credentials: "same-origin" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) return null;
        if (outdated(data.assets)) { location.reload(); return null; }
        const changed = String(data.rev) !== rev;
        rev = String(data.rev);
        if (changed) {
          prefetched.clear();
          document.dispatchEvent(new CustomEvent("satis:live", { detail: data }));
        }
        return changed || pending ? refresh() : null;
      })
      .catch(() => {})
      .finally(() => { running = false; });
  }

  function schedule() {
    clearInterval(timer);
    timer = null;
    if (!document.hidden && body.dataset.liveUrl) timer = setInterval(poll, POLL_MS);
  }

  /* Seitenwechsel ohne Neuladen: Links und Formulare holen die neue Seite im Hintergrund.
     Getauscht wird nur, was anders ist: Kopf, Brotkrumen, Meldungen und Inhalt einzeln.
     Bleibt man auf derselben Seite und das Gerüst ist gleich (z. B. im Rechner), werden nur die
     data-live-Bereiche getauscht, die Karte und der Graph bleiben also stehen.
     Fehlende Skripte der neuen Seite werden nachgeladen. Klappt etwas nicht, lädt der Browser ganz normal.
     Mit data-no-nav an Link oder Formular bleibt es beim normalen Laden. */
  const PARTS = ["header", "crumbs", "flash"];
  const PREFETCH_MS = 10000;
  const nav = { busy: false, parts: {}, skeleton: "" };
  const prefetched = new Map();  // URL -> { at, promise }, für Links unter Maus oder Finger
  const assets = () => { const m = document.querySelector('meta[name="satis-assets"]'); return m ? m.content : ""; };
  const pageUrl = (u) => { const x = new URL(u, location.href); x.hash = ""; return x.href; };

  /* Gerüst des Inhalts: das HTML ohne die Live-Bereiche. Gleiches Gerüst = nur Bereiche tauschen. */
  function skeleton(content) {
    const c = content.cloneNode(true);
    if (c.matches("[data-live]")) c.replaceChildren();
    c.querySelectorAll("[data-live]").forEach((r) => r.replaceChildren());
    return c.outerHTML;
  }

  /* Original-HTML merken, bevor enhance() Felder umbaut, sonst sähe jeder Vergleich eine Änderung */
  function remember(root) {
    PARTS.forEach((name) => { const p = part(root, name); if (p) nav.parts[name] = p.innerHTML; });
    const content = part(root, "content");
    if (content) {
      nav.skeleton = skeleton(content);
      Object.entries(regions(content)).forEach(([name, r]) => { live.last[name] = r.innerHTML; });
    }
  }

  /* Ladebalken oben und leicht abgedunkelter Inhalt, erst nach kurzer Zeit, damit schnelle Wechsel nicht flackern */
  const bar = el("div", "s-progress");
  body.append(bar);
  const progress = {
    width: 0, trickle: null, delay: null, shown: false,
    set(w, instant) {
      this.width = w;
      bar.classList.toggle("s-instant", Boolean(instant));
      bar.style.transform = "scaleX(" + w + ")";
    },
    start() {
      this.stop();
      this.delay = setTimeout(() => {
        this.shown = true;
        this.set(0, true);
        void bar.offsetWidth;  // Neustart ohne Übergang
        bar.classList.add("s-run");
        this.set(0.15);
        this.trickle = setInterval(() => this.set(this.width + (0.92 - this.width) * 0.08), 200);
        const content = part(document, "content");
        if (content) content.classList.add("s-loading");
      }, 120);
    },
    stop() {
      clearTimeout(this.delay);
      clearInterval(this.trickle);
    },
    done() {
      this.stop();
      const content = part(document, "content");
      if (content) content.classList.remove("s-loading");
      if (!this.shown) return;
      this.shown = false;
      this.set(1);
      setTimeout(() => bar.classList.remove("s-run"), 200);
    },
  };

  function read(url, init) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, init)).then((res) => {
      const type = res.headers.get("Content-Type") || "";
      if (new URL(res.url).origin !== location.origin) throw new Error("fremde Seite");
      if (!type.includes("text/html")) return { html: null, url: res.url };
      return res.text().then((html) => ({ html, url: res.url }));
    });
  }

  function prefetch(url) {
    const key = pageUrl(url);
    const hit = prefetched.get(key);
    if (hit && Date.now() - hit.at < PREFETCH_MS) return hit.promise;
    const promise = read(key);
    promise.catch(() => prefetched.delete(key));
    prefetched.set(key, { at: Date.now(), promise });
    return promise;
  }

  function loadScripts(doc) {
    const have = new Set([...document.scripts].map((s) => s.src));
    return [...doc.querySelectorAll("script[src]")]
      .map((s) => new URL(s.getAttribute("src"), location.href).href)
      .filter((src) => !have.has(src))
      .reduce((chain, src) => chain.then(() => new Promise((ok, fail) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = ok;
        s.onerror = fail;
        body.append(s);
      })), Promise.resolve());
  }

  let seq = 0;
  let controller = null;

  /* opts: form (für den Notfall), body (POST), history: "push" | "replace" | "none", scroll (zurück/vor) */
  function go(url, opts) {
    opts = opts || {};
    const id = ++seq;
    if (controller) controller.abort();
    controller = new AbortController();
    nav.busy = true;
    $("#mainNav.show").collapse("hide");
    progress.start();
    const wanted = new URL(url, location.href);
    let request;
    if (opts.body) {
      prefetched.clear();
      request = read(wanted.href, { method: "POST", body: opts.body, signal: controller.signal });
    } else {
      const key = pageUrl(wanted);
      const hit = prefetched.get(key);
      request = hit && Date.now() - hit.at < PREFETCH_MS ? hit.promise : read(key, { signal: controller.signal });
      prefetched.delete(key);
    }
    return request.then(({ html, url: final }) => {
      if (id !== seq) return null;
      if (html === null) {  // Keine Seite (z. B. JSON): nach dem Absenden den aktuellen Stand zeigen, sonst normal öffnen
        if (opts.body) location.reload(); else location.href = final;
        return null;
      }
      const doc = new DOMParser().parseFromString(html, "text/html");
      const meta = doc.querySelector('meta[name="satis-assets"]');
      if (!part(doc, "content") || !meta || meta.content !== assets()) {
        // Fehlerseite nach dem Absenden direkt zeigen, ein neuer Abruf würde nur "Methode nicht erlaubt" liefern
        if (opts.body && !part(doc, "content")) { document.open(); document.write(html); document.close(); return null; }
        location.href = final;  // Update eingespielt oder Seite ohne Satis-Rahmen: einmal richtig laden
        return null;
      }
      const target = new URL(final);
      if (!target.hash && wanted.hash && pageUrl(final) === pageUrl(wanted)) target.hash = wanted.hash;
      return loadScripts(doc).then(() => { if (id === seq) render(doc, target, opts); });
    }).catch((err) => {
      if (id !== seq || (err && err.name === "AbortError")) return;
      if (opts.form) HTMLFormElement.prototype.submit.call(opts.form);
      else location.href = wanted.href;
    }).finally(() => {
      if (id !== seq) return;
      nav.busy = false;
      progress.done();
    });
  }

  function activeTab(root) {
    const a = root.querySelector('a.active[data-toggle="tab"]');
    return a ? a.getAttribute("href") : null;
  }

  function render(doc, url, opts) {
    const samePage = url.pathname === location.pathname;
    const sameUrl = pageUrl(url) === pageUrl(location.href);
    const mode = opts.history || (sameUrl ? "replace" : "push");
    if (mode === "push") {
      history.replaceState(Object.assign({}, history.state, { satis: true, scroll: scrollY }), "");
      history.pushState({ satis: true, scroll: 0 }, "", url.href);
    } else if (mode === "replace") {
      history.replaceState({ satis: true, scroll: scrollY }, "", url.href);
    }
    shown = pageUrl(url);
    document.title = doc.title;
    if (doc.body.dataset.liveRev) rev = body.dataset.liveRev = doc.body.dataset.liveRev;

    PARTS.forEach((name) => {
      const cur = part(document, name), next = part(doc, name);
      if (!cur || !next || next.innerHTML === nav.parts[name]) return;
      nav.parts[name] = next.innerHTML;
      cur.replaceChildren(...next.childNodes);
      enhance(cur);
    });

    const cur = part(document, "content"), next = part(doc, "content");
    const frame = skeleton(next);
    if (samePage && frame === nav.skeleton) {
      apply(doc, true);  // Nur die Bereiche, die sich geändert haben, Scrollstand bleibt
      if (opts.scroll !== undefined) scrollTo(0, opts.scroll);
      pending = false;
      return;
    }
    const tab = activeTab(cur);
    nav.skeleton = frame;
    live.last = {};
    Object.entries(regions(next)).forEach(([name, r]) => { live.last[name] = r.innerHTML; });
    signal(cur, "satis:unload");
    const fresh = document.importNode(next, true);
    fresh.classList.add("s-enter");
    fresh.addEventListener("animationend", () => fresh.classList.remove("s-enter"), { once: true });
    cur.replaceWith(fresh);
    enhance(fresh);
    // Gleiche Tabs auf der neuen Seite (z. B. Rechner -> gespeicherter Plan): offener Tab bleibt offen
    if (!url.hash && tab) $(fresh).find('a[data-toggle="tab"][href="' + tab + '"]').tab("show");
    signal(fresh, "satis:load");
    pending = false;
    const anchor = url.hash && document.getElementById(decodeURIComponent(url.hash.slice(1)));
    if (opts.scroll !== undefined) scrollTo(0, opts.scroll);
    else if (anchor && !anchor.classList.contains("tab-pane")) anchor.scrollIntoView();
    else scrollTo(0, 0);
  }

  function local(url) {
    return url.origin === location.origin && !url.pathname.startsWith("/cdn-cgi/") && !url.pathname.startsWith("/static/");
  }

  function linkUrl(e) {
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download") || a.dataset.toggle || "noNav" in a.dataset) return null;
    const url = new URL(a.href, location.href);
    if (!local(url)) return null;
    if (url.hash && pageUrl(url) === pageUrl(location.href)) return null;  // Sprungmarke auf derselben Seite
    return url;
  }

  function submit(form, submitter) {
    const attr = (name) => (submitter && submitter.getAttribute("form" + name)) || form.getAttribute(name);
    const method = (attr("method") || "get").toLowerCase();
    const url = new URL(attr("action") || location.href, location.href);
    if ("noNav" in form.dataset || (attr("target") && attr("target") !== "_self") || !local(url) || method === "dialog") {
      HTMLFormElement.prototype.submit.call(form);
      return;
    }
    const data = new FormData(form);
    if (submitter && submitter.name) data.append(submitter.name, submitter.value);
    if (method === "get") {
      url.search = new URLSearchParams(data).toString();
      go(url.href, { form });
    } else {
      const multipart = (attr("enctype") || "").includes("multipart");
      go(url.href, { form, body: multipart ? data : new URLSearchParams(data) });
    }
  }

  // Am window, damit Skripte am document (z. B. Abhaken) vorher preventDefault() aufrufen können
  window.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const url = linkUrl(e);
    if (!url) return;
    e.preventDefault();
    go(url.href);
  });
  window.addEventListener("submit", (e) => {
    if (e.defaultPrevented) return;
    e.preventDefault();
    submit(e.target, e.submitter);
  });

  // Vorladen, sobald Maus oder Finger auf einem Link ist: Der Wechsel fühlt sich dann sofort an
  let hover = null;
  document.addEventListener("mouseover", (e) => {
    const url = linkUrl(e);
    clearTimeout(hover);
    if (url && pageUrl(url) !== pageUrl(location.href)) hover = setTimeout(() => prefetch(url.href).catch(() => {}), 80);
  });
  document.addEventListener("touchstart", (e) => {
    const url = linkUrl(e);
    if (url && pageUrl(url) !== pageUrl(location.href)) prefetch(url.href).catch(() => {});
  }, { passive: true });

  let shown = pageUrl(location.href);
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  history.replaceState(Object.assign({}, history.state, { satis: true }), "");
  window.addEventListener("popstate", (e) => {
    if (pageUrl(location.href) === shown) return;  // nur die Sprungmarke hat sich geändert
    go(location.href, { history: "none", scroll: e.state && e.state.scroll ? e.state.scroll : 0 });
  });

  // Ältere Browser: requestSubmit() löst wie ein Klick auf Absenden das submit-Ereignis aus
  if (!HTMLFormElement.prototype.requestSubmit) {
    HTMLFormElement.prototype.requestSubmit = function () {
      const b = document.createElement("button");
      b.type = "submit";
      b.hidden = true;
      this.append(b);
      b.click();
      b.remove();
    };
  }

  if (body.dataset.liveUrl) {
    document.addEventListener("visibilitychange", () => { schedule(); if (!document.hidden) poll(); });
    schedule();
  }

  window.satisEnhance = enhance;
  window.satisNav = { go, submit };
  remember(document);  // vor dem Umbau der Felder
  enhance(document);
  // Seitenskripte stehen unter satis.js und hängen ihre Listener erst noch an
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => signal(body, "satis:load"));
  } else {
    signal(body, "satis:load");
  }
})();
