/* The preview-then-confirm component: ONE renderer for every preview.
 *
 * Stage 7.1 (NSOT_STAGE7_PLAN.md section 2, pattern 1). The server builds
 * the six parts with one helper (modules/preview_confirm.py) and this draws
 * them, so the payload-to-render check covers one renderer, not six drifting
 * ones. In order:
 *   1 what        what will happen, each target named (and ticked here)
 *   2 what_not    what will NOT happen, with the reason
 *   3 program     per target: what is sent, byte for byte
 *   4 operands    per target: the values the confirm is bound to
 *   5 gates       per target: each gate by name, with its state
 *   6 confirm     who is confirming, or why they may not
 *
 * Every part is drawn, always. A part with nothing to say draws the sentence
 * the server wrote saying so: an empty section and a missing section read
 * the same to a person (the operator, 2026-09-27).
 *
 * PURE: HTML in, HTML out, so the shipped code runs in duktape against a
 * real payload (tests/test_preview_confirm.py). The screen wires the hooks:
 *   selectable: draw a tick per selectable target
 *   onSelect:   the NAME of the function a tick calls
 *   authorise:  the NAME of the function a dangerous line's box calls
 */
(function (root) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  function idFor(name) { return 'pc_sel_' + String(name).replace(/[^a-z0-9]/gi, '_'); }

  var GATE_STATE = {
    pass: ['bg-success', 'pass'],
    fail: ['bg-danger', 'FAIL'],
    not_applicable: ['bg-secondary', 'not applicable'],
    at_apply: ['bg-info text-dark', 'checked at apply'],
    not_reached: ['bg-secondary', 'not reached']
  };

  var PARTS = ['what', 'what_not', 'program', 'operands', 'gates', 'confirm'];

  var TARGET_STATE = {
    deployable: ['bg-success', 'deployable'],
    blocked: ['bg-warning text-dark', 'not deployable'],
    refused: ['bg-warning text-dark', 'refused'],
    not_authorised: ['bg-danger', 'dangerous line(s) not authorised'],
    capturable: ['bg-success', 'will be recorded'],
    unchanged: ['bg-secondary', 'unchanged'],
    unread: ['bg-warning text-dark', 'could not be read']
  };

  /* A part's heading: the operation's own words where the server gives them
     (a capture RECORDS; it sends nothing), else the default. */
  function title(obj, part, dflt) {
    return ((obj || {}).titles || {})[part] || dflt;
  }

  function explain(p, part) {
    var items = (p.explain || {})[part] || [];
    return items.map(function (e) {
      return '<div class="small text-muted" data-concept="' + esc(e.concept) + '">'
        + esc(e.text) + '</div>';
    }).join('');
  }

  function section(part, title, body) {
    return '<section class="mb-2" data-pc-part="' + part + '">'
      + '<div class="small fw-semibold text-uppercase text-muted">' + esc(title) + '</div>'
      + body + '</section>';
  }

  function whatHtml(p, hooks) {
    var rows = (p.what.targets || []).map(function (t) {
      var badge = TARGET_STATE[t.state] || ['bg-secondary', t.state || ''];
      var data = t.select_data || {};
      var attrs = Object.keys(data).map(function (k) {
        return ' data-' + esc(k) + '="' + esc(data[k]) + '"';
      }).join('');
      var box = hooks.selectable
        ? '<input class="form-check-input" type="checkbox" data-pc-select id="' + idFor(t.name)
          + '" data-device="' + esc(t.name) + '"' + attrs
          + (t.selectable ? '' : ' disabled')
          + (hooks.onSelect ? ' onchange="' + esc(hooks.onSelect) + '()"' : '') + '> '
        : '';
      return '<div class="form-check d-flex align-items-center gap-2">' + box
        + '<label class="form-check-label fw-semibold" for="' + idFor(t.name) + '">'
        + esc(t.name) + '</label>'
        + '<span class="badge ' + badge[0] + '">' + esc(badge[1]) + '</span></div>';
    }).join('');
    return section('what', title(p, 'what', 'What will happen'), '<div class="small">' + esc(p.what.summary)
      + '</div>' + rows);
  }

  function whatNotHtml(p) {
    var wn = p.what_not || {};
    var body = (wn.items || []).length
      ? (wn.items || []).map(function (i) {
          return '<div class="small mt-1" data-pc-not="' + esc(i.kind) + '"><strong>'
            + esc(i.target) + '</strong>: ' + esc(i.text)
            + ((i.lines || []).length
                ? '<pre class="small bg-body-tertiary p-2 rounded mb-0" '
                  + 'style="max-height:180px;overflow:auto">' + esc(i.lines.join('\n')) + '</pre>'
                : '')
            + '</div>';
        }).join('')
      : '<div class="small" data-pc-none>' + esc(wn.none) + '</div>';
    return section('what_not', 'What will NOT happen', explain(p, 'what_not') + body);
  }

  function programHtml(p, t, hooks) {
    var prog = t.program || {};
    var lines = prog.lines || [];
    // `dangerous` and `authorised` are STRIPPED lines while the program keeps
    // its indentation: compare trimmed, or a line never gets its box (P.3).
    var risky = {}, auth = {};
    (prog.dangerous || []).forEach(function (x) { risky[String(x).trim()] = 1; });
    (prog.authorised || []).forEach(function (x) { auth[String(x).trim()] = 1; });
    var body;
    if (!lines.length) {
      body = '<div class="small text-muted" data-pc-none>' + esc(prog.none) + '</div>';
    } else {
      var rows = lines.map(function (c) {
        var key = String(c).trim();
        if (!risky[key]) return '<div style="white-space:pre">' + esc(c) + '</div>';
        var ok = !!auth[key];
        var box = hooks.authorise
          ? '<input type="checkbox" class="form-check-input mt-0" data-auth-device="'
            + esc(t.name) + '" data-line="' + esc(key) + '"' + (ok ? ' checked' : '')
            + ' onchange="' + esc(hooks.authorise) + '(this.dataset.authDevice)">'
          : '';
        return '<div class="bg-danger-subtle text-danger-emphasis" data-dangerous-line>'
          + '<label class="d-flex gap-2 align-items-start mb-0">' + box
          + '<span style="white-space:pre">' + esc(c) + '</span>'
          + '<span class="ms-auto small">' + (ok ? 'dangerous: AUTHORISED'
            : 'dangerous: tick to authorise this exact line') + '</span></label></div>';
      }).join('');
      body = '<div class="small">Exactly these ' + lines.length
        + ' line(s) will be sent, in this order</div>'
        + '<div class="font-monospace small bg-body-tertiary p-2 rounded" '
        + 'style="max-height:280px;overflow:auto" data-program="' + esc(t.name) + '">'
        + rows + '</div>';
    }
    if (prog.authorisation_error) {
      body += '<div class="small text-danger mt-1" data-authorisation-error>'
        + esc(prog.authorisation_error) + '</div>';
    }
    (prog.notes || []).forEach(function (n) {
      var mine = n.from_this_edit || [], old = n.pre_existing || [];
      var pre = function (x) {
        return '<pre class="small bg-body-tertiary p-2 rounded mt-1 mb-1" '
          + 'style="max-height:140px;overflow:auto">' + esc(x.join('\n')) + '</pre>';
      };
      // A plain note: a title and its lines (the restore's "what these lines
      // replace on the device").
      if (n.lines) {
        body += '<div class="mt-2 small" data-pc-note><div class="fw-semibold">'
          + esc(n.title) + '</div>' + pre(n.lines) + '</div>';
        return;
      }
      body += '<div class="mt-2 small" data-attribution><div class="fw-semibold">'
        + esc(n.title) + '</div>'
        + (n.intent_commit ? '<div class="text-muted">This edit: <code>'
           + esc(n.intent_commit.slice(0, 8)) + '</code> ' + esc(n.intent_subject || '') + '</div>' : '')
        + (n.note ? '<div class="text-warning-emphasis">' + esc(n.note) + '</div>' : '')
        + '<div>From this edit: <strong>' + mine.length + '</strong> line(s)</div>'
        + (mine.length ? pre(mine) : '')
        + '<div>Not from this edit: <strong>' + old.length + '</strong> line(s), '
        + 'already pending before it. They are sent too.</div>'
        + (old.length ? pre(old) : '') + '</div>';
    });
    return section('program', title(p, 'program', 'The exact program'), body);
  }

  function operandsHtml(t) {
    return section('operands', 'Operands', '<div class="small font-monospace">'
      + (t.operands || []).map(function (o) {
          return '<div>' + esc(o.name) + ': ' + esc(o.value) + '</div>';
        }).join('') + '</div>');
  }

  function gatesHtml(t) {
    return section('gates', 'Gates', (t.gates || []).map(function (g) {
      var st = GATE_STATE[g.state] || ['bg-secondary', g.state];
      return '<div class="small" data-pc-gate="' + esc(g.state) + '">'
        + '<span class="badge ' + st[0] + '">' + esc(st[1]) + '</span> '
        + esc(g.name) + (g.detail ? ' <span class="text-muted">(' + esc(g.detail) + ')</span>' : '')
        + '</div>';
    }).join(''));
  }

  function confirmHtml(p) {
    var c = p.confirm || {};
    return section('confirm', 'Confirm', explain(p, 'confirm')
      + '<div class="small fw-semibold"' + (c.may ? '' : ' data-pc-refusal') + '>'
      + esc(c.statement) + '</div>');
  }

  function previewConfirmHtml(p, hooks) {
    hooks = hooks || {};
    // The server names the parts it built. A preview naming others (a newer
    // server, this file cached from an older deploy) is refused, drawn, rather
    // than rendered with a part missing or unknown: that is how a screen
    // loses a part without anyone seeing it go.
    if ((p.parts || []).join(',') !== PARTS.join(',')) {
      return '<div class="alert alert-danger" data-pc-mismatch>This preview cannot be '
        + 'drawn: the server sent parts [' + esc((p.parts || []).join(', ')) + '] and this '
        + 'page draws [' + PARTS.join(', ') + ']. Reload the page. Nothing was confirmed.</div>';
    }
    var cards = (p.targets || []).map(function (t) {
      return '<div class="card mb-2 border-light-subtle" data-pc-target="' + esc(t.name) + '">'
        + '<div class="card-body py-2 px-3"><div class="fw-semibold mb-1">' + esc(t.name) + '</div>'
        + programHtml(p, t, hooks) + operandsHtml(t) + gatesHtml(t) + '</div></div>';
    }).join('');
    return '<div data-preview-confirm="' + esc(p.action) + '">'
      + whatHtml(p, hooks) + whatNotHtml(p) + cards + confirmHtml(p) + '</div>';
  }

  /* PURE: the confirm button's state. With no verified person the button
     STATES the refusal rather than being greyed out with nothing said. */
  function previewConfirmButton(p, selectedCount, label) {
    var c = (p && p.confirm) || {};
    if (!c.may) return {disabled: true, text: c.statement || 'You may not confirm.'};
    if (!selectedCount) return {disabled: true, text: label};
    return {disabled: false, text: label};
  }

  /* ---- The RESULT half (7.1 step 2): what happened, drawn the way what
     will happen is. Six parts, built by the server FROM THE RECEIPT ROWS it
     wrote, so the screen and the record are one computation:
       1 happened     what happened, each target named
       2 did_not      what did not happen, with the reason
       3 sent         per target: the program as sent, its hash against the
                      hash you confirmed
       4 checks       per target: what verify compared, before and after, or
                      why nothing was checked
       5 record       the commit, its tags, the receipt
       6 not_watched  what is not being watched after the change
     COLOUR COMES ONLY FROM THE SERVER'S `level`, never from a branch here: a
     green result on a partial success is a false statement in a different
     medium (the operator, 2026-09-27). Every field goes through esc(), so the
     class of unescaped device text (C88) is closed for anything drawn here. */

  var RESULT_PARTS = ['happened', 'did_not', 'sent', 'checks', 'record', 'not_watched'];

  var LEVEL = {
    success: ['alert-success', 'success', 'Done'],
    partial: ['alert-warning', 'warning', 'Partly done'],
    failed: ['alert-danger', 'danger', 'Not done'],
    nothing: ['alert-secondary', 'secondary', 'Nothing to do']
  };

  var OUTCOME_BADGE = {
    deployed: 'bg-success', refused: 'bg-warning text-dark',
    skipped_drifted: 'bg-warning text-dark', failed: 'bg-danger',
    unattempted: 'bg-secondary', skipped_not_selected: 'bg-secondary',
    captured: 'bg-success', unchanged: 'bg-secondary', moved: 'bg-warning text-dark',
    unread: 'bg-warning text-dark', partial: 'bg-warning text-dark'
  };

  function resultSection(part, title, body) {
    return '<section class="mb-2" data-pr-part="' + part + '">'
      + '<div class="small fw-semibold text-uppercase text-muted">' + esc(title) + '</div>'
      + body + '</section>';
  }

  function pair(a) {
    a = a || [];
    return esc(a[0] == null ? '?' : a[0]) + ' &rarr; ' + esc(a[1] == null ? '?' : a[1]);
  }

  function sentHtml(t, r) {
    var s = t.sent || {};
    var body;
    if (!(s.lines || []).length) {
      body = '<div class="small text-muted" data-pr-none>' + esc(s.none) + '</div>';
    } else {
      body = (s.program_hash
        ? '<div class="small">' + s.lines.length + ' line(s) sent, program <code>'
          + esc((s.program_hash || '').slice(0, 12)) + '</code>: <span data-pr-match="'
          + esc(String(s.matches)) + '"' + (s.matches === false ? ' class="text-danger fw-semibold"' : '')
          + '>' + esc(s.match_words) + '</span></div>'
        : '<div class="small">' + esc(s.caption || (s.lines.length + ' line(s)')) + '</div>')
        + '<div class="font-monospace small bg-body-tertiary p-2 rounded" '
        + 'style="max-height:220px;overflow:auto;white-space:pre" data-pr-program="'
        + esc(t.name) + '">' + esc(s.lines.join('\n')) + '</div>';
    }
    var rb = t.rollback || {};
    if (rb.performed) {
      body += '<div class="small mt-1" data-pr-rollback><span class="badge bg-info text-dark">rolled back</span> '
        + (rb.commands || []).length + ' line(s)'
        + ((rb.not_undone || []).length ? ', ' + rb.not_undone.length
           + ' line(s) not undone because the device never applied them' : '') + '</div>';
    }
    return resultSection('sent', title(r, 'sent', 'What was sent'), body);
  }

  function checksHtml(t, r) {
    var c = t.checks || {};
    var body;
    if (!c.ran) {
      body = '<div class="small text-muted" data-pr-none>Nothing was checked: ' + esc(c.why) + '</div>';
    } else if (c.statements) {
      body = '<div class="small" data-pr-statements>'
        + (c.ok ? '<span class="badge bg-success">matches</span> '
                : '<span class="badge bg-warning text-dark">departs</span> ')
        + c.statements.map(esc).join('; ') + '</div>'
        + ((c.issues || []).length ? '<pre class="small bg-body-tertiary p-2 rounded mb-0">'
           + esc(c.issues.join('\n')) + '</pre>' : '');
    } else {
      var protocols = c.checked_protocols || [];
      var rows = protocols.map(function (p) {
        return '<div><span class="font-monospace">' + esc(p) + '</span> neighbours '
          + pair((c.neighbours || {})[p]) + '</div>';
      }).join('');
      body = '<div class="small" data-pr-checked="' + esc(protocols.join(',')) + '">'
        + (c.ok ? '<span class="badge bg-success">verify passed</span> '
                : '<span class="badge bg-danger">verify failed</span> ')
        + (protocols.length ? 'checked ' + esc(protocols.join(', ')) : esc(c.neighbours_note || 'no routing protocol on this device'))
        + '</div><div class="small font-monospace">' + rows
        + '<div>routes ' + pair(c.routes) + '</div><div>interfaces up '
        + pair(c.interfaces_up) + '</div></div>'
        + (c.issues || []).map(function (i) {
            return '<div class="small text-danger">' + esc(i) + '</div>';
          }).join('')
        + (c.pending_convergence || []).map(function (i) {
            return '<div class="small text-muted">' + esc(i) + '</div>';
          }).join('');
    }
    return resultSection('checks', title(r, 'checks', 'What was checked'), body);
  }

  function previewConfirmResultHtml(r, hooks) {
    hooks = hooks || {};
    if (!r || (r.parts || []).join(',') !== RESULT_PARTS.join(',')) {
      return '<div class="alert alert-danger" data-pr-mismatch>This result cannot be drawn: '
        + 'the server sent parts [' + esc(((r || {}).parts || []).join(', ')) + '] and this page '
        + 'draws [' + RESULT_PARTS.join(', ') + ']. Reload the page; the receipt holds the record.</div>';
    }
    var lv = LEVEL[r.level] || ['alert-secondary', 'secondary', r.level];
    var rows = (r.happened.targets || []).map(function (t) {
      return '<div class="d-flex align-items-center gap-2"><span class="fw-semibold">'
        + esc(t.name) + '</span><span class="badge ' + (OUTCOME_BADGE[t.outcome] || 'bg-secondary')
        + '" data-pr-outcome="' + esc(t.outcome) + '">' + esc(t.words) + '</span>'
        + (t.outcome === 'skipped_drifted' && hooks.repreview
            ? '<button class="btn btn-outline-primary btn-sm py-0" onclick="'
              + esc(hooks.repreview) + '([\'' + esc(t.name) + '\'])">Preview again</button>' : '')
        + '</div>';
    }).join('');
    var head = '<div class="alert ' + lv[0] + ' py-2 px-3" data-pr-level="' + esc(r.level) + '">'
      + '<strong>' + esc(lv[2]) + '.</strong> ' + esc(r.happened.summary) + '</div>';
    var dn = r.did_not || {};
    var didNot = (dn.items || []).length
      ? (dn.items || []).map(function (i) {
          return '<div class="small mt-1" data-pr-not="' + esc(i.kind) + '"><strong>'
            + esc(i.target) + '</strong>: ' + esc(i.text)
            + ((i.lines || []).length ? '<pre class="small bg-body-tertiary p-2 rounded mb-0">'
               + esc(i.lines.join('\n')) + '</pre>' : '') + '</div>';
        }).join('')
      : '<div class="small" data-pr-none>' + esc(dn.none) + '</div>';
    var cards = (r.targets || []).map(function (t) {
      return '<div class="card mb-2 border-light-subtle" data-pr-target="' + esc(t.name) + '">'
        + '<div class="card-body py-2 px-3"><div class="fw-semibold mb-1">' + esc(t.name)
        + (t.stage ? ' <span class="small text-muted">stopped at: ' + esc(t.stage) + '</span>' : '')
        + '</div>' + (t.reason ? '<div class="small mb-1">' + esc(t.reason) + '</div>' : '')
        + sentHtml(t, r) + checksHtml(t, r) + '</div></div>';
    }).join('');
    var rec = r.record || {};
    var receipt = rec.receipt || {};
    var record = '<div class="small font-monospace">'
      + '<div>golden commit: ' + (rec.commit ? '<code>' + esc(rec.commit.slice(0, 12)) + '</code>' : 'none') + '</div>'
      + '<div>baseline: ' + (rec.baseline ? esc(rec.baseline) : 'none') + '</div>'
      + ((rec.tags || []).length ? '<div>tags: ' + esc(rec.tags.join(', ')) + '</div>' : '')
      // Only an operation that writes a receipt has a receipt line: a capture
      // has none, and "NOT WRITTEN" there would be a false alarm.
      + (rec.receipt ? '<div data-pr-receipt="' + (receipt.ok ? 'ok' : 'failed') + '"'
        + (receipt.ok ? '' : ' class="text-danger fw-semibold"') + '>receipt: '
        + (receipt.ok ? esc(receipt.written) + ' row(s) written'
                      : 'NOT WRITTEN: ' + esc(receipt.error || 'not reported')) + '</div>' : '')
      + '</div>'
      + '<div class="small">' + esc(rec.statement) + '</div>';
    return '<div data-pr-result="' + esc(r.action) + '">' + head
      + resultSection('happened', title(r, 'happened', 'What happened'), rows)
      + resultSection('did_not', 'What did not happen', didNot) + cards
      + resultSection('record', 'The record', record)
      + resultSection('not_watched', 'What is not being watched', '<div class="small text-muted">'
          + esc(r.not_watched) + '</div>') + '</div>';
  }

  /* The toast level for a result: from the server's level, never guessed. */
  function previewConfirmResultLevel(r) {
    return (LEVEL[(r || {}).level] || LEVEL.nothing)[1];
  }

  root.previewConfirmHtml = previewConfirmHtml;
  root.previewConfirmButton = previewConfirmButton;
  root.previewConfirmResultHtml = previewConfirmResultHtml;
  root.previewConfirmResultLevel = previewConfirmResultLevel;
})(typeof window !== 'undefined' ? window : this);
