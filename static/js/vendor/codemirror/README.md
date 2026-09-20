# CodeMirror (vendored) — files to add

The template editor uses CodeMirror when it is present here and falls back to a
styled `<textarea>` when it is not. The editor is fully usable either way; the
fallback loses syntax highlighting and bracket matching only.

**This directory is intentionally empty of library code.** It was not possible
to download CodeMirror in the environment where the editor was written, and
shipping a hand-written stand-in would have been worse than shipping nothing.

## Why vendored rather than a CDN

The tool must work on air-gapped management networks. No `<script src="https://…">`.

## Drop in these files

CodeMirror 5 (simplest — single file, no bundler):

    static/js/vendor/codemirror/codemirror.js
    static/js/vendor/codemirror/codemirror.css
    static/js/vendor/codemirror/mode/jinja2/jinja2.js

From <https://codemirror.net/5/> — download the ZIP, copy `lib/codemirror.js`,
`lib/codemirror.css`, and `mode/jinja2/jinja2.js`.

The partial detects them at load:

```js
const hasCodeMirror = typeof window.CodeMirror !== 'undefined';
```

No other change is needed — add the files and reload.
