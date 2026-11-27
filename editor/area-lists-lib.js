// Area lists editor: rules for content/area-lists.json. No DOM here, so tools/test_editor.js runs it in Node.
// build.py applies the same rules (load_areas), so a bad edit fails the rebuild and nothing goes live.
(function (root) {
  "use strict";
  var LIMITS = { name: 40, aka: 40, akas: 5, areas: 80, lists: 40 };
  var BAD = /[<>\x00-\x1f\x7f]/;
  var SLUG = /^[a-z0-9][a-z0-9-]{0,60}$/;

  function text(v, field, limit, need) {
    if (typeof v !== "string") throw new Error(field + " must be text.");
    v = v.split(/\s+/).filter(Boolean).join(" ");
    if (need && !v) throw new Error(field + " is needed for every list.");
    if (v.length > limit) throw new Error(field + " is too long (" + v.length + " characters, the limit is " + limit + ").");
    if (BAD.test(v)) throw new Error(field + " can't contain < or > or control characters.");
    return v;
  }
  function slug(name) { return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "list"; }

  // places: optional {id: true} of known area ids; when given, every area must be one of them.
  function cleanList(l, seen, colours, places) {
    var name = text(l.name, "Name", LIMITS.name, true);
    var id = l.id || slug(name);
    if (!SLUG.test(id)) throw new Error("Bad id '" + id + "'.");
    if (seen[id]) throw new Error("Two lists share the id '" + id + "'. Rename one.");
    seen[id] = 1;
    var aka = (l.aka || []).map(function (a) { return text(a, "Also called", LIMITS.aka, false); }).filter(Boolean);
    if (aka.length > LIMITS.akas) throw new Error(name + ": keep 'also called' to " + LIMITS.akas + " names.");
    if (colours.indexOf(l.colour) < 0) throw new Error(name + ": pick a colour.");
    if (typeof l.picker !== "boolean" || typeof l.panel !== "boolean") throw new Error(name + ": the show switches must be on or off.");
    if (!Array.isArray(l.areas) || !l.areas.length) throw new Error(name + ": tick at least one suburb.");
    if (l.areas.length > LIMITS.areas) throw new Error(name + ": keep it to " + LIMITS.areas + " suburbs.");
    var areas = [];
    l.areas.forEach(function (a) {
      if (typeof a !== "string" || !SLUG.test(a) || (places && !places[a])) throw new Error(name + ": '" + a + "' is not a suburb in the list.");
      if (areas.indexOf(a) < 0) areas.push(a);
    });
    return { id: id, name: name, aka: aka, colour: l.colour, picker: l.picker, panel: l.panel, areas: areas };
  }

  // Returns a cleaned copy with keys in the file's usual order. Throws Error with a plain message.
  function clean(data, places) {
    if (!data || !Array.isArray(data.lists)) throw new Error("The file has no lists.");
    if (!Array.isArray(data.colours) || !data.colours.length || data.colours.some(function (c) { return !SLUG.test(c); })) throw new Error("The file's colours list is broken.");
    if (data.lists.length > LIMITS.lists) throw new Error("Keep it to " + LIMITS.lists + " lists.");
    var seen = {};
    return { colours: data.colours.slice(), lists: data.lists.map(function (l) { return cleanList(l, seen, data.colours, places); }) };
  }

  var KEYS = ["id", "name", "aka", "colour", "picker", "panel", "areas"];
  // One list per line keeps edits on GitHub readable.
  function dump(data) {
    var lines = ["{", '  "colours": ' + JSON.stringify(data.colours).replace(/","/g, '", "') + ",", '  "lists": ['];
    data.lists.forEach(function (l, n) {
      lines.push("    {" + KEYS.map(function (k) {
        return JSON.stringify(k) + ": " + JSON.stringify(l[k]).replace(/","/g, '", "');
      }).join(", ") + "}" + (n < data.lists.length - 1 ? "," : ""));
    });
    lines.push("  ]", "}");
    return lines.join("\n") + "\n";
  }

  function summary(a, b) {
    var out = [], old = {}, nu = {};
    a.lists.forEach(function (l) { old[l.id] = l; });
    b.lists.forEach(function (l) { nu[l.id] = l; });
    Object.keys(nu).forEach(function (id) {
      if (!old[id]) return out.push("Added " + nu[id].name);
      if (JSON.stringify(old[id]) !== JSON.stringify(nu[id])) out.push("Changed " + nu[id].name);
    });
    Object.keys(old).forEach(function (id) { if (!nu[id]) out.push("Removed " + old[id].name); });
    if (!out.length && JSON.stringify(a.lists.map(function (l) { return l.id; })) !== JSON.stringify(b.lists.map(function (l) { return l.id; }))) out.push("Changed the order");
    return out;
  }

  var api = { LIMITS: LIMITS, clean: clean, dump: dump, summary: summary, slug: slug };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.AreasLib = api;
})(typeof self !== "undefined" ? self : this);
