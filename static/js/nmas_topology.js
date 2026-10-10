/* Topology's Arrange (C655; P.11 step 3; the operator, 2026-10-10: "topology needs to be
   re-arrangable by the user (drag and drop)"). While the map is arranging
   (svg.topo-arranging), a device or segment ([data-node]) is dragged with the pointer, or moved
   with the arrow keys when focused; each line joined to it is redrawn straight as it moves, and
   every node's place is written into the Save form's hidden field (#topo-positions). Saving
   posts that field; the server redraws the map from the saved layout, its labels placed again.
   Nothing is saved until Save is pressed. Strict CSP: no inline handler, attributes only. */
(function (root) {
  'use strict';

  /* PURE: a place kept inside the map's frame, with a margin. */
  function clamp(x, y, width, height) {
    var m = 20;
    return [Math.min(Math.max(x, m), width - m), Math.min(Math.max(y, m), height - m)];
  }

  /* PURE: a straight line between two places, as a path. */
  function straight(a, b) {
    return 'M' + Math.round(a[0]) + ' ' + Math.round(a[1]) + 'L' + Math.round(b[0]) + ' ' +
      Math.round(b[1]);
  }

  /* PURE: every node's place, from [{name, x, y}], as the JSON the server reads. */
  function layoutJson(nodes) {
    var out = {};
    nodes.forEach(function (n) { out[n.name] = [Math.round(n.x), Math.round(n.y)]; });
    return JSON.stringify(out);
  }

  function place(el) {
    return [parseFloat(el.getAttribute('data-x')), parseFloat(el.getAttribute('data-y'))];
  }

  function nodesOf(svg) {
    return Array.prototype.slice.call(svg.querySelectorAll('[data-node]'));
  }

  function record(svg, edited) {
    var field = root.document.getElementById('topo-positions');
    if (!field) return;
    // A place moved and not saved is a person's work: a live redraw is held until it is saved
    // or cancelled (C459's rule, `data-editing`), never wiping the arrangement.
    if (edited && field.form) field.form.setAttribute('data-editing', 'true');
    field.value = layoutJson(nodesOf(svg).map(function (el) {
      var p = place(el);
      return {name: el.getAttribute('data-node'), x: p[0], y: p[1]};
    }));
  }

  function move(svg, el, x, y) {
    var w = parseFloat(svg.getAttribute('data-width')), h = parseFloat(svg.getAttribute('data-height'));
    var p = clamp(x, y, w, h);
    el.setAttribute('data-x', String(Math.round(p[0])));
    el.setAttribute('data-y', String(Math.round(p[1])));
    el.setAttribute('transform', 'translate(' + Math.round(p[0]) + ' ' + Math.round(p[1]) + ')');
    var name = el.getAttribute('data-node');
    var byName = {};
    nodesOf(svg).forEach(function (n) { byName[n.getAttribute('data-node')] = n; });
    svg.querySelectorAll('path[data-a][data-b]').forEach(function (line) {
      var a = line.getAttribute('data-a'), b = line.getAttribute('data-b');
      if (a !== name && b !== name) return;
      if (!byName[a] || !byName[b]) return;
      line.setAttribute('d', straight(place(byName[a]), place(byName[b])));
    });
  }

  function toSvg(svg, evt) {
    var pt = svg.createSVGPoint();
    pt.x = evt.clientX;
    pt.y = evt.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }

  var drag = null;

  function arranging(target) {
    var el = target && target.closest ? target.closest('[data-node]') : null;
    var svg = el ? el.closest('svg.topo-arranging') : null;
    return svg ? {svg: svg, el: el} : null;
  }

  function onDown(evt) {
    var hit = arranging(evt.target);
    if (!hit) return;
    evt.preventDefault();
    var p = toSvg(hit.svg, evt), at = place(hit.el);
    drag = {svg: hit.svg, el: hit.el, dx: at[0] - p.x, dy: at[1] - p.y, id: evt.pointerId};
    hit.el.classList.add('topo-dragging');
    if (hit.el.setPointerCapture) hit.el.setPointerCapture(evt.pointerId);
  }

  function onMove(evt) {
    if (!drag || evt.pointerId !== drag.id) return;
    var p = toSvg(drag.svg, evt);
    move(drag.svg, drag.el, p.x + drag.dx, p.y + drag.dy);
  }

  function onUp(evt) {
    if (!drag || evt.pointerId !== drag.id) return;
    drag.el.classList.remove('topo-dragging');
    record(drag.svg, true);
    drag = null;
  }

  /* The arrow keys move a focused node 10 units (50 with Shift). */
  function onKey(evt) {
    var hit = arranging(evt.target);
    if (!hit) return;
    var step = evt.shiftKey ? 50 : 10;
    var d = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step],
             ArrowDown: [0, step]}[evt.key];
    if (!d) return;
    evt.preventDefault();
    var at = place(hit.el);
    move(hit.svg, hit.el, at[0] + d[0], at[1] + d[1]);
    record(hit.svg, true);
  }

  /* Each time the map is drawn arranging, the field starts as the places drawn. */
  function ready() {
    var svg = root.document.querySelector('svg.topo-arranging');
    if (svg) record(svg);
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('pointerdown', onDown);
    root.document.addEventListener('pointermove', onMove);
    root.document.addEventListener('pointerup', onUp);
    root.document.addEventListener('pointercancel', onUp);
    root.document.addEventListener('keydown', onKey);
    root.document.addEventListener('DOMContentLoaded', ready);
    root.document.addEventListener('htmx:afterSwap', ready);
  }
  root.NMAS_TOPOLOGY = {clamp: clamp, straight: straight, layoutJson: layoutJson};
}(typeof window !== 'undefined' ? window : this));
