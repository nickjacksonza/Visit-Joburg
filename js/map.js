// Home-page map. Without script the map is a plain picture. With script, picking a suburb (from the list or by tapping
// the map) swaps the picture for the same SVG inline, then lifts that suburb's hexagons out of the map as columns and
// shows its summary. The SVG is fetched only when someone first uses the picker or taps the map.
(function () {
  var sel = document.getElementById('map-area'), fig = document.getElementById('map'), info = document.getElementById('map-info');
  if (!sel || !fig || !info || !window.fetch || !window.DOMParser) return;
  var NS = 'http://www.w3.org/2000/svg', LIFT = 40, SLICES = 8, svg = null, loading = null;

  function load() {
    if (loading) return loading;
    var img = fig.querySelector('img');
    loading = fetch(img.getAttribute('src')).then(function (r) { return r.text(); }).then(function (t) {
      var doc = new DOMParser().parseFromString(t, 'image/svg+xml');
      svg = document.importNode(doc.documentElement, true);
      svg.removeAttribute('width');
      svg.removeAttribute('height');
      svg.setAttribute('class', 'map-svg');
      svg.setAttribute('aria-label', img.getAttribute('alt'));
      fig.replaceChild(svg, img);
      svg.addEventListener('click', onTap);
      return svg;
    });
    return loading;
  }

  function centreY(d) {
    var n = d.match(/-?\d+(\.\d+)?/g).map(Number), y = 0;
    for (var i = 1; i < n.length; i += 2) y += n[i];
    return y / (n.length / 2);
  }

  function clear() {
    var old = svg.querySelector('.lift');
    if (old) old.parentNode.removeChild(old);
    [].forEach.call(svg.querySelectorAll('.picked'), function (n) { n.classList.remove('picked'); });
    svg.classList.remove('picking');
  }

  function explode(id) {
    clear();
    var grp = id && svg.getElementById('hex-' + id);
    if (!grp) { info.textContent = ''; return; }
    svg.classList.add('picking');
    grp.classList.add('picked');
    var outline = svg.getElementById(id);
    if (outline) outline.classList.add('picked');
    var cells = [].map.call(grp.querySelectorAll('path'), function (p) {
      var d = p.getAttribute('d');
      return { d: d, y: centreY(d) };
    }).sort(function (a, b) { return a.y - b.y; });
    var lift = document.createElementNS(NS, 'g');
    lift.setAttribute('class', 'lift');
    cells.forEach(function (c) {
      for (var k = 1; k <= SLICES; k++) {
        var s = document.createElementNS(NS, 'path');
        s.setAttribute('d', c.d);
        s.setAttribute('class', 'slice k' + k + (k === SLICES ? ' top' : ''));
        lift.appendChild(s);
      }
    });
    var box = grp.getBBox(), label = svg.getElementById('label-' + id);
    if (label) {
      var l = label.cloneNode(true);
      l.removeAttribute('id');
      l.setAttribute('class', 'lift-label');
      l.setAttribute('x', box.x + box.width / 2);
      l.setAttribute('y', box.y - LIFT - 6);
      lift.appendChild(l);
    }
    svg.appendChild(lift);
    requestAnimationFrame(function () { requestAnimationFrame(function () { lift.classList.add('up'); }); });
    show(sel.options[sel.selectedIndex]);
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
      var a = document.createElement('a');
      a.href = opt.getAttribute('data-href');
      a.textContent = 'Read the ' + opt.textContent + ' guide';
      var q = document.createElement('p');
      q.appendChild(a);
      info.appendChild(q);
    }
  }

  function onTap(e) {
    var g = e.target.closest('[id^="hex-"]');
    var id = g ? g.id.slice(4) : null;
    if (!id) {
      var a = e.target.closest('#areas > *');
      id = a ? a.id : null;
    }
    if (!id || !sel.querySelector('option[value="' + id + '"]')) return;
    sel.value = id;
    explode(id);
  }

  sel.addEventListener('focus', load);
  sel.addEventListener('change', function () { load().then(function () { explode(sel.value); }); });
  fig.addEventListener('click', function (e) { if (!svg) { e.preventDefault(); load(); } });
})();
