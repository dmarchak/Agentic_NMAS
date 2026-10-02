"""CLAUDE.md cites real checks, and every citation names a file and section that exist (the
operator, 2026-10-02; rules_audit check 1, and item 5 of the consolidation).

1. Every standing rule in CLAUDE.md ends with its enforcement: a bracket that names a check
   (a path) or says it is not mechanised (or "partly"), never nothing.
2. Every path CLAUDE.md names (tests/, scripts/, modules/, routes/, docs/, deploy/, .claude/)
   exists, so a rule never cites a check that was renamed or removed.
3. Every rule's [why] link opens a section of docs/LESSONS.md that exists, and every LESSONS
   section is linked from its rule (both directions).
4. Every section citation anywhere in the repository resolves: `docs/<file>.md#<section>`
   (as text or a link), a markdown link `(<file>.md#<section>)`, and a same-file `(#section)`,
   against the target's headings as GitHub anchors them (or an explicit `{#id}`).
5. A citation that QUOTES CLAUDE.md (`CLAUDE.md "X"`) quotes text CLAUDE.md still holds, so a
   rule moved out leaves no citation pointing at the wrong file.
Floors on every population, and controls planting each failure.
"""

import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE = os.path.join(ROOT, "CLAUDE.md")
LESSONS = os.path.join(ROOT, "docs", "LESSONS.md")


def read(path):
    return open(path, encoding="utf-8").read()


def slug(heading):
    """GitHub's anchor for a heading: lowercase, punctuation dropped (hyphens and underscores
    kept), spaces to hyphens. An explicit `{#id}` (the manual's form) wins."""
    m = re.search(r"\{#([A-Za-z0-9_-]+)\}\s*$", heading)
    if m:
        return m.group(1)
    h = re.sub(r"[`*]", "", heading.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(path):
    out, in_code = set(), False
    for ln in read(path).splitlines():
        if ln.startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"#{1,6} ", ln):
            out.add(slug(ln.lstrip("#").strip()))
    return out


def rules(text):
    """The standing rules: each `- **` bullet between "## Standing rules" and the next `## `,
    with its continuation lines."""
    sect = text.split("## Standing rules", 1)[1].split("\n## ", 1)[0]
    out, cur = [], None
    for ln in sect.splitlines():
        if ln.startswith("- **"):
            cur = [ln]
            out.append(cur)
        elif cur is not None and ln.startswith("  "):
            cur.append(ln)
        else:
            cur = None
    return ["\n".join(r) for r in out]


ENFORCEMENT = re.compile(r"\[([^\]]*(?:tests/|scripts/|hook|not mechanised|partly)[^\]]*)\]")


def unenforced(text):
    return [r.splitlines()[0][:80] for r in rules(text) if not ENFORCEMENT.search(r)]


PATH = re.compile(r"(?<![\w/.])((?:tests|scripts|modules|routes|docs|deploy|\.claude)/[\w./-]*[\w-])")


def missing_paths(text, root=ROOT):
    found = sorted({m.group(1).rstrip(".") for m in PATH.finditer(text)})
    return found, [p for p in found if not os.path.exists(os.path.join(root, p.split("#")[0]))]


def tracked_text_files():
    names = subprocess.run(["git", "-C", ROOT, "ls-files", "--cached", "--others",
                            "--exclude-standard"], capture_output=True, text=True).stdout.split()
    out = []
    for n in names:
        if n.endswith((".md", ".py", ".txt", ".html", ".js", ".yml", ".json", ".sh")) or "/" not in n:
            p = os.path.join(ROOT, n)
            if os.path.isfile(p):
                out.append(n)
    return out


DOC_CITE = re.compile(r"(docs/[\w/.-]+\.md)#([\w-]+)")
REL_LINK = re.compile(r"\]\(((?:[\w./-]+/)?[\w.-]+\.md)?#([\w-]+)\)")


def broken_citations(files, root=ROOT):
    """Every section citation in *files* whose file or section does not exist."""
    cache, bad, seen = {}, [], 0

    def has(path, anchor):
        if path not in cache:
            cache[path] = anchors(path) if os.path.isfile(path) else None
        return cache[path] is not None and anchor in cache[path]

    for rel in files:
        if rel == "tests/test_claude_md.py":
            continue                                   # its controls plant broken citations
        try:
            text = read(os.path.join(root, rel))
        except (UnicodeDecodeError, OSError):
            continue
        here = os.path.dirname(os.path.join(root, rel))
        for m in DOC_CITE.finditer(text):
            seen += 1
            if not has(os.path.join(root, m.group(1)), m.group(2)):
                bad.append(f"{rel}: {m.group(0)}")
        if rel.endswith(".md"):
            for m in REL_LINK.finditer(text):
                target = m.group(1)
                if target and target.startswith("docs/"):
                    continue                                   # counted above
                seen += 1
                path = os.path.normpath(os.path.join(here, target)) if target else os.path.join(root, rel)
                if not has(path, m.group(2)):
                    bad.append(f"{rel}: {m.group(0)}")
    return seen, bad


