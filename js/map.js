// Home-page map. Without script the map is a plain picture. With script, picking a suburb (from the list or by tapping
// the map) swaps the picture for the same SVG inline, zooms to the suburb, swaps the 1 km hexagons for the 420 m ones
// and lifts the suburb's hexagons out of the map as columns. "Whole city" zooms back out. The SVG is fetched only when
// someone first uses the picker or taps the map; the 420 m data (map/region.json) only on the first zoom.
(function () {
  var sel = document.getElementById('map-area'), fig = document.getElementById('map'), info = document.getElementById('map-info'),
    out = document.getElementById('map-out');
  if (!sel || !fig || !info || !window.fetch || !window.DOMParser) return;
  var NS = 'http://www.w3.org/2000/svg', SLICES = 8, svg = null, loading = null, region = null, full = null, view = null, anim = 0, city = null, goal = null,
    still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function load() {
    if (loading) return loading;
    var img = fig.querySelector('img'), base = img.getAttribute('src').replace(/[^/]*$/, '');
    var map = fetch(img.getAttribute('src')).then(function (r) { return r.text(); }).then(function (t) {
      var doc = new DOMParser().parseFromString(t, 'image/svg+xml');
      svg = document.importNode(doc.documentElement, true);
      svg.removeAttribute('width');
      svg.removeAttribute('height');
      svg.setAttribute('class', 'map-svg');
      svg.setAttribute('aria-label', img.getAttribute('alt'));
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      var fine = document.createElementNS(NS, 'g');
      fine.id = 'fine';
      var hexes = svg.getElementById('hexes');
      hexes.parentNode.insertBefore(fine, hexes.nextSibling);
      fig.replaceChild(svg, img);
      city = union([svg.getElementById('hexes'), svg.getElementById('ring-road')].filter(Boolean));
      full = fit(city, 1.06);
      setView(full);
      window.addEventListener('resize', function () {
        full = fit(city, 1.06);
        cancelAnimationFrame(anim);
        setView(goal ? fit(goal, 1) : full);
      });
      groupLabels();
      svg.addEventListener('click', onTap);
      svg.addEventListener('pointermove', onHover);
      svg.addEventListener('pointerleave', function () { if (hover) hover.setAttribute('class', 'hover-label'); hoverId = null; });
    });
    var reg = fetch(base + 'region.json').then(function (r) { return r.json(); }).then(function (d) { region = d; }, function () {});
    loading = Promise.all([map, reg]);
    return loading;
  }

  // ---- view and zoom
  function setView(v) {
    view = v;
    svg.setAttribute('viewBox', v.map(function (n) { return n.toFixed(2); }).join(' '));
    svg.style.setProperty('--z', (v[2] / full[2]).toFixed(4));
    svg.classList.toggle('zoomed', v[2] < full[2] * 0.95);
  }

  function zoomTo(v, done) {
    cancelAnimationFrame(anim);
    if (still) { setView(v); if (done) done(); return; }
    var from = view.slice(), t0 = performance.now(), T = 700;
    (function step(now) {
      var t = Math.min(1, (now - t0) / T), e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      setView(from.map(function (a, i) { return a + (v[i] - a) * e; }));
      if (t < 1) anim = requestAnimationFrame(step); else if (done) done();
    })(t0);
  }

  // The space the map can use: the whole figure, less the panel when it floats over the map's left side.
  function avail() {
    var r = svg.getBoundingClientRect(), panel = document.querySelector('.map-side'), left = 0;
    if (panel && getComputedStyle(panel).position === 'absolute') left = Math.max(0, panel.getBoundingClientRect().right - r.left + 16);
    return { w: r.width, h: r.height, left: left };
  }

  function fit(b, pad) {  // a viewBox that shows box b (padded) in the free space and fills the figure
    var a = avail(), bw = b.width * pad, bh = b.height * pad;
    var s = Math.min((a.w - a.left) / bw, a.h / bh), vw = a.w / s, vh = a.h / s;
    var cx = b.x + b.width / 2, cy = b.y + b.height / 2;
    return [cx - (a.left + (a.w - a.left) / 2) / s, cy - vh / 2, vw, vh];
  }

  function frame(box) {  // the view for a picked area: room round it, and room above for the raised columns
    var w = Math.max(box.width * 2.2, 60), h = Math.max(box.height * 2.2, 60);
    goal = { x: box.x + box.width / 2 - w / 2, y: box.y + box.height / 2 - h * 0.56, width: w, height: h };
    return fit(goal, 1);
  }

  // ---- the 420 m hexagons
  function hexD(x, y, r) {
    var d = '';
    for (var k = 0; k < 6; k++) {
      var t = Math.PI / 180 * (30 + 60 * k);
      d += (k ? 'L' : 'M') + (x + r * Math.cos(t)).toFixed(1) + ',' + (y + r * Math.sin(t)).toFixed(1);
    }
    return d + 'Z';
  }

  function fineGroup(id) {
    var g = svg.getElementById('fine-' + id);
    if (g || !region || !region.areas[id]) return g;
    g = document.createElementNS(NS, 'g');
    g.id = 'fine-' + id;
    region.areas[id].forEach(function (c) {
      var p = document.createElementNS(NS, 'path');
      p.setAttribute('d', hexD(c[0], c[1], region.r));
      p.setAttribute('fill', '#' + c[2]);
      g.appendChild(p);
    });
    svg.getElementById('fine').appendChild(g);
    return g;
  }

  function showFine(v) {  // draw the 420 m hexagons of every area that reaches into the view
    if (!region) return false;
    Object.keys(region.areas).forEach(function (id) {
      var b = region.box || (region.box = {}), cs = region.areas[id];
      if (!b[id]) {
        var xs = cs.map(function (c) { return c[0]; }), ys = cs.map(function (c) { return c[1]; });
        b[id] = [Math.min.apply(0, xs), Math.min.apply(0, ys), Math.max.apply(0, xs), Math.max.apply(0, ys)];
      }
      var q = b[id];
      if (q[2] >= v[0] && q[0] <= v[0] + v[2] && q[3] >= v[1] && q[1] <= v[1] + v[3]) fineGroup(id);
    });
    svg.classList.add('fine');
    return true;
  }

  // ---- picking and lifting
  function clear() {
    var old = svg.querySelector('.lift');
    if (old) old.parentNode.removeChild(old);
    [].forEach.call(svg.querySelectorAll('.picked'), function (n) { n.classList.remove('picked'); });
    svg.classList.remove('picking');
  }

  function centreY(d) {
    var n = d.match(/-?\d+(\.\d+)?/g).map(Number), y = 0;
    for (var i = 1; i < n.length; i += 2) y += n[i];
    return y / (n.length / 2);
  }

  function lift(groups, name, share, colour, gradient) {  // groups: the hexagon groups to raise; name: the label over them; colour: an area list's
    var cells = [];
    groups.forEach(function (grp) {
      [].forEach.call(grp.tagName === 'path' ? [grp] : grp.querySelectorAll('path'), function (p) {
        var d = p.getAttribute('d');
        cells.push({ d: d, y: centreY(d) });
      });
    });
    cells.sort(function (a, b) { return a.y - b.y; });
    var top = cells.length ? cells[0].y : 0, span = cells.length > 1 ? cells[cells.length - 1].y - top : 1;
    var n = cells.length > 300 ? 4 : SLICES, height = view[3] * share;
    var g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'lift' + (colour ? ' hl-' + colour : '') + (gradient ? ' gradient' : ''));
    g.style.setProperty('--step', (height / n).toFixed(2) + 'px');
    cells.forEach(function (c) {
      for (var k = 1; k <= n; k++) {
        var s = document.createElementNS(NS, 'path');
        s.setAttribute('d', c.d);
        s.setAttribute('class', 'slice k' + k + (k === n ? ' top' : ''));
        if (gradient) s.style.setProperty('--t', ((c.y - top) / span).toFixed(3));  // 0 in the north (gold) to 1 in the south (purple)
        g.appendChild(s);
      }
    });
    var x0 = Infinity, x1 = -Infinity, y0 = Infinity;
    groups.forEach(function (grp) {
      var b = grp.getBBox();
      x0 = Math.min(x0, b.x); x1 = Math.max(x1, b.x + b.width); y0 = Math.min(y0, b.y);
    });
    var l = document.createElementNS(NS, 'text');
    l.setAttribute('class', 'lift-label');
    l.setAttribute('x', (x0 + x1) / 2);
    l.setAttribute('y', y0 - height - 8 * view[2] / full[2]);
    l.setAttribute('text-anchor', 'middle');
    l.setAttribute('font-size', '13');
    l.setAttribute('font-weight', '700');
    l.setAttribute('font-family', 'Inter, Arial, sans-serif');
    l.setAttribute('stroke-width', '3');
    l.setAttribute('paint-order', 'stroke');
    l.textContent = name;
    g.appendChild(l);
    svg.appendChild(g);
    requestAnimationFrame(function () { requestAnimationFrame(function () { g.classList.add('up'); }); });
  }

  function pickRegion(rid) {  // a whole part of the city: stay at whole-city view and raise every suburb in it
    clear();
    pressed(null);
    svg.classList.remove('fine');
    var opts = [].slice.call(sel.querySelectorAll('option[data-region="' + rid + '"]'));
    var groups = opts.map(function (o) { return svg.getElementById('hex-' + o.value); }).filter(Boolean);
    if (!groups.length) return;
    out.hidden = false;
    svg.classList.add('picking');
    groups.forEach(function (g) { g.classList.add('picked'); });
    var name = sel.options[sel.selectedIndex].getAttribute('data-name');
    info.textContent = '';
    var h = document.createElement('h3'), p = document.createElement('p');
    h.textContent = name;
    p.textContent = groups.length + ' suburbs on the map: ' + opts.map(function (o) { return o.textContent; }).join(', ') + '. Pick one to zoom in.';
    info.appendChild(h);
    info.appendChild(p);
    goal = null;
    zoomTo(full.slice(), function () { lift(groups, name, 0.05); });
  }

  function pickGroup(opt) {  // an area list such as The Parks (an option or a panel button): zoom to fit and raise its suburbs
    clear();
    var ids = opt.getAttribute('data-areas').split(' ');
    pressed(opt.getAttribute('value') || opt.getAttribute('data-list'));
    var city = ids.map(function (i) { return svg.getElementById('hex-' + i); }).filter(Boolean);
    if (!city.length) return;
    out.hidden = false;
    svg.classList.add('picking');
    city.forEach(function (g) { g.classList.add('picked'); });
    var names = ids.map(function (i) { var o = sel.querySelector('option[value="' + i + '"]'); return o ? o.textContent : i; });
    info.textContent = '';
    var h = document.createElement('h3'), p = document.createElement('p');
    h.textContent = opt.getAttribute('data-name');
    p.textContent = (opt.getAttribute('data-aka') ? 'Also called ' + opt.getAttribute('data-aka') + '. ' : '') +
      'Takes in ' + names.join(', ') + '. Pick one to read about it.';
    info.appendChild(h);
    info.appendChild(p);
    var target = frame(union(city));
    zoomTo(target, function () {
      var fine = showFine(target) ? ids.map(fineGroup).filter(Boolean) : [];
      fine.forEach(function (g) { g.classList.add('picked'); });
      lift(fine.length ? fine : city, opt.getAttribute('data-name'), 0.1, opt.getAttribute('data-colour'));
    });
  }

  function stationHexes() {  // the 1 km hexagons that hold a Gautrain station, each with its station's name
    var found = [], seen = {}, paths = [].slice.call(svg.querySelectorAll('#hexes path'));
    [].forEach.call(svg.querySelectorAll('#gautrain-stations > g'), function (n) {
      var b = n.getBBox(), pt = new DOMPoint(b.x + b.width / 2, b.y + b.height / 2), id = n.id.replace(/^station-/, ''),
        t = svg.getElementById('station-label-' + id);
      var hit = null, near = null, best = Infinity;
      for (var i = 0; i < paths.length && !hit; i++) {
        if (paths[i].isPointInFill && paths[i].isPointInFill(pt)) hit = paths[i];
        else {  // a station can sit in the thin gap between two hexagons: take the nearest one, within a hexagon's reach
          var q = paths[i].getBBox(), dist = Math.hypot(q.x + q.width / 2 - pt.x, q.y + q.height / 2 - pt.y);
          if (dist < best && dist <= q.width * 0.75) { best = dist; near = paths[i]; }
        }
      }
      hit = hit || near;
      if (!hit) return;
      var key = hit.getAttribute('d'), nm = t ? t.textContent : n.id;
      if (seen[key]) seen[key].names.push(nm);  // two stations can share a hexagon, such as Rhodesfield and the airport
      else { seen[key] = { path: hit, names: [nm] }; found.push(seen[key]); }
    });
    return found;
  }

  function pickGautrain() {  // stay at whole-city view and raise the hexagon under each station, gold in the north to purple in the south
    clear();
    pressed('gautrain');
    var hexes = stationHexes(), opt = sel.querySelector('option[value="gautrain"]');
    if (!hexes.length) return;
    out.hidden = false;
    svg.classList.add('picking');
    svg.classList.remove('fine');
    hexes.forEach(function (h) { h.path.classList.add('picked'); });
    info.textContent = '';
    var h = document.createElement('h3'), p = document.createElement('p');
    h.textContent = 'Gautrain stations';
    var names = [].concat.apply([], hexes.map(function (x) { return x.names; }));
    p.textContent = names.length + ' stations on the map: ' + names.join(', ') + '. Stations further out are off the edge of the map.';
    info.appendChild(h);
    info.appendChild(p);
    if (opt && opt.getAttribute('data-href')) {
      var a = document.createElement('a'), q = document.createElement('p');
      a.href = opt.getAttribute('data-href');
      a.textContent = 'Read the Gautrain guide';
      q.appendChild(a);
      info.appendChild(q);
    }
    goal = null;
    zoomTo(full.slice(), function () { lift(hexes.map(function (x) { return x.path; }), 'Gautrain stations', 0.12, null, true); });
  }

  function union(groups) {
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    groups.forEach(function (g) {
      var b = g.getBBox();
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height);
    });
    return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
  }

  // ---- names: popular areas at whole-city view, suburbs when zoomed in, any suburb under the pointer
  function groupLabels() {
    var layer = document.createElementNS(NS, 'g');
    layer.id = 'group-labels';
    var done = {};
    [].forEach.call(sel.querySelectorAll('option[value^="group:"]'), function (o) {  // place names only: theme lists stay unlabelled
      var key = o.getAttribute('value') || o.getAttribute('data-list');
      if (done[key]) return;
      done[key] = 1;
      var gs = o.getAttribute('data-areas').split(' ').map(function (i) { return svg.getElementById('hex-' + i); }).filter(Boolean);
      if (!gs.length) return;
      var b = union(gs), t = document.createElementNS(NS, 'text');
      t.setAttribute('x', b.x + b.width / 2);
      t.setAttribute('y', b.y + b.height / 2);
      t.textContent = o.getAttribute('data-name');
      layer.appendChild(t);
    });
    svg.appendChild(layer);
  }

  var hover = null, hoverId = null;
  function onHover(e) {
    var g = e.target.closest && e.target.closest('[id^="hex-"], [id^="fine-"]');
    var id = g ? g.id.replace(/^(hex|fine)-/, '') : null, o = id && sel.querySelector('option[value="' + id + '"]');
    if (!o) { if (hover) hover.setAttribute('class', 'hover-label'); hoverId = null; return; }
    if (id === hoverId) return;
    hoverId = id;
    if (!hover) { hover = document.createElementNS(NS, 'text'); svg.appendChild(hover); }
    var b = g.getBBox();
    hover.setAttribute('x', b.x + b.width / 2);
    hover.setAttribute('y', b.y + b.height / 2);
    hover.textContent = o.textContent;
    hover.setAttribute('class', 'hover-label on');
    svg.appendChild(hover);
  }

  function pick(id) {
    if (id === 'gautrain') return pickGautrain();
    if (id && id.indexOf('all:') === 0) return pickRegion(id.slice(4));
    if (id && id.indexOf('group:') === 0) return pickGroup(sel.options[sel.selectedIndex]);
    pressed(null);
    clear();
    var city = id && svg.getElementById('hex-' + id);
    if (!city) { info.textContent = ''; whole(); return; }
    out.hidden = false;
    svg.classList.add('picking');
    city.classList.add('picked');
    var outline = svg.getElementById(id);
    if (outline) outline.classList.add('picked');
    show(sel.options[sel.selectedIndex]);
    var target = frame(city.getBBox());
    zoomTo(target, function () {
      var grp = showFine(target) && fineGroup(id);
      if (grp) grp.classList.add('picked');
      lift([grp || city], sel.options[sel.selectedIndex].textContent, 0.1);
    });
  }

  function whole() {
    pressed(null);
    if (!svg) return;
    clear();
    svg.classList.remove('fine');
    out.hidden = true;
    goal = null;
    zoomTo(full.slice());
  }

  function show(opt) {
    info.textContent = '';
    if (!opt || !opt.value) return;
    var h = document.createElement('h3'), p = document.createElement('p');
    h.textContent = opt.textContent;
    p.textContent = opt.getAttribute('data-summary') || 'We have not written up this area yet.';
    info.appendChild(h);
    info.appendChild(p);
    if (opt.getAttribute('data-href')) {
      var a = document.createElement('a'), q = document.createElement('p');
      a.href = opt.getAttribute('data-href');
      a.textContent = 'Read the ' + opt.textContent + ' guide';
      q.appendChild(a);
      info.appendChild(q);
    }
  }

  function onTap(e) {
    var g = e.target.closest('[id^="hex-"], [id^="fine-"]');
    var id = g ? g.id.replace(/^(hex|fine)-/, '') : null;
    if (!id) {
      var a = e.target.closest('#areas > *');
      id = a ? a.id : null;
    }
    if (!id || !sel.querySelector('option[value="' + id + '"]')) return;
    sel.value = id;
    pick(id);
  }

  // ---- the panels: each can fold away under its heading; the Area lists panel picks a list
  var lists = [].slice.call(document.querySelectorAll('.map-list'));
  function pressed(key) { lists.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-list') === key)); }); }
  lists.forEach(function (b) {
    b.addEventListener('click', function () {
      var o = sel.querySelector('option[value="' + b.getAttribute('data-list') + '"]');
      sel.value = o ? o.value : '';
      load().then(function () { if (b.getAttribute('data-list') === 'gautrain') pickGautrain(); else pickGroup(b); });
    });
  });
  pressed(null);
  [].forEach.call(document.querySelectorAll('.map-panel'), function (panel) {
    var h = panel.querySelector('h2, h3'), body = panel.querySelector('.map-panel-body');
    if (!h || !body) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('aria-expanded', 'true');
    b.setAttribute('aria-controls', body.id);
    b.textContent = h.textContent;
    h.textContent = '';
    h.appendChild(b);
    b.addEventListener('click', function () {
      var open = b.getAttribute('aria-expanded') !== 'true';
      b.setAttribute('aria-expanded', String(open));
      body.hidden = !open;
    });
  });
  if (!lists.length) { var lp = document.querySelector('.map-panel-lists'); if (lp) lp.hidden = true; }

  sel.addEventListener('focus', load);
  sel.addEventListener('change', function () { load().then(function () { pick(sel.value); }); });
  out.addEventListener('click', function () { sel.value = ''; info.textContent = ''; whole(); sel.focus(); });
  fig.addEventListener('click', function () { if (!svg) load(); });
})();
