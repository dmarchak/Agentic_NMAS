/* Credentials > The break-glass record (board 7, signed off 2026-10-03).
 *
 * `breakglassExport`, the export card's confirm. ONE export, routes/breakglass.py's: this posts
 * the passphrase twice with the list and the preview's hash, and clears both fields the moment
 * the request leaves. When the sealed file comes back, the browser HASHES THE BYTES IT RECEIVED
 * (SHA-256, before saving them) and compares with the sha256 the server recorded, saves the
 * file, and records its word at /v2/credentials/intact; that answer is the result card, drawn
 * in place of this one. A refusal is said beside the button in the server's words.
 *
 * Busy on itself ("Building, sealing and verifying…") until the answer. ES5 and Alpine's CSP
 * build: getters and argument-free methods, every data-* read from $root. `exportButton`,
 * `exportOutcome` and `hexOf` are PURE, executed in duktape by tests/test_credentials_v2.py.
 */
(function (root) {
  'use strict';

  /* PURE. The confirm's state from the two fields. */
  function exportButton(pass, again, min, label) {
    if ((pass || '').length < min) {
      return {disabled: true, text: 'The passphrase needs ' + min + ' characters or more'};
    }
    if (pass !== again) return {disabled: true, text: 'The two passphrases differ'};
    return {disabled: false, text: label};
  }

  /* PURE. What the page does with the export's answer: the file to save, or why not. */
  function exportOutcome(status, body) {
    if (status === 200 && body && body.file && body.sha256) {
      return {ok: true, file: body.file, sha256: body.sha256,
              filename: body.filename || 'nmas-breakglass.bg', error: ''};
    }
    var happened = ((body || {}).result || {}).happened || {};
    var why = (body && body.error) || happened.summary || ('refused (HTTP ' + status + ')');
    if (why.indexOf('Nothing was sent') !== 0) why = 'Nothing was sent: ' + why;
    return {ok: false, file: '', sha256: '', filename: '', error: why};
  }

  /* PURE. Bytes (an array of numbers) as lowercase hex. */
  function hexOf(bytes) {
    var out = '';
    for (var i = 0; i < bytes.length; i++) out += ('0' + (bytes[i] & 255).toString(16)).slice(-2);
    return out;
  }

  function bytesOf(b64) {
    var bin = root.atob(b64), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function sha256Of(bytes) {
    var subtle = root.crypto && root.crypto.subtle;
    if (!subtle) return Promise.resolve('');      // said by the result: not checked
    return subtle.digest('SHA-256', bytes).then(function (buf) {
      return hexOf(new Uint8Array(buf));
    }, function () { return ''; });
  }

  function save(bytes, filename) {
    var blob = new root.Blob([bytes], {type: 'application/octet-stream'});
    var url = root.URL.createObjectURL(blob);
    var a = root.document.createElement('a');
    a.href = url;
    a.download = filename;
    root.document.body.appendChild(a);
    a.click();
    a.remove();
    root.setTimeout(function () { root.URL.revokeObjectURL(url); }, 10000);
  }

  function register() {
    root.Alpine.data('breakglassExport', function () {
      return {
        busy: false, done: false, error: '', state: {disabled: true, text: ''},
        init: function () { this.refresh(); },
        field: function (name) { return this.$root.querySelector('[data-bg-' + name + ']'); },
        refresh: function () {
          var p = this.field('pass'), a = this.field('again');
          this.state = exportButton(p ? p.value : '', a ? a.value : '',
                                    parseInt(this.$root.getAttribute('data-min'), 10) || 12,
                                    this.$root.getAttribute('data-label'));
        },
        get blocked() { return this.busy || this.done || this.state.disabled; },
        get label() { return this.busy ? 'Building, sealing and verifying…' : this.state.text; },
        get hasError() { return !!this.error; },
        get noError() { return !this.error; },
        confirm: function () {
          var self = this, el = self.$root;
          if (self.blocked) return;
          var p = self.field('pass'), a = self.field('again');
          var body = JSON.stringify({list_name: el.getAttribute('data-list'),
                                     hash: el.getAttribute('data-hash'),
                                     passphrase: p.value, confirm: a.value});
          // Cleared at once: nothing on the page holds the passphrase once it is sent.
          p.value = ''; a.value = '';
          self.busy = true;
          self.error = '';
          root.fetch(el.getAttribute('data-export-url'), {
            method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: body
          }).then(function (r) {
            body = null;
            return r.json().then(function (b) { return exportOutcome(r.status, b); },
                                 function () { return exportOutcome(r.status, null); });
          }).then(function (o) {
            if (!o.ok) { self.busy = false; self.refresh(); self.error = o.error; return null; }
            var bytes = bytesOf(o.file);
            o.file = '';
            return sha256Of(bytes).then(function (hex) {
              save(bytes, o.filename);
              var form = new root.URLSearchParams();
              form.set('list', el.getAttribute('data-list'));
              form.set('sha256', o.sha256);
              form.set('browser_sha256', hex);
              form.set('filename', o.filename);
              return root.fetch(el.getAttribute('data-intact-url'), {
                method: 'POST', body: form,
                headers: {'Content-Type': 'application/x-www-form-urlencoded'}});
            }).then(function (r) { return r.text(); }).then(function (html) {
              self.busy = false;
              self.done = true;
              if (root.htmx && root.htmx.swap) root.htmx.swap(el, html, {swapStyle: 'outerHTML'});
              else el.outerHTML = html;
            });
          }).catch(function (e) {
            self.busy = false;
            self.refresh();
            self.error = 'The request failed before an answer came back (' + e + '). Whether a '
              + 'record was built is unknown: the reveal record says, and nothing was saved here.';
          });
        }
      };
    });
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('alpine:init', register);
  }
  root.NMAS_CREDENTIALS = {exportButton: exportButton, exportOutcome: exportOutcome,
                           hexOf: hexOf};
})(typeof window !== 'undefined' ? window : this);
