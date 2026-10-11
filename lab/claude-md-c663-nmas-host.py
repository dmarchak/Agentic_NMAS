#!/usr/bin/env python3
"""CLAUDE.md lines the agent may not write (a hook refuses its edits), for the operator to apply,
on the laptop, from the checkout:

    python3 lab/claude-md-c663-nmas-host.py

Five lines change, and nothing else:
- C663's last entry: three lines name the access helper's new home, `lab/nmas-host` (each
  `scripts/nmas-host` becomes `lab/nmas-host`);
- the prose rule names the second hook that enforces it (2026-10-11, the operator's (c)):
  `scripts/hooks/claude-no-shell-prose-edits`, beside the heredoc hook.
Each line is found by its own text AND the lines around it (the anchor), and the script
refuses, changing nothing: when any anchor is not found exactly once (CLAUDE.md moved since
2026-10-11: say so), or when a new line is already there (run twice, or pasted by hand). On
success it writes CLAUDE.md once, then shows `git diff -- CLAUDE.md`. Exit 0 written, 1 refused.
Then tell the agent to commit; it moves the helper, its hooks' and the lab sync's references
and its tests in that commit.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "CLAUDE.md")

#: (the line before, the line, the line after, the new line) as CLAUDE.md held them on
#: 2026-10-11 (lines 68 to 70, 114 to 117, 401 to 403, 412 to 414).
CHANGES = (
    ("  Every operation gets a real run on the host; watch what else moves. [not mechanised] "
     "[why](docs/LESSONS.md#walk-the-path-for-real)",
     "- **Read-only measurement of lab services is the agent's to run**, through "
     "`scripts/nmas-host`,",
     "  printing counts and names, never values. Writes, devices, Proxmox and the lab host are "
     "the",
     "- **Read-only measurement of lab services is the agent's to run**, through "
     "`lab/nmas-host`,"),
    (None,
     "- **Prose goes through the Edit and Write tools, never a heredoc into an interpreter.**",
     "  [hook: scripts/hooks/claude-no-heredoc-interpreter (.claude/settings.json); "
     "tests/test_claude_heredoc_hook.py] [why](docs/LESSONS.md#text-through-file-tools)",
     "- **Prose goes through the Edit and Write tools, never a heredoc into an interpreter and "
     "never an in-place shell edit.**"),
    ("- **Prose goes through the Edit and Write tools, never a heredoc into an interpreter.**",
     "  [hook: scripts/hooks/claude-no-heredoc-interpreter (.claude/settings.json); "
     "tests/test_claude_heredoc_hook.py] [why](docs/LESSONS.md#text-through-file-tools)",
     "- **CLAUDE.md is the operator's: a change it needs is given to the operator as the exact",
     "  [hooks: scripts/hooks/claude-no-heredoc-interpreter and "
     "scripts/hooks/claude-no-shell-prose-edits (.claude/settings.json); "
     "tests/test_claude_heredoc_hook.py, tests/test_claude_prose_edit_hook.py] "
     "[why](docs/LESSONS.md#text-through-file-tools)"),
    ("local file (`data/` is gitignored), because the repository is public",
     "(2026-09-29). `scripts/nmas-host` reads it and refuses, naming the file, when it is",
     "absent (exit 78); `nmas-host <host> --field <user|lan|tunnel>` prints one value,",
     "(2026-09-29). `lab/nmas-host` reads it and refuses, naming the file, when it is"),
    ("- **One helper makes the choice, and every host read goes through it:",
     "  `scripts/nmas-host <nmas|clab|pve> -- <command>`.** For scp and rsync,",
     "  `--target` prints `user@address`. It tries a TCP connect to the LAN",
     "  `lab/nmas-host <nmas|clab|pve> -- <command>`.** For scp and rsync,"),
)


def main() -> int:
    with open(PATH, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    problems, at = [], []
    for before, line, after, new in CHANGES:
        if new in lines:
            problems.append(f"already there (refusing a duplicate): {new.strip()}")
            continue
        hits = [n for n in range(1, len(lines) - 1)
                if lines[n] == line and (before is None or lines[n - 1] == before)
                and lines[n + 1] == after]
        if len(hits) != 1:
            problems.append(f"anchor found {len(hits)} times, expected once: {line.strip()}")
            continue
        at.append((hits[0], new))
    if problems:
        print("REFUSED, CLAUDE.md not changed:")
        for p in problems:
            print("  -", p)
        return 1
    for n, new in at:
        lines[n] = new
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"written: {len(at)} lines of CLAUDE.md ({', '.join(str(n + 1) for n, _ in at)})")
    subprocess.run(["git", "-C", ROOT, "--no-pager", "diff", "--", "CLAUDE.md"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
