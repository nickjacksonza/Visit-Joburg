// Events editor: the list of events in content/events.json. Sign-in and saving are in core.js.
(function () {
  "use strict";
  var L = window.EventsLib, api = null;
  var el = function (t, a, k) { return api.el(t, a, k); };
  function $(id) { return document.getElementById(id); }

  function field(label, input, cls) {
    return el("label", { class: cls || "" }, [document.createTextNode(label), input]);
  }
  function row(ev, idx) {
    var past = ev.end && L.ended(ev, api.work.timezone, new Date());
    var r = el("div", { class: "row" + (ev.published && !past ? "" : " off") });
    function inp(key, attrs, num) {
      var a = Object.assign({ value: ev[key] === undefined || (num && isNaN(ev[key])) ? "" : ev[key], oninput: function () {
        ev[key] = num ? (this.value === "" ? NaN : parseFloat(this.value)) : this.value; api.touch();
      } }, attrs || {});
      return el("input", a);
    }
    var pub = el("input", { type: "checkbox", onchange: function () { ev.published = this.checked; r.classList.toggle("off", !this.checked); api.touch(); } });
    pub.checked = ev.published;
    var head = el("p", { class: "wide note", text: past ? "Ended. The site no longer shows this event." : (ev.published ? "" : "Hidden from the site.") });
    [
      field("Name", inp("name", { maxlength: L.LIMITS.name, required: "" }), "wide"),
      field("Starts", inp("start", { type: "datetime-local", required: "" })),
      field("Ends", inp("end", { type: "datetime-local", required: "" })),
      field("Area", inp("place", { maxlength: L.LIMITS.place, required: "" })),
      field("Street", inp("street", { maxlength: L.LIMITS.street, required: "" })),
      field("Description", inp("description", { maxlength: L.LIMITS.description, required: "" }), "wide"),
      field("Link for tickets or details", inp("url", { type: "url", maxlength: L.LIMITS.url, placeholder: "https://", required: "" }), "wide"),
      field("Price in rand (0 for free)", inp("price", { type: "number", step: "0.01", min: "0" }, true)),
      el("div", { class: "acts" }, [el("label", { class: "inline" }, [pub, document.createTextNode(" Show on the site")])]),
      el("div", { class: "acts wide" }, [head,
        el("button", { class: "btn", type: "button", text: "Remove", "aria-label": "Remove " + (ev.name || "this event"), onclick: function () {
          if (confirm("Remove " + (ev.name || "this event") + "?")) { api.work.events.splice(idx, 1); render(api); } } })])
    ].forEach(function (n) { r.appendChild(n); });
    return r;
  }

  function render(a) {
    api = a;
    var app = $("app"); app.textContent = "";
    app.appendChild(el("p", { class: "note", text: "Times are Johannesburg time. Events drop off the site once they end, and the list is sorted by date when you save." }));
    app.appendChild(el("button", { class: "btn", type: "button", text: "Add an event", onclick: function () {
      api.work.events.unshift({ id: "", name: "", description: "", start: "", end: "", place: "", street: "", url: "", price: 0, published: true }); render(api);
      app.querySelector(".row input").focus();
    } }));
    var past = api.work.events.filter(function (e) { return e.end && L.ended(e, api.work.timezone, new Date()); });
    if (past.length) app.appendChild(el("button", { class: "btn", type: "button", text: "Remove " + past.length + " ended event" + (past.length > 1 ? "s" : ""), onclick: function () {
      api.work.events = api.work.events.filter(function (e) { return past.indexOf(e) < 0; }); render(api);
    } }));
    api.work.events.forEach(function (ev, i) { app.appendChild(row(ev, i)); });
    if (!api.work.events.length) app.appendChild(el("p", { text: "No events yet." }));
    api.touch();
  }

  EditorCore({ file: "content/events.json", noun: "events", commit: "Events", siteUrl: "../events.html",
    clean: function (d) { return L.clean(d); }, dump: L.dump, summary: L.summary, render: render });
})();
