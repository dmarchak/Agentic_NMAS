"""Nothing personal or installation-specific is published (2026-09-29).

The repository is public. The documentation pass replaced the operator's
email, the user name and home paths, the homelab's LAN addresses, the tunnel
domain, the config repository's name, credential digests and chassis serials
with placeholders (`<operator>`, `<user>`, `<home>`, `<nmas-host>`,
`<lab-host>`, `<hypervisor>`, `<tunnel-host>`, `<laptop>`, `<LAN>`,
`<domain>`, `<repo>`, `<account>`, `[Author]`, `<redacted>`). This keeps them
out of what is written next.

The population is every tracked file under `docs/`, plus `CLAUDE.md` and
`README.md`. The rules are:

- **an email address**, except a documentation domain (`example.com`,
  `.example`, `.invalid`, `.test`);
- **a home directory** (`/home/<name>`, `C:/Users/<name>`), except a service
  account's (`/home/nmas`, the install example), which names no person;
- **an address in the homelab's `10.0.0.0/24`**. vrnetlab's internal
  addresses share that /24 (`10.0.0.15`, `.2`, `.3`, the same inside every
  container), so quoted device output would match. That is handled by a
  PER-LINE exemption keyed on the line's content hash with its reason, never
  by narrowing the pattern. An edited line loses its exemption and is read
  again, and an exemption whose line is gone fails (no ghosts);
- **a local denylist**, `data/publication_denylist.txt`, which is gitignored
  (so the terms themselves are not published). It holds the name, the user
  name, the domain and the redacted digests. Where the file is absent (CI, a
  fresh clone), that one rule SKIPS and says so, because an absent list
  checks nothing and must not read as clean.

An exemption covers the address rule only. The email, home and denylist rules
still run on an exempt line.
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

VRNETLAB = "vrnetlab's internal address, the same inside every container: quoted device or NetBox output, not the homelab"
# (path, sha256 of the stripped line [:12]) -> why the address on it is not the homelab's.
ADDRESS_EXEMPT = {
    ("docs/NSOT_WRITEUP.md", "65d73a3b391d"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "6ddf6399503e"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "83d4b9123c9f"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "25715794b34e"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "453247b4e56d"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "691ae00f5397"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "e65637a37ac0"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "c197b94492e2"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "3fe23aaf744c"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "5e27570dfa0f"): VRNETLAB,
    ("docs/NSOT_WRITEUP_NOTES.md", "90a9938fc540"): VRNETLAB,
    ("docs/OPEN_FINDINGS.md", "d61da30d6e24"): "the suite's fixture address, quoted from the app log",
    ("docs/OPEN_FINDINGS.md", "22925f26679b"): "the suite's fixture address, quoted from the app log",
    ("docs/OPEN_FINDINGS.md", "07623b5e97d7"): "a static route in r3's and r4's configs (10.0.0.0/8 to Null0)",
    ("docs/OPEN_FINDINGS.md", "27d3c4ac05f6"): VRNETLAB,
    ("docs/P6_ZTP_PROBE.md", "3b43d8de0cb6"): VRNETLAB + " (10.0.0.2 is its qemu gateway)",
    ("docs/P6_ZTP_PROBE.md", "2f31694af734"): "vrnetlab's qemu DHCP resolver, inside the container",
    ("docs/PHASE2_DHCP.md", "1dc599275d51"): VRNETLAB,
    ("docs/PHASE2_DHCP.md", "eeb1506b2887"): VRNETLAB,
    ("docs/R6_PHASE1.md", "2677c75621ed"): VRNETLAB,
    ("CLAUDE.md", "a126bf59a559"): VRNETLAB,
    ("CLAUDE.md", "41fddedeca84"): VRNETLAB,
    ("CLAUDE.md", "78d35b5cb4c8"): VRNETLAB,
    ("CLAUDE.md", "d70a0a321f4c"): VRNETLAB,
}


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


def scan(path: str, text: str, *, exempt=ADDRESS_EXEMPT, denylist=None):
    """Findings in one file: (path, line number, rule, what). Pure."""
    terms = [(t, _term_pattern(t)) for t in (denylist or [])]
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in EMAIL.finditer(line):
            if not DOC_DOMAINS.search(m.group(1)):
                found.append((path, n, "email", m.group(0)))
        for m in HOME.finditer(line):
            who = m.group(1) or m.group(2)
            if who not in SERVICE_HOMES:
                found.append((path, n, "home directory", m.group(0)))
        if LAN.search(line) and (path, line_key(line)) not in exempt:
            found.append((path, n, "homelab address (no exemption for this line: "
                          f"{line_key(line)})", ", ".join(sorted(set(LAN.findall(line))))))
        for term, rx in terms:
            if rx.search(line):
                found.append((path, n, "local denylist", term))
    return found


def published_files():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "docs", "CLAUDE.md", "README.md"],
                         capture_output=True, text=True, check=True).stdout.split()
    texts = {}
    for rel in out:
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                texts[rel] = fh.read()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
    return texts


@pytest.fixture(scope="module")
def files():
    texts = published_files()
    # The floor: 59 text files on 2026-09-29. A scan of nothing passes everything.
    assert len(texts) >= 50 and "CLAUDE.md" in texts and "docs/NSOT_WRITEUP.md" in texts
    return texts


class TestThePublishedFiles:
    def test_no_email_home_or_homelab_address(self, files):
        found = [f for p, t in files.items() for f in scan(p, t)]
        assert not found, "\n".join(f"{p}:{n}: {rule}: {what}" for p, n, rule, what in found)

    def test_no_term_on_the_local_denylist(self, files):
        terms = load_denylist()
        if terms is None:
            pytest.skip(f"{DENYLIST} is absent on this machine (it is local by design), "
                        "so the denylist rule checked NOTHING here; the other rules ran")
        assert len(terms) >= 5, "a denylist this short is not the one written 2026-09-29"
        found = [f for p, t in files.items() for f in scan(p, t, denylist=terms)
                 if f[2] == "local denylist"]
        assert not found, "\n".join(f"{p}:{n}: denylisted term {w!r}" for p, n, _, w in found)

    def test_every_exemption_names_a_line_that_exists(self, files):
        present = {(p, line_key(l)) for p, t in files.items() for l in t.splitlines()}
        ghosts = sorted(set(ADDRESS_EXEMPT) - present)
        assert not ghosts, f"exemptions whose line is gone or was edited (re-read it): {ghosts}"

    def test_the_local_files_are_not_tracked(self):
        for path in (DENYLIST, LAB_HOSTS):
            rc = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", path]).returncode
            assert rc == 0, f"{path} is not gitignored: committing it would publish it"


class TestTheScanCanFail:
    """Controls: each rule is shown finding a planted case, and not finding
    the forms it deliberately allows."""

    def test_a_planted_email_is_found(self):
        (f,) = scan("docs/x.md", "Actor: someone.real@mail-provider.net")
        assert f[2] == "email" and f[3] == "someone.real@mail-provider.net"

    def test_a_documentation_email_is_not(self):
        assert scan("docs/x.md", "forged@example.com and a@b.invalid") == []

    def test_a_home_directory_is_found_and_a_placeholder_or_service_home_is_not(self):
        assert [f[3] for f in scan("docs/x.md", "cd /home/alice/labs")] == ["/home/alice"]
        assert [f[2] for f in scan("docs/x.md", r"C:\Users\alice\x")] == ["home directory"]
        assert scan("docs/x.md", "cd <home>/labs; /home/<user>; /home/nmas/app") == []

    def test_a_homelab_address_is_found_unless_its_line_is_exempt(self):
        line = "ip address 10.0.0.15 255.255.255.0"
        assert [f[3] for f in scan("docs/x.md", line, exempt={})] == ["10.0.0.15"]
        assert scan("docs/x.md", line, exempt={("docs/x.md", line_key(line)): "why"}) == []

    def test_an_exemption_covers_one_line_in_one_file_only(self):
        line = "ip address 10.0.0.15 255.255.255.0"
        ex = {("docs/x.md", line_key(line)): "why"}
        assert scan("docs/y.md", line, exempt=ex), "another file is not exempt"
        assert scan("docs/x.md", line + " edited", exempt=ex), "an edited line is read again"

    def test_an_exemption_covers_the_address_rule_only(self):
        line = "10.0.0.15 seen by someone.real@mail-provider.net"
        ex = {("docs/x.md", line_key(line)): "why"}
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
