/* SDN › Apps, Add an app as a Draft… (the operator's decision of 2026-11-10; board
 * docs/boards/authoring-from-words.html, artboard F): the folder picker's preview sends each
 * file with its path inside the chosen folder.
 *
 * A browser's own post of an <input type=file webkitdirectory> does not reliably keep a file's
 * relative path (some send its name only), and the server takes the top folder's name as the
 * app's and each file's path below it (modules/apps/draft_write.py `files_from_upload`). So on
 * the form marked `data-draft-folder`, htmx's request is configured here: every `file` entry is
 * replaced by the same file named by its `webkitRelativePath` (`<folder>/<path>`). Nothing else
 * in the request changes; the button is busy on itself as htmx's every post is.
 *
 * ES5. `named` and `rewrite` are PURE, executed in duktape by tests/test_draft_write.py.
 */
(function (root) {
  'use strict';

  /* PURE. Each picked file as [file, the name to send]: its path in the folder when the
     browser gives one, else its name (the server then refuses, naming why). */
  function named(files) {
    var out = [], i, f;
    for (i = 0; i < (files ? files.length : 0); i += 1) {
      f = files[i];
      out.push([f, (f && f.webkitRelativePath) || (f && f.name) || '']);
    }
    return out;
  }

  /* PURE. *fd* (a FormData, or anything with delete and append) with its `file` entries
     replaced by *files*, each named by its relative path. Returns how many were sent. */
  function rewrite(fd, files) {
    var each = named(files), i;
    fd['delete']('file');
    for (i = 0; i < each.length; i += 1) fd.append('file', each[i][0], each[i][1]);
    return each.length;
  }

  function onConfigRequest(e) {
    var d = e.detail, form = d && d.elt && d.elt.closest ? d.elt.closest('form') : null;
    if (!form || !form.hasAttribute('data-draft-folder') || !d.formData) return;
    var input = form.querySelector('input[type=file][name=file]');
    if (input) rewrite(d.formData, input.files);
  }

  if (root.document && root.document.addEventListener) {
    root.document.addEventListener('htmx:configRequest', onConfigRequest);
  }
  root.NMAS_DRAFT = {named: named, rewrite: rewrite};
}(typeof window !== 'undefined' ? window : this));
