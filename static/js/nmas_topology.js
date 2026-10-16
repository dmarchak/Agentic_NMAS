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
   - Snap to grid (board E, C691; the map carries data-snap while it is on): a dragged device's
     landing point is outlined, and on the drop it lands on the nearest grid point;
   - Labels Auto: the labels hide while the map is zoomed out (svg.topo-far);
   - the view (pan and zoom) is kept, per network, across the region's redraws;
   - while a pointer is down on the map, nothing redraws it (C882, static/js/nmas_drag.js): an
     announcement or a save's answer that arrives mid-drag is applied after the drop. A drop that
     would land more than one grid step (FAR) from where the pointer let go is refused, put back,
     and said above the map; nothing is saved.
   Strict CSP: no inline handler, attributes only. */
(function (root) {
  'use strict';

  /* The zoom's range, relative to the whole map fitted (1 = 100%). */
  var MIN_SCALE = 0.25, MAX_SCALE = 6;
  /* A press that moves less than this many screen pixels is a click. */
  var CLICK_SLOP = 4;
  /* On a phone's narrow box (under 700 px), the fewest screen pixels a map unit is first drawn
     at: a name (12.5 units) stays about 7.5 pixels, readable. A wider box opens on the whole map
     (the board's 100%). */
  var READABLE = 0.6;
  /* C882: the most a drop may land from where the pointer let go, in map units, on either axis:
     one grid step (modules/topology_page.GRID). A correct drag lands exactly where the pointer
     says (to a unit's rounding); in the walk, consecutive saved places moved 120 to 400 units on
     an axis, and the measured cause some 360 (a redraw under the pointer). One step, so a
     pointer between two dots may take either. */
  var FAR = 40;

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

  /* PURE: how far a view is zoomed, 1 being the whole map *s* fitted in a box *bw* by *bh*
     pixels: the pixels a map unit gets in the view over those it gets at the fit, each the
     smaller of across and down (the box keeps the map's proportions). Measured on the host's map
     (C661's walk): a map taller than its box fits by its height, and a ratio of widths alone
     called the whole map 93%, hiding Labels Auto at the first view. */
  function scaleOf(s, view, bw, bh) {
    if (!bw || !bh) return s.w / view.w;
    return Math.min(bw / view.w, bh / view.h) / Math.min(bw / s.w, bh / s.h);
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
    var scale = scaleOf(size(svg), view, box.clientWidth, box.clientHeight);
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

  /* PURE: snap to grid (board E, C691): a place's nearest grid point, *step* map units apart,
     never nearer the map's edge than one step. */
  function snapTo(v, step) {
    return Math.max(step, Math.round(v / step) * step);
  }

  /* The grid's step while Snap to grid is on (the map carries it), else 0. */
  function gridOf(svg) {
    return parseFloat(svg.getAttribute('data-snap') || 0) || 0;
  }

  /* While a device is dragged with the grid on: the outline where it will land. */
  function markLanding(svg, g) {
    var mark = svg.querySelector('.topo-snapmark'), step = gridOf(svg);
    if (!mark || !step) return;
    var p = placeOf(g);
    mark.setAttribute('cx', String(snapTo(p[0], step)));
    mark.setAttribute('cy', String(snapTo(p[1], step)));
    mark.setAttribute('visibility', 'visible');
  }

  /* On the drop with the grid on: the device lands on the nearest grid point. */
  function unmark(svg) {
    var mark = svg.querySelector('.topo-snapmark');
    if (mark) mark.setAttribute('visibility', 'hidden');
  }

  function land(svg, g) {
    var step = gridOf(svg);
    unmark(svg);
    if (!step) return;
    var p = placeOf(g);
    shift(svg, g, snapTo(p[0], step) - parseFloat(g.getAttribute('data-x')),
          snapTo(p[1], step) - parseFloat(g.getAttribute('data-y')));
  }

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

  /* C882: where the pointer let go says where the device lands: its map position (read now, on
     the map that is on the page) plus where on the device it was grabbed, snapped with the grid
     on. '' when the device is there; else why it is refused, naming both places. */
  function judgeDrop(p, clientX, clientY) {
    var name = p.node.getAttribute('data-node');
    var there = root.NMAS_DRAG ? root.NMAS_DRAG.stillThere(p.hold) : p.box.isConnected;
    if (!there || !p.svg.isConnected || !p.node.isConnected) {
      return name + ' was drawn again while it was dragged, so where it would land cannot be ' +
        'trusted; nothing was saved. Drag it again';
    }
    var at = toMap(p.svg, clientX, clientY), step = gridOf(p.svg);
    var want = [at.x + p.grab[0], at.y + p.grab[1]].map(function (v) {
      return step ? snapTo(v, step) : Math.max(v, 20);
    });
    var landed = placeOf(p.node);
    var off = root.NMAS_DRAG ? root.NMAS_DRAG.far(landed, want, FAR) : null;
    if (!off) return '';
    return name + ' would have landed at (' + Math.round(landed[0]) + ', ' +
      Math.round(landed[1]) + '), but the pointer let go over (' + Math.round(want[0]) + ', ' +
      Math.round(want[1]) + '): ' + off.by + ' map units apart, more than one grid step (' +
      off.limit + '); nothing was saved. Drag it again';
  }

  /* A refused drop, said in the slot above the map (a refusal drawn inside the region would be
     wiped by its next redraw); the next save's answer replaces it. */
  function sayRefused(words) {
    var slot = root.document.getElementById('topo-result');
    if (!slot) return;
    var doc = root.document, ns = 'http://www.w3.org/2000/svg';
    var div = doc.createElement('div');
    div.className = 'notice notice-danger set-result';
    div.setAttribute('role', 'alert');
    var ico = doc.createElementNS(ns, 'svg');
    [['class', 'ico'], ['width', '16'], ['height', '16'], ['viewBox', '0 0 24 24'],
     ['fill', 'none'], ['stroke', 'currentColor'], ['stroke-width', '2'],
     ['stroke-linecap', 'round'], ['stroke-linejoin', 'round'], ['aria-hidden', 'true']]
      .forEach(function (a) { ico.setAttribute(a[0], a[1]); });
    ['M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
     'M12 9v4', 'M12 17h.01'].forEach(function (d) {
      var path = doc.createElementNS(ns, 'path');
      path.setAttribute('d', d);
      ico.appendChild(path);
    });
    var para = doc.createElement('p'), strong = doc.createElement('strong');
    strong.textContent = 'Not moved:';
    para.appendChild(strong);
    para.appendChild(doc.createTextNode(' ' + words + '.'));
    div.appendChild(ico);
    div.appendChild(para);
    slot.textContent = '';
    slot.appendChild(div);
  }

  /* ------------------------------------------------------------------ the pointer */

  var press = null;          // one pointer: a pan or a device's drag
  var touches = {};          // the pointers down on the map, for a pinch
  var pinch = null;
  var swallowClick = false;

  /* C882: the map is held (nothing redraws it) from a press until it ends; *answered*: the
     drop's own save redraws it, so nothing set aside meanwhile is asked for again. */
  function holdMap(box, pointerId) {
    return root.NMAS_DRAG ? root.NMAS_DRAG.hold(box, pointerId) : null;
  }
  function letGo(h, answered) {
    if (h && root.NMAS_DRAG) root.NMAS_DRAG.release(h, answered);
  }

  function onDown(evt) {
    var box = evt.target.closest && evt.target.closest('[data-topo-view]');
    if (!box) return;
    var svg = svgOf(box);
    if (!svg) return;
    touches[evt.pointerId] = {x: evt.clientX, y: evt.clientY};
    var ids = Object.keys(touches);
    if (ids.length === 2) {
      // Two fingers: a pinch replaces whatever the first began, and keeps its hold.
      var a = touches[ids[0]], b = touches[ids[1]];
      pinch = {box: box, svg: svg, d: Math.hypot(a.x - b.x, a.y - b.y) || 1,
               mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2,
               hold: press ? press.hold : holdMap(box, evt.pointerId)};
      press = null;
      return;
    }
    if (evt.button !== undefined && evt.button !== 0) return;
    if (press) letGo(press.hold, false);
    var g = evt.target.closest('[data-node]');
    press = {box: box, svg: svg, id: evt.pointerId, x: evt.clientX, y: evt.clientY,
             view: readView(svg), node: (g && canMove(evt.pointerType)) ? g : null,
             moved: false, hold: holdMap(box, evt.pointerId)};
    if (press.node) {
      var p = toMap(svg, evt.clientX, evt.clientY), at = placeOf(press.node);
      press.start = [p.x, p.y];
      press.grab = [at[0] - p.x, at[1] - p.y];    // where on the device it was taken
      press.d0 = [parseFloat(press.node.getAttribute('data-dx') || 0),
                  parseFloat(press.node.getAttribute('data-dy') || 0)];
    }
    if (box.setPointerCapture) box.setPointerCapture(evt.pointerId);
  }

  /* The dragged device follows the pointer, in map units on the map as it is now. */
  function follow(p, clientX, clientY) {
    var at = toMap(p.svg, clientX, clientY);
    shift(p.svg, p.node, p.d0[0] + at.x - p.start[0], p.d0[1] + at.y - p.start[1]);
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
      follow(press, evt.clientX, evt.clientY);
      markLanding(press.svg, press.node);
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
    if (pinch && Object.keys(touches).length < 2) {
      letGo(pinch.hold, false);
      pinch = null;
    }
    if (!press || evt.pointerId !== press.id) return;
    var p = press;
    press = null;
    p.box.classList.remove('topo-panning');
    if (!p.moved || !p.node) {
      if (p.moved) swallowClick = true;
      letGo(p.hold, false);
      return;
    }
    swallowClick = true;
    if (evt.type === 'pointercancel') {
      // Not a drop: the device goes back and nothing is saved.
      unmark(p.svg);
      shift(p.svg, p.node, p.d0[0], p.d0[1]);
      p.svg.classList.remove('topo-moving');
      letGo(p.hold, false);
      return;
    }
    follow(p, evt.clientX, evt.clientY);
    land(p.svg, p.node);
    var refused = judgeDrop(p, evt.clientX, evt.clientY);
    if (refused) {
      shift(p.svg, p.node, p.d0[0], p.d0[1]);    // back where it was
      p.svg.classList.remove('topo-moving');
      sayRefused(refused);
      letGo(p.hold, false);
      return;
    }
    letGo(p.hold, true);
    save(p.svg, p.node);
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

  /* C668: a click on the map's empty space, or Escape, closes the selected link's card (its close
     link, .topo-cardx, is pressed, so the region redraws without the selection). A click on a
     device, a link or a card is theirs. */
  function closeSelected() {
    var x = root.document.querySelector('#topo .topo-cardx');
    if (x) x.click();
    return !!x;
  }

  function onClickOff(evt) {
    if (evt.defaultPrevented || !evt.target.closest) return;
    if (!evt.target.closest('[data-topo-view]')) return;
    if (evt.target.closest('[data-node], .topo-l, .topo-card')) return;
    closeSelected();
  }

  function onEscape(evt) {
    if (evt.key === 'Escape' && closeSelected()) evt.preventDefault();
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

  /* Alt and an arrow key move a focused device 20 units (60 with Shift), or with the grid on one
     grid point (three with Shift), landing on the grid; saved on each step. */
  function onKey(evt) {
    if (!evt.altKey || !canMove('keyboard')) return;
    var d = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[evt.key];
    var g = d && evt.target.closest && evt.target.closest('[data-node]');
    var svg = g && g.closest('svg.topo-map');
    if (!svg) return;
    evt.preventDefault();
    var grid = gridOf(svg);
    var step = (grid || 20) * (evt.shiftKey ? 3 : 1);
    shift(svg, g, parseFloat(g.getAttribute('data-dx') || 0) + d[0] * step,
          parseFloat(g.getAttribute('data-dy') || 0) + d[1] * step);
    land(svg, g);
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
                                     parseFloat(svg.getAttribute('data-z')) || 100,
                                     box.clientWidth < 700 ? READABLE : 0));
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('pointerdown', onDown);
    root.document.addEventListener('pointermove', onMove);
    root.document.addEventListener('pointerup', onUp);
    root.document.addEventListener('pointercancel', onUp);
    root.document.addEventListener('click', onClick, true);
    root.document.addEventListener('click', onZoomButton, true);
    root.document.addEventListener('click', onClickOff);
    root.document.addEventListener('keydown', onEscape);
    root.document.addEventListener('wheel', onWheel, {passive: false});
    root.document.addEventListener('keydown', onKey);
    root.document.addEventListener('DOMContentLoaded', ready);
    root.document.addEventListener('htmx:afterSwap', ready);
  }
  root.NMAS_TOPOLOGY = {zoomAt: zoomAt, initial: initial, firstView: firstView, scaleOf: scaleOf,
                        layoutJson: layoutJson, straight: straight, snapTo: snapTo, FAR: FAR};
}(typeof window !== 'undefined' ? window : this));
