// Shared by the editors (events, area lists). Sign-in: the password decrypts a GitHub token kept in sealed.json
// (PBKDF2-SHA256 + AES-GCM, Web Crypto). Save: one commit of the editor's JSON file through the GitHub contents API.
// The rebuild-docs workflow then rebuilds and publishes.
//
// EditorCore({ file, noun, siteUrl, clean(obj, extra), dump(obj), summary(a, b), render(api), extra(api) })
//   extra (optional) loads more data after sign-in, e.g. the list of suburbs; it returns a promise.
//   render draws api.work into #app and calls api.touch() after each edit.
(function () {
  "use strict";
  var C = window.EDITOR_CONFIG;
  var API = "https://api.github.com/repos/" + C.owner + "/" + C.repo;
  var ITER = 1000000, MIN_PW = 16;
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

  window.EditorCore = function (opt) {
    var token = null, fileSha = null, busy = false;
    var api = { original: null, work: null, extra: null, el: el, touch: touch, status: status, getFile: getFile };

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
      if (e.status === 409 || e.status === 422) return "The " + opt.noun + " changed on GitHub since you opened it. Reload the page and make your edits again.";
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
            .then(function (sha) { return putFile("editor/sealed.json", JSON.stringify(box, null, 2) + "\n", "Editors: new encrypted access key", sha); });
        }).then(function (r) {
          token = null; form.reset(); out.hidden = false; out.className = "msg ok";
          out.textContent = "Saved (commit " + r.commit.sha.slice(0, 7) + "). The site rebuilds in a few minutes; then the password opens both editors."; btn.textContent = "Done";
        }, function (er) { token = null; fail(plain(er)); });
      });
    }

    // ---- editing
    function load() {
      status("", "", []);
      (opt.extra ? opt.extra(api) : Promise.resolve(null)).then(function (x) {
        api.extra = x;
        return getFile(opt.file);
      }).then(function (f) {
        fileSha = f.sha; api.original = opt.clean(JSON.parse(f.text), api.extra); api.work = JSON.parse(JSON.stringify(api.original)); opt.render(api);
      }).catch(function (e) { status("err", "Couldn't load the " + opt.noun, [plain(e)]); });
    }
    function dirty() { return JSON.stringify(api.work) !== JSON.stringify(api.original); }
    function touch() { var n = dirty(); $("bar").hidden = !n; $("count").textContent = n ? "Unsaved changes" : ""; }

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
      try { cleaned = opt.clean(api.work, api.extra); } catch (e) { return status("err", "Check the " + opt.noun, [e.message]); }
      var lines = opt.summary(api.original, cleaned);
      busy = true; $("save").disabled = true; $("save").textContent = "Publishing…";
      status("", "Publishing…", ["Saving to GitHub. Keep this page open."]);
      putFile(opt.file, opt.dump(cleaned), opt.commit + ": " + (lines.slice(0, 3).join(", ") || "update"), fileSha).then(function (r) {
        api.original = cleaned; api.work = JSON.parse(JSON.stringify(cleaned)); fileSha = r.content.sha; opt.render(api);
        status("", "Saved. Now updating the website…", ["GitHub is rebuilding and checking the site. This takes one to three minutes."].concat(lines));
        return follow(r.commit.sha).then(function (run) {
          if (run && run.conclusion === "success") status("ok", "Published", ["The live page shows the change within a minute or two."].concat(lines), [["Open the live page", opt.siteUrl]]);
          else if (run && run.status === "completed") status("err", "Saved, but the website was not updated", ["The site check failed, so the live page still shows the old " + opt.noun + "."], [["See what went wrong", run.html_url]]);
          else status("ok", "Saved", ["The live page updates within a few minutes."], [["Open the live page", opt.siteUrl]]);
        }, function () { status("ok", "Saved", ["The live page updates within a few minutes."], [["Open the live page", opt.siteUrl]]); });
      }).catch(function (e) { status("err", "Not published", [plain(e), "Your edits are still here."]); })
        .then(function () { busy = false; $("save").disabled = false; $("save").textContent = "Save and publish"; });
    }

    $("save").addEventListener("click", save);
    $("discard").addEventListener("click", function () { api.work = JSON.parse(JSON.stringify(api.original)); opt.render(api); });
    $("signout").addEventListener("click", function () { token = null; location.reload(); });
    window.addEventListener("beforeunload", function (e) { if (api.work && dirty() && !busy) { e.preventDefault(); e.returnValue = ""; } });

    if (!window.crypto || !crypto.subtle) { $("login-msg").hidden = false; $("login-msg").textContent = "This browser can't run the editor. Use an up-to-date Chrome, Safari or Firefox."; }
    else if (location.hash === "#setup") showSetup();
    else fetch("sealed.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }, function () { return null; }).then(showLogin);
    return api;
  };
})();
