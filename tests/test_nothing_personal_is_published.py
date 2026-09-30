"""Nothing personal or installation-specific is published (2026-09-29).

The repository is public, and the operator decided it stays public with its
history unrewritten, so this check is the only thing between a future commit
and the public record. The population is EVERY tracked text file: the docs,
CLAUDE.md and README, and the program, its scripts, deploy templates, tests
and fixtures (the operator: "so none of these can drift back").

The rules:

- **an email address**, except a documentation domain (`example.com`,
  `.example`, `.invalid`, `.test`);
- **a home directory** (`/home/<name>`, `C:/Users/<name>`), except a service
  account's (`/home/nmas`, the install example);
- **an address in the homelab's /24**;
- **a local denylist**, `data/publication_denylist.txt` (gitignored, so the
  terms are not themselves published): the name, the user name, the domain,
  the config repository's name and the redacted digests. Where the file is
  absent (CI, a fresh clone), that rule SKIPS and says so: an absent list
  checks nothing and must not read as clean.

vrnetlab's internal addresses share the homelab's /24 (the same inside every
container), so captured device output matches the address rule. That, and
every other excused line, is `tests/publication_exemptions.py`: ONE LINE per
entry, keyed on its content hash, with its reason and the rules it is excused
from. The pattern is never narrowed; an edited line is read again; an entry
whose line is gone fails (no ghosts).
"""

import hashlib
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENYLIST = os.path.join(ROOT, "data", "publication_denylist.txt")
LAB_HOSTS = os.path.join(ROOT, "data", "lab_hosts.json")

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
DOC_DOMAINS = re.compile(r"(^|\.)(example\.(com|org|net)|example|invalid|test)$", re.I)
HOME = re.compile(r"/home/(?!<)([A-Za-z_][\w.-]*)|[A-Za-z]:[\\/]+Users[\\/]+([^\\/<\s`'\"]+)")
SERVICE_HOMES = {"nmas"}
LAN = re.compile(r"\b10\.0\.0\.\d{1,3}(?:/\d{1,2})?\b")

#: The rule names an exemption can excuse.
RULES = ("email", "home", "address", "denylist")