def norm(s):
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\n\s*#\s*", " ", s)                  # a quote wrapped in a code comment
    return re.sub(r"\s+", " ", re.sub(r"[*`_]", "", s)).strip().lower()


QUOTE = re.compile(r"""CLAUDE\.md(?:'s)?(?:,|:)?[ \n]+["“](.+?)["”]""", re.S)


def stale_quotes(files, claude_text, root=ROOT):
    body, seen, bad = norm(claude_text), 0, []
    for rel in files:
        if rel in ("CLAUDE.md", "docs/LESSONS.md") or rel.startswith("tests/test_claude_md"):
            continue
        try:
            text = read(os.path.join(root, rel))
        except (UnicodeDecodeError, OSError):
            continue
        for m in QUOTE.finditer(text):
            words = norm(m.group(1)).rstrip(".…").split()
            if len(" ".join(words)) < 6:
                continue
            seen += 1
            if " ".join(words[:5]) not in body:
                bad.append(f"{rel}: CLAUDE.md \"{m.group(1)[:60]}\"")
    return seen, bad


class TestCLAUDEmdCitesRealChecks:
    def test_every_rule_names_its_enforcement(self):
        text = read(CLAUDE)
        assert len(rules(text)) >= 70, len(rules(text))                  # the floor
        assert unenforced(text) == [], unenforced(text)

    def test_every_path_it_names_exists(self):
        found, missing = missing_paths(read(CLAUDE))
        assert len(found) >= 60, len(found)                               # the floor
        assert missing == [], missing

    def test_every_why_link_opens_a_lessons_section_and_every_section_is_linked(self):
        links = set(re.findall(r"\[why\]\(docs/LESSONS\.md#([\w-]+)\)", read(CLAUDE)))
        sections = set()
        for ln in read(LESSONS).splitlines():
            if ln.startswith("### ") and not ln.startswith("### From "):
                sections.add(slug(ln[4:]))
        assert len(links) >= 50, len(links)
        assert links - anchors(LESSONS) == set(), links - anchors(LESSONS)
        assert sections - links == set(), ("a LESSONS section no rule links to",
                                           sections - links)


class TestEveryCitationResolves:
    def test_every_section_citation_names_a_file_and_section_that_exist(self):
        seen, bad = broken_citations(tracked_text_files())
        assert seen >= 60, seen                                           # the floor
        assert bad == [], bad

    def test_every_quote_of_claude_md_is_text_it_still_holds(self):
        seen, bad = stale_quotes(tracked_text_files(), read(CLAUDE))
        assert seen >= 3, seen
        assert bad == [], bad


class TestTheControls:
    def test_a_rule_with_no_enforcement_is_found(self):
        text = ("## Standing rules\n\n- **A planted rule** with nothing after it.\n"
                "- **A kept rule.** [not mechanised]\n\n## Next\n")
        assert unenforced(text) == ["- **A planted rule** with nothing after it."]

    def test_a_missing_path_is_found(self):
        _found, missing = missing_paths("[tests/test_does_not_exist.py; tests/test_claude_md.py]")
        assert missing == ["tests/test_does_not_exist.py"]

    def test_a_broken_section_citation_is_found(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "A.md").write_text("# Title\n\n## Real section\n\n```\n## not a heading\n```\n")
        (tmp_path / "docs" / "B.md").write_text(
            "see docs/A.md#real-section and docs/A.md#gone-section and docs/A.md#not-a-heading, "
            "[x](A.md#real-section), [y](#nowhere), docs/Missing.md#x\n")
        seen, bad = broken_citations(["docs/B.md"], root=str(tmp_path))
        assert seen == 6
        assert bad == ["docs/B.md: docs/A.md#gone-section", "docs/B.md: docs/A.md#not-a-heading",
                       "docs/B.md: docs/Missing.md#x", "docs/B.md: ](#nowhere)"], bad

    def test_a_quote_of_moved_text_is_found(self, tmp_path):
        (tmp_path / "x.md").write_text('as CLAUDE.md "A rule that moved out long ago" says, '
                                       'and CLAUDE.md "the gate stays here" too\n')
        seen, bad = stale_quotes(["x.md"], "- **The gate stays here.**", root=str(tmp_path))
        assert seen == 2 and len(bad) == 1 and "moved out" in bad[0]

    def test_the_slug_is_githubs(self):
        assert slug("9. Completion plan (after Part 1 submission, 2026-09-22)") == \
            "9-completion-plan-after-part-1-submission-2026-09-22"
        assert slug("How it starts {#start}") == "start"
        assert slug("Walk the path for real") == "walk-the-path-for-real"
