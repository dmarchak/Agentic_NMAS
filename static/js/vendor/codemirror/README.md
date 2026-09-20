# CodeMirror 5.65.16 (vendored)

**Vendored and in use.** The template editor uses CodeMirror for syntax
highlighting of Jinja2 templates.

    codemirror.js              402 KB   CodeMirror 5.65.16 core
    codemirror.css             8.7 KB   base stylesheet
    mode/jinja2/jinja2.js      5.9 KB   Jinja2 mode (defines the "jinja2" mode)

## Why vendored rather than a CDN

The tool has to work on air-gapped management networks. No `<script src="https://…">`.

## Load order matters

`mode/jinja2/jinja2.js` calls `CodeMirror.defineMode("jinja2", …)`, so it must
load **after** `codemirror.js`. `templates/partials/template_editor.html` loads
them in that order.

A missing or misplaced mode file is **not** an error in CodeMirror — the editor
initialises with an unknown mode and renders as plain text, which looks
identical to the library being absent. The partial therefore checks
`CodeMirror.modes.jinja2` explicitly and reports the two failure cases
differently, and `tests/test_codemirror_assets.py` asserts that every script
path in the partial resolves to a file that exists.

## Verifying highlighting

Highlighting was verified by executing the library in a JS engine and
tokenising a real template line, rather than by assuming the files load:

    {% for i in vars.interfaces %} ip address {{ i.ipv4 }}

    '{%'  -> tag        ' for' -> keyword    'i'   -> variable
    '%}'  -> tag        ' in'  -> keyword    '{{'  -> tag

## Upgrading

Download from <https://codemirror.net/5/>, then copy `lib/codemirror.js`,
`lib/codemirror.css`, and `mode/jinja2/jinja2.js` preserving that last path.
