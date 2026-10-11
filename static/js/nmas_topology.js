/* Topology's map in the browser (C661; the operator, 2026-10-11): "User should be able to move
   devices and save their topology", "drag the display to move around the topology and use the
   mouse wheel to zoom", and the decisions that followed:
   - drag empty space (or a link) to pan; the wheel, a trackpad pinch or two fingers zoom at the
     pointer; the −, 100% and + buttons zoom about the middle (their links are the no-script
     fallback, the server's zoom steps);
   - drag a device to move it, where the pointer is fine and the screen wide (the phone pans and
     zooms only); Alt and an arrow key move a focused device. On the drop, every device's place is
     written into the move form (#topo-move) and posted: the network's layout, for everyone,
     recorded; the device is busy on itself until the answer redraws the map;
   - Labels Auto: the labels hide while the map is zoomed out (svg.topo-far);
   - the view (pan and zoom) is kept, per network, across the region's redraws.
   Strict CSP: no inline handler, attributes only. */
(function (root) {
  'use strict';

  /* The zoom's range, relative to the whole map fitted (1 = 100%). */
  var MIN_SCALE = 0.25, MAX_SCALE = 6;
  /* A press that moves less than this many screen pixels is a click. */
  var CLICK_SLOP = 4;
  /* The fewest screen pixels a map unit is first drawn at: a name (12.5 units) stays about 7.5
     pixels, readable. */
  var READABLE = 0.6;

  /* PURE: a view box zoomed by *factor* about the point (px, py) in map units, its scale kept
     within the range relative to the whole map's width. */
  function zoomAt(view, factor, px, py, width) {
    var w = view.w / factor;
    var scale = width / w;
    if (scale < MIN_SCALE) w = width / MIN_SCALE;
    if (scale > MAX_SCALE) w = width / MAX_SCALE;
    var f = view.w / w;
    return {x: px - (px - view.x) / f, y: py - (py - view.y) / f, w: w, h: view.h / f};
  }

  /* PURE: the view a zoom step asks for (the server's steps, 50 to 200), the whole map at 100. */
  function initial(width, height, z) {
    var s = (z || 100) / 100;
    return {x: 0, y: 0, w: width / s, h: height / s};
  }

  /* PURE: every device's place, from [{name, x, y}], as the JSON the server reads. */
  function layoutJson(nodes) {
    var out = {};
    nodes.forEach(function (n) { out[n.name] = [Math.round(n.x), Math.round(n.y)]; });
    return JSON.stringify(out);
  }

  /* PURE: a straight line between two places, as a path. */
  function straight(a, b) {
    return 'M' + Math.round(a[0]) + ' ' + Math.round(a[1]) + 'L' + Math.round(b[0]) + ' ' +
      Math.round(b[1]);
  }

  var views = {};      // the view kept per network, across redraws

  function svgOf(box) { return box.querySelector('svg.topo-map'); }
  function size(svg) {
    return {w: parseFloat(svg.getAttribute('data-width')), h: parseFloat(svg.getAttribute('data-height'))};
  }
  function readView(svg) {
    var v = svg.getAttribute('viewBox').split(/\s+/).map(parseFloat);
    return {x: v[0], y: v[1], w: v[2], h: v[3]};
  }

  function setView(box, view) {
    var svg = svgOf(box);
    if (!svg) return;
    svg.setAttribute('viewBox', [view.x, view.y, view.w, view.h].map(function (n) {
      return Math.round(n * 10) / 10;
    }).join(' '));
    views[box.getAttribute('data-topo-view')] = view;
    var scale = size(svg).w / view.w;
    svg.classList.toggle('topo-far', scale < 0.95);
    var region = box.closest('#topo');
    var fit = region && region.querySelector('[data-topo-zoom="fit"]');
    if (fit) fit.textContent = Math.round(scale * 100) + '%';
  }

  function toMap(svg, clientX, clientY) {
    var pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }

  /* A device is moved by a mouse or a pen on a wide screen; a touch pans (the phone pans and
     zooms only). Judged by the pointer the press came from, not the device's media query (a
     touchscreen laptop has both; a headless browser reports neither). */
  function canMove(pointerType) {
    return pointerType !== 'touch' &&
      !!(root.matchMedia && root.matchMedia('(min-width: 701px)').matches);
  }

  /* ------------------------------------------------------------------ a device moved */

  function placeOf(g) {
    return [parseFloat(g.getAttribute('data-x')) + parseFloat(g.getAttribute('data-dx') || 0),
            parseFloat(g.getAttribute('data-y')) + parseFloat(g.getAttribute('data-dy') || 0)];
  }

  function shift(svg, g, dx, dy) {
    var s = size(svg), x0 = parseFloat(g.getAttribute('data-x')), y0 = parseFloat(g.getAttribute('data-y'));
    // Kept on the map's frame, with a margin, so a device is never dragged out of reach.
    dx = Math.min(Math.max(x0 + dx, 20), Math.max(s.w, x0 + dx) + 400) - x0;
    dy = Math.min(Math.max(y0 + dy, 20), Math.max(s.h, y0 + dy) + 400) - y0;
    g.setAttribute('data-dx', String(Math.round(dx)));
    g.setAttribute('data-dy', String(Math.round(dy)));
    g.setAttribute('transform', 'translate(' + Math.round(dx) + ' ' + Math.round(dy) + ')');
    var name = g.getAttribute('data-node'), byName = {};
    svg.querySelectorAll('[data-node]').forEach(function (n) { byName[n.getAttribute('data-node')] = n; });
    svg.querySelectorAll('path[data-a][data-b]').forEach(function (line) {
      var a = line.getAttribute('data-a'), b = line.getAttribute('data-b');
      if ((a === name || b === name) && byName[a] && byName[b]) {
        line.setAttribute('d', straight(placeOf(byName[a]), placeOf(byName[b])));
      }
    });
  }

  function save(svg, g) {
    var form = root.document.getElementById('topo-move');
    if (!form) return;
    form.elements.moved.value = g.getAttribute('data-node');
    form.elements.positions.value = layoutJson(Array.prototype.map.call(
      svg.querySelectorAll('[data-node]'), function (n) {
        var p = placeOf(n);
        return {name: n.getAttribute('data-node'), x: p[0], y: p[1]};
      }));
    g.classList.add('topo-saving');      // busy on itself until the answer redraws the map
    if (root.htmx) root.htmx.trigger(form, 'submit');
    else form.submit();
  }

  /* ------------------------------------------------------------------ the pointer */

  var press = null;          // one pointer: a pan or a device's drag
  var touches = {};          // the pointers down on the map, for a pinch
  var pinch = null;
  var swallowClick = false;

  function onDown(evt) {
    var box = evt.target.closest && evt.target.closest('[data-topo-view]');
    if (!box) return;
    var svg = svgOf(box);
    if (!svg) return;
    touches[evt.pointerId] = {x: evt.clientX, y: evt.clientY};
    var ids = Object.keys(touches);
    if (ids.length === 2) {
      // Two fingers: a pinch replaces whatever the first began.
      var a = touches[ids[0]], b = touches[ids[1]];
      pinch = {box: box, svg: svg, d: Math.hypot(a.x - b.x, a.y - b.y) || 1,
               mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2};
      press = null;
      return;
    }
    if (evt.button !== undefined && evt.button !== 0) return;
    var g = evt.target.closest('[data-node]');
    press = {box: box, svg: svg, id: evt.pointerId, x: evt.clientX, y: evt.clientY,
             view: readView(svg), node: (g && canMove(evt.pointerType)) ? g : null,
             moved: false};
    if (press.node) {
      var p = toMap(svg, evt.clientX, evt.clientY);
      press.start = [p.x, p.y];
      press.d0 = [parseFloat(press.node.getAttribute('data-dx') || 0),
                  parseFloat(press.node.getAttribute('data-dy') || 0)];
    }
    if (box.setPointerCapture) box.setPointerCapture(evt.pointerId);
  }

  function onMove(evt) {
    if (touches[evt.pointerId]) touches[evt.pointerId] = {x: evt.clientX, y: evt.clientY};
    if (pinch) {
      var ids = Object.keys(touches);
      if (ids.length < 2) return;
      var a = touches[ids[0]], b = touches[ids[1]];
      var d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      var view = readView(pinch.svg);
      var before = toMap(pinch.svg, pinch.mx, pinch.my);
      view = zoomAt(view, d / pinch.d, before.x, before.y, size(pinch.svg).w);
      setView(pinch.box, view);
      var now = toMap(pinch.svg, mx, my), then = toMap(pinch.svg, pinch.mx, pinch.my);
      view.x -= now.x - then.x;
      view.y -= now.y - then.y;
      setView(pinch.box, view);
      pinch.d = d;
      pinch.mx = mx;
      pinch.my = my;
      swallowClick = true;
      return;
    }
    if (!press || evt.pointerId !== press.id) return;
    if (!press.moved && Math.hypot(evt.clientX - press.x, evt.clientY - press.y) < CLICK_SLOP) return;
    if (!press.moved) {
      press.moved = true;
      press.box.classList.add('topo-panning');
      if (press.node) press.svg.classList.add('topo-moving');
    }
    if (press.node) {
      var p = toMap(press.svg, evt.clientX, evt.clientY);
      shift(press.svg, press.node, press.d0[0] + p.x - press.start[0], press.d0[1] + p.y - press.start[1]);
      return;
    }
    // A pan: the view moves by the pointer's travel, in map units at the view's own scale.
    var ctm = press.svg.getScreenCTM();
    var k = ctm ? ctm.a : 1;
    setView(press.box, {x: press.view.x - (evt.clientX - press.x) / k,
                        y: press.view.y - (evt.clientY - press.y) / k,
                        w: press.view.w, h: press.view.h});
  }

  function onUp(evt) {
    delete touches[evt.pointerId];
    if (pinch && Object.keys(touches).length < 2) pinch = null;
    if (!press || evt.pointerId !== press.id) return;
    press.box.classList.remove('topo-panning');
    if (press.moved) {
      swallowClick = true;
      if (press.node) save(press.svg, press.node);
    }
    press = null;
  }

  /* A press that panned, pinched or moved a device is not a click on what it began over. */
  function onClick(evt) {
    if (!swallowClick) return;
    swallowClick = false;
    if (evt.target.closest && evt.target.closest('[data-topo-view]')) {
      evt.preventDefault();
      evt.stopPropagation();
    }
  }

  function onWheel(evt) {
    var box = evt.target.closest && evt.target.closest('[data-topo-view]');
    if (!box) return;
    var svg = svgOf(box);
    if (!svg) return;
    evt.preventDefault();
    var p = toMap(svg, evt.clientX, evt.clientY);
    // A trackpad pinch arrives as a wheel with ctrlKey and small steps; a wheel notch as ~100.
    var factor = Math.exp(-evt.deltaY * (evt.ctrlKey ? 0.01 : 0.0015));
    setView(box, zoomAt(readView(svg), factor, p.x, p.y, size(svg).w));
  }

  /* The −, 100% and + buttons: zoom about the middle, or fit; their links are the fallback. */
  function onZoomButton(evt) {
    var btn = evt.target.closest && evt.target.closest('[data-topo-zoom]');
    if (!btn) return;
    var region = btn.closest('#topo');
    var box = region && region.querySelector('[data-topo-view]');
    var svg = box && svgOf(box);
    if (!svg) return;
    evt.preventDefault();
    evt.stopPropagation();
    var s = size(svg), view = readView(svg), how = btn.getAttribute('data-topo-zoom');
    if (how === 'fit') view = initial(s.w, s.h, 100);
    else view = zoomAt(view, how === 'in' ? 1.4 : 1 / 1.4, view.x + view.w / 2, view.y + view.h / 2, s.w);
    setView(box, view);
  }

  /* Alt and an arrow key move a focused device 20 units (60 with Shift); saved on each step. */
  function onKey(evt) {
    if (!evt.altKey || !canMove('keyboard')) return;
    var d = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[evt.key];
    var g = d && evt.target.closest && evt.target.closest('[data-node]');
    var svg = g && g.closest('svg.topo-map');
    if (!svg) return;
    evt.preventDefault();
    var step = evt.shiftKey ? 60 : 20;
    shift(svg, g, parseFloat(g.getAttribute('data-dx') || 0) + d[0] * step,
          parseFloat(g.getAttribute('data-dy') || 0) + d[1] * step);
    save(svg, g);
  }

  /* PURE: the first view of a map *s* in a box *bw* by *bh* pixels, at the zoom step asked for:
     the whole map, unless that draws it smaller than *floor* pixels a map unit (a wide map in a
     phone's tall box), when it starts at the floor, centred, and the person pans to the rest. */
  function firstView(s, bw, bh, z, floor) {
    var v = initial(s.w, s.h, z);
    if (!bw || !bh || Math.min(bw / v.w, bh / v.h) >= floor) return v;
    var w = bw / floor, h = bh / floor;
    return {x: v.x + (v.w - w) / 2, y: v.y + (v.h - h) / 2, w: w, h: h};
  }

  /* Each time the map is drawn: the network's kept view, else the first view. */
  function ready() {
    root.document.querySelectorAll('[data-topo-view]').forEach(function (box) {
      var svg = svgOf(box);
      if (!svg) return;
      var s = size(svg), kept = views[box.getAttribute('data-topo-view')];
      setView(box, kept || firstView(s, box.clientWidth, box.clientHeight,
                                     parseFloat(svg.getAttribute('data-z')) || 100, READABLE));
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('pointerdown', onDown);
    root.document.addEventListener('pointermove', onMove);
    root.document.addEventListener('pointerup', onUp);
    root.document.addEventListener('pointercancel', onUp);
    root.document.addEventListener('click', onClick, true);
    root.document.addEventListener('click', onZoomButton, true);
    root.document.addEventListener('wheel', onWheel, {passive: false});
    root.document.addEventListener('keydown', onKey);
    root.document.addEventListener('DOMContentLoaded', ready);
    root.document.addEventListener('htmx:afterSwap', ready);
  }
  root.NMAS_TOPOLOGY = {zoomAt: zoomAt, initial: initial, firstView: firstView,
                        layoutJson: layoutJson, straight: straight};
}(typeof window !== 'undefined' ? window : this));
