// Events editor: rules for content/events.json. No DOM here, so tools/test_editor.js runs it in Node.
// build.py applies the same rules (load_events), so a bad edit fails the rebuild and nothing goes live.
(function (root) {
  "use strict";
  var LIMITS = { name: 80, description: 300, place: 60, street: 80, url: 200 };
  var MAX_PRICE = 100000, MAX_EVENTS = 200;
  var BAD = /[<>\x00-\x1f\x7f]/;
  var SLUG = /^[a-z0-9][a-z0-9-]{0,60}$/;
  var WHEN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

  function text(v, field, limit, need) {
    if (typeof v !== "string") throw new Error(field + " must be text.");
    v = v.split(/\s+/).filter(Boolean).join(" ");
    if (need && !v) throw new Error(field + " is needed for every event.");
    if (v.length > limit) throw new Error(field + " is too long (" + v.length + " characters, the limit is " + limit + ").");
    if (BAD.test(v)) throw new Error(field + " can't contain < or > or control characters.");
    return v;
  }
  function when(v, field, name) {
    if (typeof v !== "string" || !WHEN.test(v)) throw new Error(field + " for " + name + " must be a date and time, like 2026-12-05T09:00.");
    var d = new Date(v + ":00Z");
    if (isNaN(d) || d.toISOString().slice(0, 16) !== v) throw new Error(field + " for " + name + " is not a real date.");
    return v;
  }
  function price(v, name) {
    if (typeof v !== "number" || !isFinite(v) || Math.abs(Math.round(v * 100) - v * 100) > 1e-9)
      throw new Error("Price for " + name + " must be a number with at most two decimals, like 150 or 99.50.");
    if (v < 0 || v > MAX_PRICE) throw new Error("Price for " + name + " must be between 0 and " + MAX_PRICE + ".");
    return Math.round(v * 100) / 100;
  }
  function slug(name) { return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "event"; }

  function cleanEvent(e, seen) {
    var name = text(e.name, "Name", LIMITS.name, true);
    var id = e.id || slug(name);
    if (!SLUG.test(id)) throw new Error("Bad id '" + id + "'.");
    if (seen[id]) throw new Error("Two events share the id '" + id + "'. Rename one.");
    seen[id] = 1;
    var start = when(e.start, "Start", name), end = when(e.end, "End", name);
    if (end <= start) throw new Error("The end of " + name + " must be after its start.");
    var url = text(e.url, "Link", LIMITS.url, true);
    if (!/^https:\/\/[^\s]+\.[^\s]+$/.test(url)) throw new Error("The link for " + name + " must start with https://.");
    if (typeof e.published !== "boolean") throw new Error("Published must be on or off.");
    return { id: id, name: name, description: text(e.description || "", "Description", LIMITS.description, true),
             start: start, end: end, place: text(e.place, "Area", LIMITS.place, true), street: text(e.street, "Street", LIMITS.street, true),
             url: url, price: price(e.price, name), published: e.published };
  }

  // Returns a cleaned copy, soonest event first, with keys in the file's usual order. Throws Error with a plain message.
  function clean(data) {
    if (!data || !Array.isArray(data.events)) throw new Error("The file has no events list.");
    if (typeof data.timezone !== "string" || !/^[+-](0\d|1[0-4]):[0-5]\d$/.test(data.timezone)) throw new Error("The file's timezone must be an offset like +02:00.");
    if (data.events.length > MAX_EVENTS) throw new Error("Keep the list to " + MAX_EVENTS + " events. Remove some past ones.");
    var seen = {};
    var events = data.events.map(function (e) { return cleanEvent(e, seen); });
    events.sort(function (a, b) { return a.start < b.start ? -1 : a.start > b.start ? 1 : 0; });
    return { timezone: data.timezone, currency: data.currency, events: events };
  }

  var KEYS = ["id", "name", "description", "start", "end", "place", "street", "url", "price", "published"];
  // One event per line keeps edits on GitHub readable: the diff shows one changed line per event.
  function dump(data) {
    var lines = ["{", '  "timezone": ' + JSON.stringify(data.timezone) + ",", '  "currency": ' + JSON.stringify(data.currency) + ",", '  "events": ['];
    data.events.forEach(function (e, n) {
      lines.push("    {" + KEYS.map(function (k) { return JSON.stringify(k) + ": " + JSON.stringify(e[k]); }).join(", ") + "}" + (n < data.events.length - 1 ? "," : ""));
    });
    lines.push("  ]", "}");
    return lines.join("\n") + "\n";
  }

  function summary(a, b) {
    var out = [], old = {}, nu = {};
    a.events.forEach(function (e) { old[e.id] = e; });
    b.events.forEach(function (e) { nu[e.id] = e; });
    Object.keys(nu).forEach(function (id) {
      if (!old[id]) return out.push("Added " + nu[id].name);
      if (JSON.stringify(old[id]) !== JSON.stringify(nu[id])) out.push("Changed " + nu[id].name);
    });
    Object.keys(old).forEach(function (id) { if (!nu[id]) out.push("Removed " + old[id].name); });
    return out;
  }

  // True when the event's end (local time in the file's timezone) is before `now` (a Date).
  function ended(e, tz, now) { return new Date(e.end + ":00" + tz) < now; }

  var api = { LIMITS: LIMITS, clean: clean, dump: dump, summary: summary, slug: slug, ended: ended };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.EventsLib = api;
})(typeof self !== "undefined" ? self : this);
