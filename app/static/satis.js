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
    $(btn).dropdown({ popperConfig: { positionFixed: true } });
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
      dialog.querySelector(".s-ok").onclick = () => form.submit();
      $(dialog).modal("show");
    });
  }

  function enhance(root) {
    root.querySelectorAll("select:not([hidden])").forEach(enhanceSelect);
    root.querySelectorAll('input[type="date"]').forEach(enhanceDate);
    root.querySelectorAll("form[data-confirm]").forEach(enhanceConfirm);
    if (location.hash) $(root).find('a[data-toggle="tab"][href="' + location.hash + '"]').tab("show");
  }

  window.satisEnhance = enhance;
  enhance(document);
})();
