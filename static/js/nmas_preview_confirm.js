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
    ready: ['bg-success', 'ready'],
    unchanged: ['bg-secondary', 'unchanged'],
    unread: ['bg-warning text-dark', 'could not be read'],
    seedable: ['bg-success', 'will be seeded'],
    has_intent: ['bg-secondary', 'already has intent'],
    unseedable: ['bg-warning text-dark', 'cannot be seeded'],
    retirable: ['bg-danger', 'will be retired']
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
        + '<span class="badge ' + badge[0] + '">' + esc(badge[1]) + '</span>'
        // Why this one cannot be selected, beside the box it disables.
        + (t.selectable || !t.why_not ? '' : '<span class="small text-danger" data-pc-why-not>'
           + 'Cannot be selected: ' + esc(t.why_not) + '</span>')
        + '</div>';
    }).join('');
    return section('what', title(p, 'what', 'What will happen'), '<div class="small">' + esc(p.what.summary)
      + '</div>' + rows);
  }

  // Mode B (7.3 step 2): each line the device has and intent lacks, with a box
  // that selects it for removal BY ID (the plan is masked, so the text could
  // never be sent back), and why where it cannot be removed, beside the box.
  function removableHtml(i, hooks) {
    return (i.removable || []).map(function (r) {
      var box = hooks.remove
        ? '<input type="checkbox" class="form-check-input mt-0" data-remove-device="'
          + esc(i.target) + '" data-remove-id="' + esc(r.id) + '"'
          + (r.selected ? ' checked' : '') + (r.why_not ? ' disabled' : '')
          + ' onchange="' + esc(hooks.remove) + '(this.dataset.removeDevice)"> '
        : '';
      var state = r.why_not
        ? '<span class="text-danger" data-pc-why-not>cannot be removed: ' + esc(r.why_not) + '</span>'
        : r.selected
          ? '<span data-pc-removing>will be removed: it is in the program, and needs your stated reason there</span>'
          : '<span>not removed</span>';
      return '<div class="d-flex gap-2 align-items-start mt-1" data-pc-removable>' + box
        + '<code style="white-space:pre">' + esc(r.text) + '</code>'
        + (r.children ? '<span class="small">(the whole stanza, ' + r.children + ' line(s) with it)</span>' : '')
        + ' <span class="small">' + state + '</span></div>';
    }).join('');
  }

  function whatNotHtml(p, hooks) {
    hooks = hooks || {};
    var wn = p.what_not || {};
    var body = (wn.items || []).length
      ? (wn.items || []).map(function (i) {
          return '<div class="small mt-1" data-pc-not="' + esc(i.kind) + '"><strong>'
            + esc(i.target) + '</strong>: ' + esc(i.text)
            + ((i.removable || []).length
                ? removableHtml(i, hooks)
                : (i.lines || []).length
                  ? '<pre class="small bg-body-tertiary text-body p-2 rounded mb-0" '
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
    // `dangerous`, `secret` and each authorisation's `line` are STRIPPED
    // (and secret positions masked) while the program keeps its indentation:
    // compare trimmed, or a line never gets its box (P.3).
    var risky = {}, auth = {};
    (prog.dangerous || []).forEach(function (x) { risky[String(x).trim()] = 'dangerous'; });
    (prog.secret || []).forEach(function (x) { risky[String(x).trim()] = 'secret'; });
    // Mode B (7.3 step 2): a line the device has and intent does not, removed
    // because a person SELECTED it; every one needs a stated reason.
    (prog.removal || []).forEach(function (x) { risky[String(x).trim()] = 'removal'; });
    (prog.authorised || []).forEach(function (a) {
      if (a && typeof a === 'object') auth[String(a.line).trim()] = a;
    });
    var prior = (prog.prior && prog.prior.lines) || {};
    var body;
    if (!lines.length) {
      body = '<div class="small text-muted" data-pc-none>' + esc(prog.none) + '</div>';
    } else {
      var rows = lines.map(function (c) {
        var key = String(c).trim();
        var kind = risky[key];
        if (!kind) return '<div style="white-space:pre">' + esc(c) + '</div>';
        var a = auth[key];
        var what = kind === 'secret'
          ? 'adds a secret line the device does not hold'
          : kind === 'removal'
            ? 'removes a line the device has and intent does not'
            : 'dangerous';
        // A reason is TESTIMONY (C140): the person's statement, drawn as that,
        // never as the cause. Its minimum is shape, never quality.
        var state = a && a.reason
          ? what + ': AUTHORISED, stated reason: "' + esc(a.reason) + '"'
          : what + ': authorise this exact line with your reason';
        var box = hooks.authorise
          ? '<input type="checkbox" class="form-check-input mt-0" data-auth-device="'
            + esc(t.name) + '" data-line="' + esc(key) + '"' + (a ? ' checked' : '')
            + ' onchange="' + esc(hooks.authorise) + '(this.dataset.authDevice)">'
          : '';
        var reason = hooks.authorise
          ? '<input type="text" class="form-control form-control-sm mt-1" data-auth-reason'
            + ' data-auth-device="' + esc(t.name) + '" data-line="' + esc(key) + '"'
            + ' placeholder="why this line is deliberate (a few words, recorded as yours)"'
            + ' value="' + esc(a ? a.reason : '') + '"'
            + ' onchange="if (this.parentNode.querySelector(\'input[type=checkbox]\').checked) '
            + esc(hooks.authorise) + '(this.dataset.authDevice)">'
          : '';
        // The AGGREGATE (C140): the same line authorised here again and again
        // is a pattern worth seeing. An unreadable record is said.
        var seen = prior[key];
        var history = (prog.prior && prog.prior.state === 'unreadable')
          ? '<div class="small" data-auth-prior>whether it was authorised here before is '
            + 'unknown: the receipt record could not be read</div>'
          : seen
            ? '<div class="small" data-auth-prior>authorised on this device ' + seen.count
              + ' time(s) before; last ' + esc(seen.last_at) + ' by ' + esc(seen.last_actor)
              + ', stated reason: "' + esc(seen.last_reason) + '"'
              // A change it was part of ROLLED BACK: shown, never blocked, so a
              // new reason is written knowing the old one failed (Mode B).
              + (seen.rolled_back_at
                  ? '. <strong data-auth-rolled-back>Rolled back at ' + esc(seen.rolled_back_at)
                    + ': ' + esc(seen.rolled_back_why) + '</strong>'
                  : '')
              + '</div>'
            : '';
        return '<div class="bg-danger-subtle text-danger-emphasis" data-dangerous-line data-kind="'
          + kind + '"><label class="d-flex gap-2 align-items-start mb-0">' + box
          + '<span style="white-space:pre">' + esc(c) + '</span>'
          + '<span class="ms-auto small">' + state + '</span></label>' + reason + history
          + '</div>';
      }).join('');
      // What the program IS, when it is not something sent (C127): a
      // capture's diff and an onboarding's startup config are sent nowhere,
      // and the one sentence said they were.
      body = '<div class="small"' + (prog.caption ? ' data-pc-caption' : '') + '>'
        + (prog.caption ? esc(prog.caption) + ' (' + lines.length + ' line(s))'
                        : 'Exactly these ' + lines.length + ' line(s) will be sent, in this order')
        + '</div>'
        + '<div class="font-monospace small bg-body-tertiary text-body p-2 rounded" '
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
        return '<pre class="small bg-body-tertiary text-body p-2 rounded mt-1 mb-1" '
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

  /* An operand that DECIDES the outcome (`blocks`: what it blocks) is drawn
     apart from the informational ones, with what it blocks, first: "committed
     intent: -1" sat among the others in the same font and was the one line
     that decided the operation (the operator, 2026-09-28). */
  function operandsHtml(t) {
    var ops = t.operands || [];
    var blocking = ops.filter(function (o) { return o.blocks; });
    var plain = ops.filter(function (o) { return !o.blocks; });
    return section('operands', 'Operands',
      blocking.map(function (o) {
        // Its CONTENT, not only a count (C179), and both ways out, each with
        // what it asserts. Text only: neither resolution is one click away.
        return '<div class="small mb-2" data-pc-blocking>'
          + '<div class="text-danger-emphasis fw-semibold">'
          + '<span class="badge bg-danger">blocks ' + esc(o.blocks) + '</span> '
          + esc(o.name) + ': ' + esc(o.value) + '</div>'
          + ((o.lines || []).length ? '<pre class="small mb-1 p-1 bg-body-tertiary text-body">'
             + (o.lines || []).map(esc).join('\n') + '</pre>' : '')
          + ((o.resolutions || []).length ? '<ul class="mb-0" data-pc-resolutions>'
             + o.resolutions.map(function (r) {
                 return '<li>' + esc(r.do) + ' <span class="text-muted">asserts: '
                   + esc(r.asserts) + (r.note ? '; ' + esc(r.note) : '') + '</span></li>';
               }).join('') + '</ul>' : '')
          + '</div>';
      }).join('')
      + '<div class="small font-monospace">'
      + plain.map(function (o) {
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

  /* What confirming WILL achieve, at the confirm, when the preview knows
     (the operator, 2026-09-28: the preview had computed that nothing would be
     committed and no baseline taken, drew both in sections above, and offered
     Confirm as if the operation would do what it was run for). */
  function confirmHtml(p) {
    var c = p.confirm || {};
    return section('confirm', 'Confirm', explain(p, 'confirm')
      + (c.effect ? '<div class="alert alert-warning py-1 px-2 small mb-1" data-pc-effect>'
                    + esc(c.effect) + '</div>' : '')
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
      + whatHtml(p, hooks) + whatNotHtml(p, hooks) + cards + confirmHtml(p) + '</div>';
  }

  /* PURE: the confirm button's state. With no verified person the button
     STATES the refusal rather than being greyed out with nothing said. */
  function previewConfirmButton(p, selectedCount, label) {
    var c = (p && p.confirm) || {};
    if (!c.may) return {disabled: true, text: c.statement || 'You may not confirm.'};
    if (!selectedCount) return {disabled: true, text: c.button || label};
    // The server's label when it knows the effect: "Record the denial only",
    // never "Record 9 device(s)" over a save that will record none.
    return {disabled: false, text: c.button || label};
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

  // [class, words, restored?] per rollback state (modules/pipeline.py
  // ROLLBACK_STATES). Only the first two leave the device as it was.
  var ROLLBACK_BADGE = {
    restored: ['bg-success', 'rolled back, read back', true],
    nothing_to_undo: ['bg-secondary', 'nothing to roll back', true],
    incomplete: ['bg-danger', 'rollback INCOMPLETE'],
    sent_unverified: ['bg-warning text-dark', 'rollback sent, NOT read back'],
    failed: ['bg-danger', 'rollback FAILED'],
    not_attempted: ['bg-danger', 'NOT rolled back']
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
        + '<div class="font-monospace small bg-body-tertiary text-body p-2 rounded" '
        + 'style="max-height:220px;overflow:auto;white-space:pre" data-pr-program="'
        + esc(t.name) + '">' + esc(s.lines.join('\n')) + '</div>';
    }
    // The authorised exceptions, each with its STATED reason (C140): the
    // person's testimony, drawn as that, never as an established cause. A
    // receipt from before reasons existed says so.
    (s.authorised || []).forEach(function (a) {
      var line = (a && typeof a === 'object') ? a.line : a;
      var why = (a && typeof a === 'object' && a.reason) ? a.reason : '';
      body += '<div class="small mt-1" data-pr-authorised>authorised'
        + (s.actor ? ' by ' + esc(s.actor) : '') + ': <code>' + esc(line) + '</code>, '
        + (why ? 'stated reason: "' + esc(why) + '"'
               : 'no reason recorded (authorised before reasons were required)')
        + '</div>';
    });
    var rb = t.rollback || {};
    if (rb.performed) {
      // What the rollback ACHIEVED, never only that it ran (C112): a rollback
      // that raised used to be drawn "rolled back". A row from before the
      // state was recorded says so rather than guessing.
      var st = ROLLBACK_BADGE[rb.state] || ['bg-secondary', 'rollback: outcome not recorded'];
      body += '<div class="small mt-1" data-pr-rollback="' + esc(rb.state || 'unrecorded')
        + '"><span class="badge ' + st[0] + '">' + esc(st[1]) + '</span> '
        + (rb.commands || []).length + ' line(s) sent'
        + ((rb.not_undone || []).length ? ', ' + rb.not_undone.length
           + ' line(s) not undone because the device never applied them' : '')
        + (rb.detail ? '<div' + (ROLLBACK_BADGE[rb.state] && ROLLBACK_BADGE[rb.state][2]
             ? '' : ' class="text-danger fw-semibold"') + '>' + esc(rb.detail) + '</div>' : '')
        + ((rb.remaining || []).length ? '<pre class="small bg-body-tertiary text-body p-2 rounded mb-0">'
           + esc(rb.remaining.join('\n')) + '</pre>' : '')
        + '</div>';
    }
    return resultSection('sent', title(r, 'sent', 'What was sent'), body);
  }

  function checksHtml(t, r) {
    var c = t.checks || {};
    var body;
    if (!c.ran) {
      body = '<div class="small text-muted" data-pr-none>Nothing was checked: ' + esc(c.why) + '</div>';
    } else if (c.statements) {
      // The badge's words are the operation's where it gives them ("answered"
      // is not "matches"); intent's comparison is the default.
      var words = c.words || ['matches', 'departs'];
      body = '<div class="small" data-pr-statements>'
        + (c.ok ? '<span class="badge bg-success">' + esc(words[0]) + '</span> '
                : '<span class="badge bg-warning text-dark">' + esc(words[1]) + '</span> ')
        + c.statements.map(esc).join('; ') + '</div>'
        + ((c.issues || []).length ? '<pre class="small bg-body-tertiary text-body p-2 rounded mb-0">'
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
        + ((c.from_intent || []).length ? ' <span data-pr-from-intent>(declared by intent, not '
           + 'running before: ' + esc(c.from_intent.join(', ')) + ')</span>' : '')
        + (c.intent_note ? '<div class="small text-muted" data-pr-intent-note>'
           + esc(c.intent_note) + '</div>' : '')
        + '</div><div class="small font-monospace">' + rows
        + '<div data-pr-routes="' + esc(String(c.routes_compared)) + '">routes ' + pair(c.routes)
        + (c.routes_compared === false ? ' <span class="text-muted">(read, NOT compared: '
             + 'the route check is skipped for this deploy)</span>'
           : c.routes_compared === true ? '' : ' <span class="text-muted">(whether it was '
             + 'compared was not recorded)</span>') + '</div><div>interfaces up '
        + pair(c.interfaces_up) + '</div></div>'
        + (c.issues || []).map(function (i) {
            return '<div class="small text-danger">' + esc(i) + '</div>';
          }).join('')
        + (c.intent_unmet || []).map(function (i) {
            return '<div class="small text-danger" data-pr-intent-unmet>' + esc(i)
              + ' (not rolled back: the change cannot have caused it)</div>';
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
            + ((i.lines || []).length ? '<pre class="small bg-body-tertiary text-body p-2 rounded mb-0">'
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