def line_key(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()[:12]


def load_denylist(path: str = DENYLIST):
    """The terms, or None when the local file is absent."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return [t.strip() for t in fh if t.strip() and not t.lstrip().startswith("#")]


def _term_pattern(term: str):
    body = re.escape(term)
    if term[0].isalnum():
        body = r"(?<![A-Za-z0-9])" + body
    if term[-1].isalnum():
        body = body + r"(?![A-Za-z0-9])"
    return re.compile(body, re.I)


def _excused(exempt, path, line, rule):
    entry = exempt.get((path, line_key(line)))
    return entry is not None and rule in entry[1]


def scan(path: str, text: str, *, exempt=None, denylist=None):
    """Findings in one file: (path, line number, rule, what). Pure.
    *exempt* maps (path, line hash) -> (reason, rules excused)."""
    exempt = {} if exempt is None else exempt
    terms = [(t, _term_pattern(t)) for t in (denylist or [])]
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        if not _excused(exempt, path, line, "email"):
            for m in EMAIL.finditer(line):
                if not DOC_DOMAINS.search(m.group(1)):
                    found.append((path, n, "email", m.group(0)))
        if not _excused(exempt, path, line, "home"):
            for m in HOME.finditer(line):
                if (m.group(1) or m.group(2)) not in SERVICE_HOMES:
                    found.append((path, n, "home directory", m.group(0)))
        if LAN.search(line) and not _excused(exempt, path, line, "address"):
            found.append((path, n, "homelab address (no exemption for this line: "
                          f"{line_key(line)}; use a documentation address such as "
                          "192.0.2.x, or exempt the line with its reason)",
                          ", ".join(sorted(set(LAN.findall(line))))))
        if not _excused(exempt, path, line, "denylist"):
            for term, rx in terms:
                if rx.search(line):
                    found.append((path, n, "local denylist", term))
    return found


def published_files(root: str = ROOT):
    """Every file that IS or WILL BE published: tracked, staged, and untracked
    but not ignored. "Tracked" alone stood in for "about to be published", and
    a file created in the commit being tested is exactly where they differ: CI
    run #199 failed on `publication_exemptions.py`, new in cdebad8, which the
    local suite never read because it ran before `git add` (2026-09-29)."""
    out = subprocess.run(["git", "-C", root, "ls-files", "--cached", "--others",
                          "--exclude-standard"], capture_output=True, text=True,
                         check=True).stdout.split()
    texts = {}
    for rel in dict.fromkeys(out):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                texts[rel] = fh.read()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
    return texts


@pytest.fixture(scope="module")
def files():
    texts = published_files()
    # The floor: every tracked text file, over 700 on 2026-09-29, from every
    # tree the operator named. A scan of a subset passes what it did not read.
    assert len(texts) >= 600
    for must in ("CLAUDE.md", "docs/NSOT_WRITEUP.md", "tests/fixtures/configs/fleet/r1.cfg",
                 "deploy/systemd/nmas-startup-check.service", "scripts/nmas-host", "app.py"):
        assert must in texts, must
    return texts


@pytest.fixture(scope="module")
def exempt():
    from tests.publication_exemptions import EXEMPT, REASONS

    assert all(reason in REASONS and rules and set(rules) <= set(RULES)
               for reason, rules in EXEMPT.values()), "an entry with no reason or no rule"
    return EXEMPT


class TestThePublishedFiles:
    def test_no_email_home_or_homelab_address(self, files, exempt):
        found = [f for p, t in files.items() for f in scan(p, t, exempt=exempt)]
        assert not found, "\n".join(f"{p}:{n}: {rule}: {what}" for p, n, rule, what in found)

    def test_no_term_on_the_local_denylist(self, files, exempt):
        terms = load_denylist()
        if terms is None:
            pytest.skip(f"{DENYLIST} is absent on this machine (it is local by design), "
                        "so the denylist rule checked NOTHING here; the other rules ran")
        assert len(terms) >= 5, "a denylist this short is not the one written 2026-09-29"
        found = [f for p, t in files.items() for f in scan(p, t, exempt=exempt, denylist=terms)
                 if f[2] == "local denylist"]
        assert not found, "\n".join(f"{p}:{n}: denylisted term {w!r}" for p, n, _, w in found)

    def test_every_exemption_names_a_line_that_exists(self, files, exempt):
        present = {(p, line_key(l)) for p, t in files.items() for l in t.splitlines()}
        ghosts = sorted(set(exempt) - present)
        assert not ghosts, f"exemptions whose line is gone or was edited (re-read it): {ghosts}"

    def test_the_local_files_are_not_tracked(self):
        for path in (DENYLIST, LAB_HOSTS, os.path.join(ROOT, ".claude", "settings.local.json")):
            rc = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", path]).returncode
            assert rc == 0, f"{path} is not gitignored: committing it would publish it"

    def test_no_real_host_address_is_exempted(self, files, exempt):
        """An exemption is for what is NOT the homelab; the hosts' real
        addresses, when the local file names them, are never excused."""
        import json
        if not os.path.exists(LAB_HOSTS):
            pytest.skip(f"{LAB_HOSTS} is absent on this machine; nothing to compare")
        with open(LAB_HOSTS, encoding="utf-8") as fh:
            real = {e["lan"] for k, e in json.load(fh).items() if not k.startswith("_")}
        excused = [(p, n) for p, t in files.items()
                   for n, l in enumerate(t.splitlines(), 1)
                   if (p, line_key(l)) in exempt
                   and any(re.search(rf"\b{re.escape(a)}\b", l) for a in real)]
        assert not excused, excused


class TestThePopulationIsWhatWillBePublished:
    """The control for the population itself, in a repository of its own."""

    def test_an_untracked_file_is_read_and_an_ignored_one_is_not(self, tmp_path):
        repo = str(tmp_path)
        run = lambda *a: subprocess.run(["git", "-C", repo, *a], check=True,  # noqa: E731
                                        capture_output=True)
        run("init", "-q")
        (tmp_path / "clean.md").write_text("nothing personal\n")
        (tmp_path / ".gitignore").write_text("local.txt\n")
        run("add", "clean.md", ".gitignore")
        planted = "Actor: " + "someone.real" + "@mail-provider.net\n"
        (tmp_path / "new_in_this_commit.md").write_text(planted)     # untracked
        (tmp_path / "staged.md").write_text(planted)
        run("add", "staged.md")                                         # staged, uncommitted
        (tmp_path / "local.txt").write_text(planted)                   # ignored: never published
        texts = published_files(repo)
        assert {"clean.md", "new_in_this_commit.md", "staged.md"} <= set(texts)
        assert "local.txt" not in texts
        found = {p for p, t in texts.items() for f in scan(p, t) if f[2] == "email"}
        assert found == {"new_in_this_commit.md", "staged.md"}


class TestTheScanCanFail:
    """Controls: each rule is shown finding a planted case, and not finding
    the forms it deliberately allows."""

    PLANTED_EMAIL = "someone.real" + "@mail-provider.net"
    PLANTED_ADDRESS = "10.0.0" + ".15"

    def test_a_planted_email_is_found(self):
        (f,) = scan("docs/x.md", "Actor: " + self.PLANTED_EMAIL)
        assert f[2] == "email" and f[3] == self.PLANTED_EMAIL

    def test_a_documentation_email_is_not(self):
        assert scan("docs/x.md", "forged@example.com and a@b.invalid") == []

    def test_a_home_directory_is_found_and_a_placeholder_or_service_home_is_not(self):
        who = "ali" + "ce"
        assert [f[3] for f in scan("docs/x.md", f"cd /home/{who}/labs")] == [f"/home/{who}"]
        assert [f[2] for f in scan("docs/x.md", "C:\\Users\\" + who + "\\x")] == ["home directory"]
        assert scan("docs/x.md", "cd <home>/labs; /home/<user>; /home/nmas/app") == []

    def test_a_homelab_address_is_found_unless_its_line_is_exempt(self):
        line = f"ip address {self.PLANTED_ADDRESS} 255.255.255.0"
        assert [f[3] for f in scan("docs/x.md", line)] == [self.PLANTED_ADDRESS]
        ex = {("docs/x.md", line_key(line)): ("VRNETLAB", ("address",))}
        assert scan("docs/x.md", line, exempt=ex) == []

    def test_an_exemption_covers_one_line_in_one_file_only(self):
        line = f"ip address {self.PLANTED_ADDRESS} 255.255.255.0"
        ex = {("docs/x.md", line_key(line)): ("VRNETLAB", ("address",))}
        assert scan("docs/y.md", line, exempt=ex), "another file is not exempt"
        assert scan("docs/x.md", line + " edited", exempt=ex), "an edited line is read again"

    def test_an_exemption_covers_only_the_rules_it_names(self):
        line = f"{self.PLANTED_ADDRESS} seen by {self.PLANTED_EMAIL}"
        ex = {("docs/x.md", line_key(line)): ("VRNETLAB", ("address",))}
        assert [f[2] for f in scan("docs/x.md", line, exempt=ex)] == ["email"]

    def test_a_denylisted_term_is_found_as_a_word(self, tmp_path):
        path = tmp_path / "deny.txt"
        path.write_text("# comment\nJaneRoe\nsecret-host.example\n")
        terms = load_denylist(str(path))
        assert terms == ["JaneRoe", "secret-host.example"]
        hits = scan("docs/x.md", "by janeroe on secret-host.example", denylist=terms)
        assert sorted(f[3] for f in hits) == ["JaneRoe", "secret-host.example"]
        assert scan("docs/x.md", "JaneRoesmith", denylist=terms) == [], "whole words only"

    def test_an_absent_denylist_is_none_never_empty(self, tmp_path):
        assert load_denylist(str(tmp_path / "absent.txt")) is None
