// Events editor. Sign-in: the password decrypts a GitHub token kept in sealed.json (PBKDF2-SHA256 + AES-GCM, Web Crypto).
// Save: one commit of content/events.json through the GitHub contents API. The rebuild-docs workflow then rebuilds and publishes.
(function () {
  "use strict";
  var C = window.EDITOR_CONFIG, L = window.EventsLib;
  var API = "https://api.github.com/repos/" + C.owner + "/" + C.repo;
  var ITER = 1000000, MIN_PW = 16;
  var token = null, original = null, work = null, fileSha = null, busy = false;
  var enc = new TextEncoder(), dec = new TextDecoder();
  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k]; else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]); else n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }

  // ---- crypto
  function b64(bytes) { var s = ""; new Uint8Array(bytes).forEach(function (b) { s += String.fromCharCode(b); }); return btoa(s); }
  function unb64(s) { var bin = atob(s.replace(/\s/g, "")), out = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; }
  function deriveKey(pw, salt, iter) {
    return crypto.subtle.importKey("raw", enc.encode(pw), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", salt: salt, iterations: iter, hash: "SHA-256" }, base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    });
  }
  function seal(secret, pw) {
    var salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    return deriveKey(pw, salt, ITER).then(function (k) { return crypto.subtle.encrypt({ name: "AES-GCM", iv: iv }, k, enc.encode(secret)); })
      .then(function (ct) { return { v: 1, kdf: "PBKDF2-SHA256", iterations: ITER, salt: b64(salt), iv: b64(iv), ciphertext: b64(ct) }; });
  }
  function unseal(box, pw) {
    return deriveKey(pw, unb64(box.salt), box.iterations).then(function (k) { return crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(box.iv) }, k, unb64(box.ciphertext)); })
      .then(function (pt) { return dec.decode(pt); });
  }

  // ---- GitHub
  function gh(method, path, body) {
    var h = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
    if (token) h.Authorization = "Bearer " + token;
    if (body) h["Content-Type"] = "application/json";
    return fetch(API + path, { method: method, headers: h, cache: "no-store", body: body ? JSON.stringify(body) : undefined }).then(function (r) {
      return r.json().catch(function () { return null; }).then(function (j) {
        if (!r.ok) { var e = new Error((j && j.message) || "HTTP " + r.status); e.status = r.status; throw e; }
        return j;
      });
    }, function () { var e = new Error("Couldn't reach GitHub. Check your connection."); e.status = 0; throw e; });
  }
  function plain(e) {
    if (e.status === 401) return "GitHub refused the saved access key. It may have expired: set it up again.";
    if (e.status === 403 && /rate limit/i.test(e.message)) return "GitHub has had too many requests. Wait a while and try again.";
    if (e.status === 403 || e.status === 404) return "GitHub refused access (" + e.message + "). Check the token's permissions.";
    if (e.status === 409 || e.status === 422) return "The events changed on GitHub since you opened it. Reload the page and make your edits again.";
    return e.message;
  }
  function putFile(path, text, message, sha) {
    var body = { message: message, content: b64(enc.encode(text)), branch: C.branch };
    if (sha) body.sha = sha;
    return gh("PUT", "/contents/" + path, body);
  }
  function getFile(path) {
    return gh("GET", "/contents/" + path + "?ref=" + encodeURIComponent(C.branch)).then(function (f) { return { sha: f.sha, text: dec.decode(unb64(f.content)) }; });
  }

  function status(kind, title, lines, links) {
    var s = $("status"); s.textContent = "";
    if (!title) return;
    var box = el("div", { class: "msg " + kind }, [el("strong", { text: title })]);
    (lines || []).forEach(function (l) { box.appendChild(el("div", { text: l })); });
    (links || []).forEach(function (l) { box.appendChild(el("div", {}, [el("a", { href: l[1], text: l[0] })])); });
    s.appendChild(box);
  }

  // ---- sign in and set-up
  function showLogin(box) {
    $("login").hidden = false;
    var form = $("login-form"), msg = $("login-msg"), btn = form.querySelector("button");
    if (!box) { msg.hidden = false; msg.textContent = "The editor isn't set up yet. Open this page with #setup at the end of the address."; btn.disabled = true; return; }
    form.addEventListener("submit", function (e) {
      e.preventDefault(); btn.disabled = true; btn.textContent = "Checking…"; msg.hidden = true;
      unseal(box, $("password").value).then(function (t) {
        token = t; $("password").value = ""; $("login").hidden = true; $("editor").hidden = false; load();
      }, function () { msg.hidden = false; msg.textContent = "That password is not right."; btn.disabled = false; btn.textContent = "Sign in"; });
    });
  }
  function showSetup() {
    $("setup").hidden = false;
    var form = $("setup-form"), out = $("setup-msg"), btn = form.querySelector("button");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var t = $("setup-token").value.trim(), p1 = $("setup-pw").value, p2 = $("setup-pw2").value;
      function fail(m) { out.hidden = false; out.className = "msg err"; out.textContent = m; btn.disabled = false; btn.textContent = "Encrypt and save"; }
      if (p1 !== p2) return fail("The two passwords are different.");
      if (p1.length < MIN_PW) return fail("Use at least " + MIN_PW + " characters.");
      if (!/^(github_pat_|ghp_)[A-Za-z0-9_]+$/.test(t)) return fail("That doesn't look like a GitHub token.");
      btn.disabled = true; btn.textContent = "Working…"; token = t;
      seal(t, p1).then(function (box) {
        return getFile("editor/sealed.json").then(function (f) { return f.sha; }, function (er) { if (er.status === 404) return null; throw er; })
          .then(function (sha) { return putFile("editor/sealed.json", JSON.stringify(box, null, 2) + "\n", "Events editor: new encrypted access key", sha); });
      }).then(function (r) {
        token = null; form.reset(); out.hidden = false; out.className = "msg ok";
        out.textContent = "Saved (commit " + r.commit.sha.slice(0, 7) + "). The site rebuilds in a few minutes; then the password opens the editor."; btn.textContent = "Done";
      }, function (er) { token = null; fail(plain(er)); });
    });
  }

  // ---- editing
  function load() {
    status("", "", []);
    getFile(C.file).then(function (f) {
      fileSha = f.sha; original = L.clean(JSON.parse(f.text)); work = JSON.parse(JSON.stringify(original)); render();
    }, function (e) { status("err", "Couldn't load the events", [plain(e)]); });
  }
  function dirty() { return JSON.stringify(work) !== JSON.stringify(original); }
  function touch() {
    var n = dirty(); $("bar").hidden = !n; $("count").textContent = n ? "Unsaved changes" : "";
  }

  function field(label, input, cls) {
    return el("label", { class: cls || "" }, [document.createTextNode(label), input]);
  }
  function row(ev, idx) {
    var past = ev.end && L.ended(ev, work.timezone, new Date());
    var r = el("div", { class: "row" + (ev.published && !past ? "" : " off") });
    function inp(key, attrs, num) {
      var a = Object.assign({ value: ev[key] === undefined || (num && isNaN(ev[key])) ? "" : ev[key], oninput: function () {
        ev[key] = num ? (this.value === "" ? NaN : parseFloat(this.value)) : this.value; touch();
      } }, attrs || {});
      return el("input", a);
    }
    var pub = el("input", { type: "checkbox", onchange: function () { ev.published = this.checked; r.classList.toggle("off", !this.checked); touch(); } });
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
          if (confirm("Remove " + (ev.name || "this event") + "?")) { work.events.splice(idx, 1); render(); } } })])
    ].forEach(function (n) { r.appendChild(n); });
    return r;
  }

  function render() {
    var app = $("app"); app.textContent = "";
    app.appendChild(el("p", { class: "note", text: "Times are Johannesburg time. Events drop off the site once they end, and the list is sorted by date when you save." }));
    app.appendChild(el("button", { class: "btn", type: "button", text: "Add an event", onclick: function () {
      work.events.unshift({ id: "", name: "", description: "", start: "", end: "", place: "", street: "", url: "", price: 0, published: true }); render();
      app.querySelector(".row input").focus();
    } }));
    var past = work.events.filter(function (e) { return e.end && L.ended(e, work.timezone, new Date()); });
    if (past.length) app.appendChild(el("button", { class: "btn", type: "button", text: "Remove " + past.length + " ended event" + (past.length > 1 ? "s" : ""), onclick: function () {
      work.events = work.events.filter(function (e) { return past.indexOf(e) < 0; }); render();
    } }));
    work.events.forEach(function (ev, i) { app.appendChild(row(ev, i)); });
    if (!work.events.length) app.appendChild(el("p", { text: "No events yet." }));
    touch();
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function follow(sha) {
    var t0 = Date.now();
    function poll() {
      return gh("GET", "/actions/runs?head_sha=" + sha + "&per_page=5").then(function (r) {
        var run = (r.workflow_runs || []).filter(function (w) { return w.name === C.workflow; })[0];
        if (run && run.status === "completed") return run;
        if (Date.now() - t0 > 6 * 60 * 1000) return run || null;
        return sleep(6000).then(poll);
      });
    }
    return sleep(4000).then(poll);
  }

  function save() {
    var cleaned;
    try { cleaned = L.clean(work); } catch (e) { return status("err", "Check the events", [e.message]); }
    var lines = L.summary(original, cleaned);
    busy = true; $("save").disabled = true; $("save").textContent = "Publishing…";
    status("", "Publishing…", ["Saving to GitHub. Keep this page open."]);
    putFile(C.file, L.dump(cleaned), "Events: " + (lines.slice(0, 3).join(", ") || "update"), fileSha).then(function (r) {
      original = cleaned; work = JSON.parse(JSON.stringify(cleaned)); fileSha = r.content.sha; render();
      status("", "Saved. Now updating the website…", ["GitHub is rebuilding and checking the site. This takes one to three minutes."].concat(lines));
      return follow(r.commit.sha).then(function (run) {
        if (run && run.conclusion === "success") status("ok", "Published", ["The live page shows the change within a minute or two."].concat(lines), [["Open the live page", C.siteUrl]]);
        else if (run && run.status === "completed") status("err", "Saved, but the website was not updated", ["The site check failed, so the live page still shows the old events."], [["See what went wrong", run.html_url]]);
        else status("ok", "Saved", ["The live page updates within a few minutes."], [["Open the live page", C.siteUrl]]);
      }, function () { status("ok", "Saved", ["The live page updates within a few minutes."], [["Open the live page", C.siteUrl]]); });
    }).catch(function (e) { status("err", "Not published", [plain(e), "Your edits are still here."]); })
      .then(function () { busy = false; $("save").disabled = false; $("save").textContent = "Save and publish"; });
  }

  $("save").addEventListener("click", save);
  $("discard").addEventListener("click", function () { work = JSON.parse(JSON.stringify(original)); render(); });
  $("signout").addEventListener("click", function () { token = null; location.reload(); });
  window.addEventListener("beforeunload", function (e) { if (work && dirty() && !busy) { e.preventDefault(); e.returnValue = ""; } });

  if (!window.crypto || !crypto.subtle) { $("login-msg").hidden = false; $("login-msg").textContent = "This browser can't run the editor. Use an up-to-date Chrome, Safari or Firefox."; }
  else if (location.hash === "#setup") showSetup();
  else fetch("sealed.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }, function () { return null; }).then(showLogin);
})();
