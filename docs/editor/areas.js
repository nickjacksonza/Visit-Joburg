// Area lists editor: content/areas.json. Each list names a cluster of suburbs (The Parks, Town), picks the colour they
// rise in on the map, and says where it shows: in the area picker, in the Area lists panel, or both.
// Sign-in and saving are in core.js. The suburbs come from src/data/neighbourhoods.json on GitHub.
(function () {
  "use strict";
  var L = window.AreasLib, api = null, places = null;
  var el = function (t, a, k) { return api.el(t, a, k); };
  var NAMES = { yellow: "Yellow", orange: "Orange", red: "Red", pink: "Pink", violet: "Violet", blue: "Blue", teal: "Teal", green: "Green" };

  function extra(a) {  // every area, grouped by part of the city, from neighbourhoods.json
    return a.getFile("src/data/neighbourhoods.json").then(function (f) {
      var d = JSON.parse(f.text), byId = {};
      d.places.forEach(function (p) { if (p.kind === "area") byId[p.id] = p; });
      places = { byId: byId, regions: d.regions };
      return byId;
    });
  }

  function card(l, i, all) {
    var c = el("section", { class: "row list" });
    var name = el("input", { value: l.name, maxlength: L.LIMITS.name, required: "", oninput: function () { l.name = this.value; head.textContent = this.value || "New list"; api.touch(); } });
    var aka = el("input", { value: (l.aka || []).join(", "), placeholder: "for example: the CBD, the inner city", oninput: function () {
      l.aka = this.value.split(",").map(function (s) { return s.trim(); }).filter(Boolean); api.touch(); } });
    var head = el("h2", { text: l.name || "New list" });
    var sw = el("div", { class: "swatches", role: "radiogroup", "aria-label": "Colour" });
    api.work.colours.forEach(function (col) {
      var r = el("input", { type: "radio", name: "colour-" + i, value: col, onchange: function () { l.colour = col; api.touch(); } });
      r.checked = l.colour === col;
      sw.appendChild(el("label", { class: "sw sw-" + col }, [r, document.createTextNode(" " + (NAMES[col] || col))]));
    });
    function toggle(key, label) {
      var b = el("input", { type: "checkbox", onchange: function () { l[key] = this.checked; api.touch(); } });
      b.checked = l[key];
      return el("label", { class: "inline" }, [b, document.createTextNode(" " + label)]);
    }
    var count = el("span", { text: "" });
    function recount() { count.textContent = l.areas.length + " ticked"; }
    recount();
    var filter = el("input", { type: "search", placeholder: "Find a suburb", "aria-label": "Find a suburb", oninput: function () {
      var q = this.value.trim().toLowerCase();
      [].forEach.call(box.querySelectorAll("label"), function (lb) { lb.hidden = q && lb.textContent.toLowerCase().indexOf(q) < 0; });
    } });
    var box = el("div", { class: "suburbs" });
    places.regions.forEach(function (r) {
      var here = Object.keys(places.byId).map(function (k) { return places.byId[k]; }).filter(function (p) { return p.region === r.id; })
        .sort(function (a, b) { return a.name < b.name ? -1 : 1; });
      if (!here.length) return;
      var g = el("fieldset", {}, [el("legend", { text: r.name })]);
      here.forEach(function (p) {
        var cb = el("input", { type: "checkbox", value: p.id, onchange: function () {
          if (this.checked) { if (l.areas.indexOf(p.id) < 0) l.areas.push(p.id); } else l.areas = l.areas.filter(function (a) { return a !== p.id; });
          recount(); api.touch(); } });
        cb.checked = l.areas.indexOf(p.id) >= 0;
        g.appendChild(el("label", { class: "inline" + (p.major ? "" : " unmapped"), title: p.major ? "" : "Not on the map yet" }, [cb, document.createTextNode(" " + p.name + (p.major ? "" : " *"))]));
      });
      box.appendChild(g);
    });
    function move(d) { var j = i + d; if (j < 0 || j >= all.length) return; all.splice(j, 0, all.splice(i, 1)[0]); render(api); }
    [
      head,
      el("label", { class: "wide" }, [document.createTextNode("Name"), name]),
      el("label", { class: "wide" }, [document.createTextNode("Also called (optional, separate with commas)"), aka]),
      el("div", { class: "wide" }, [el("p", { class: "lab", text: "Colour on the map" }), sw]),
      el("div", { class: "wide tags" }, [toggle("picker", "Show in the area picker"), toggle("panel", "Show in the Area lists panel")]),
      el("details", { class: "wide" }, [el("summary", {}, [document.createTextNode("Suburbs ("), count, document.createTextNode(")")]),
        el("p", { class: "note", text: "Suburbs marked * are not drawn on the map yet. They join the list now and show once they're mapped." }), filter, box]),
      el("div", { class: "acts wide" }, [
        el("span", {}, [el("button", { class: "btn", type: "button", text: "Move up", onclick: function () { move(-1); } }), document.createTextNode(" "),
          el("button", { class: "btn", type: "button", text: "Move down", onclick: function () { move(1); } })]),
        el("button", { class: "btn", type: "button", text: "Remove", "aria-label": "Remove " + (l.name || "this list"), onclick: function () {
          if (confirm("Remove " + (l.name || "this list") + "?")) { all.splice(i, 1); render(api); } } })])
    ].forEach(function (n) { c.appendChild(n); });
    return c;
  }

  function render(a) {
    api = a;
    var app = document.getElementById("app"); app.textContent = "";
    app.appendChild(el("p", { class: "note", text: "Each list is a name people use for a group of suburbs. On the home-page map, picking a list raises its suburbs in its colour. The order here is the order on the map." }));
    app.appendChild(el("button", { class: "btn", type: "button", text: "Add a list", onclick: function () {
      api.work.lists.unshift({ id: "", name: "", aka: [], colour: api.work.colours[0], picker: true, panel: true, areas: [] }); render(api);
      app.querySelector(".row input").focus();
    } }));
    api.work.lists.forEach(function (l, i) { app.appendChild(card(l, i, api.work.lists)); });
    if (!api.work.lists.length) app.appendChild(el("p", { text: "No lists yet." }));
    api.touch();
  }

  EditorCore({ file: "content/areas.json", noun: "area lists", commit: "Area lists", siteUrl: "../index.html#map-h",
    clean: function (d, byId) { return L.clean(d, byId); }, dump: L.dump, summary: L.summary, render: render, extra: extra });
})();
