# A remote is optional: the audit

**The operator's decision, 2026-10-18** (docs/MERCURY_CHARTER.md, "The network's repository: on
the host; a remote is optional"):
- **The source of truth** for intent, configurations and templates is the network's git
  repository on the Mercury host.
- **A remote is optional.** It may be GitHub, Gitea or GitLab, or a kit's upstream Mercury. It
  is an off-host copy, never required.
- **Mercury works fully offline,** with no remote at all.
- **A GitHub-specific check runs only when a GitHub remote is configured.**

This audit lists every place in the product that requires a remote, assumes one, checks one
or nags about one. Each is marked **fine** or **must change**, with its file and line.

**Written 2026-10-19 (UTC) at 7f715f4d's code, docs only** (the operator: "Docs only before
the close"). Nothing here is fixed yet.
- **How it was made:** a read-only survey of app.py, modules/, routes/, templates/v2/, static/js/,
  scripts/ and deploy/. The search words were remote, ls-remote, publish, push, github,
  api.github, deploy key, visibility, private, origin, upstream, gitea, gitlab, "no repo",
  "not assigned" and remote_url.
- **How it was checked:** the agent re-read ten of its findings at their lines before writing
  them down. The other line numbers are the survey's, read from the code at that commit.
- **The builds that follow** are registered as post-Phase 7:
  - C1315: a remote's commits Mercury lacks, taken in as foreign changes.
  - C1320: durability, which replaces the "no remote" notice.

## What already holds

**A network with no remote and no `origin` works fully and is quiet.**
- It commits, deploys, shows History and records, all with no remote.
- No Needs attention row fires. `attention.remote_source` skips the `no_remote` state
  (`modules/attention.py:2717-2721`).
- Nothing is pushed: `archive.push_hook` answers ok, "no remote configured … nothing pushed"
  (`modules/nsot/archive.py:100-102`).

**"No repo assigned":** no notice with these words exists in the code. The nearest are:
- the reader's "no remote: the history is on this host only" (grey);
- History's "No repository yet: the network's first commit makes it", which is about a missing
  local repository, not a remote;
- the set-up card's "This network has no remote…".

Each is listed below.

## Must change

**Rule-breaking: the remote, or GitHub, is assumed.**

| # | Where | What it does | Why it must change |
|---|---|---|---|
| R1 | `modules/nsot/remote.py:372-414` (`check_private`, URLs at 389-391) | Asks `api.github.com/repos/<owner>/<repo>` and `github.com/<owner>/<repo>.git/info/refs`, whatever host the SSH alias reaches. | GitHub-only, run for every remote. For a Gitea or GitLab remote it asks GitHub about an unrelated name: a 404 passes as "private" when it may not be. With no outbound HTTPS it fails. **Run it only when the remote is GitHub**; otherwise say privacy was not asked. |
| R2 | `modules/nsot/remote.py:273-302` (`check_key_scope`) | Requires GitHub's `ssh -T` greeting, "Hi owner/repo!". | Gitea's greeting fails as "an account-wide key" (293-297), and GitLab's fails `key_authenticates` (287-291). `verify()` runs the rest only if this passes (612-618). GitHub-only: **run it only for a GitHub remote.** |
| R3 | `modules/nsot/remote.py:1201-1204` (`push`) | Refuses without `verified_at`. | `verified_at` needs R1 and R2, so Push now never works for a non-GitHub remote. **A verification must be one the remote's kind can pass.** |
| R4 | `modules/nsot/remote.py:1272-1283` (`enable_auto_push`) | Needs a `last_push` first, which needs R3. | Automatic pushing is unreachable for a non-GitHub remote (follows R3). |
| R5 | `modules/nsot/remote.py:163-174` (`SETUP_SHAPES`), `:243-244` (`remote_url`), `modules/remote_setup.py:60`, `templates/v2/_remote_setup.html:31-40` | Owner and repository follow GitHub's naming rules; the URL is only `alias:owner/repo`. | Refuses GitLab subgroups, and Gitea owners with "_" or ".". No https form, no port. **The shape must come from the remote's kind.** |
| R6 | `modules/nsot/remote.py:224` (`_adopt_locked`) | `"provider": "github"` is hard-coded. Nothing asks for it and nothing reads it. | The one field that could gate R1 and R2 is a constant. **Ask for it, or measure it, and gate the GitHub checks on it.** |
| R7 | `modules/nsot/remote.py:359-362` (`check_write_probe`) | Its fix text and comment name GitHub ("Enable 'Allow write access'", "GitHub's own gc"). | Wording only: name the remote's own setting, or say it generically. |
| R8 | `modules/readers/remote_publication.py:116-117` (`_judge_heads`) | Asks `origin` if one exists, even with no `remote.json`. | A bare `origin` added by hand gets publication states and rows. The push hook pushes nothing there (`archive.py:100-102`), Push now refuses (409), and the row cannot be acknowledged (R10), so **the row never clears.** Mercury's own record should decide whether a remote is configured. |
| R9 | `modules/readers/remote_publication.py:284-288` (`_describe`, state `ahead`) | Turns danger 600 s after an unpushed commit, "auto-push has not sent it". | It never asks whether automatic pushing is on. With it deliberately off, every commit turns red after 10 minutes: **a nag against a chosen setting.** |
| R10 | `modules/attention.py:135-136`, `:245-247` (row kind and clears), `:2691-2782` (`remote_source`) | The publication row clears only by resolving. Its remote-ahead or diverged action is "Resolve it by hand on the host". | A terminal step, against "No terminal steps". A remote's commits Mercury lacks hold its own pushes until a person acts on the host. **C1315, post-Phase 7:** foreign changes reviewed through preview and confirm; Mercury's own pushes never held. |
| R11 | `modules/integrations/nsot_git.py:82-86`, shown at `modules/attention.py:1847-1856` | A failed push becomes "NSoT git repo is not answering", a danger row. Its action points at "Settings › Default, the NSoT git repo card". | A failed push is not an outage of the repository on the host, which is the source of truth and is answering. The card it names does not exist (`settings_scope.py:138-142`, `installation_settings.py:346-353`). **Report it as the remote's push failure, with an action that exists.** |
| R12 | `templates/v2/_history_remote.html:5-7` | Draws the grey badge "no remote" for every grey state, `not_read` included. | A configured remote reads "no remote" until its first read. That is a wrong thing looking right: **say "not read yet."** |
| R13 | `templates/v2/_history_remote.html:19-32` | Draws Verify the remote and Push now for every state but `no_remote` and `not_read`. | With a bare `origin` (R8) both are drawn, and both fail "has no remote configured". |
| R14 | (absent) | No statement of durability. | A list with no remote says "the history is on this host only", but not whether another copy exists, such as the VM's backup, or how old it is. **C1320, post-Phase 7:** say whether an off-host copy exists and its age; a single copy, chosen, is not an error. |

## Fine

**Works with no remote, quietly, or is a person's own choice.**

| Where | What it does |
|---|---|
| `modules/nsot/remote.py:71-93` (`load_remote`) | No record: `None`, quietly. A damaged record raises, which is right: it is unreadable, not absent. |
| `modules/nsot/remote.py:1286-1312` (`auto_push_decision`) | No remote: `push: False`, "no remote configured", used quietly. |
| `modules/nsot/archive.py:22-55`, `:58-106`, `:283-312` | The push hook and the publication hook run after every commit and do nothing without a remote. They never fall back to the dead global `nsot_git_remote_url` (79-90). |
| `modules/nsot/archive.py:135-137`, `:160`, `:188` | With a remote record: sets `origin` only if absent, and pushes to `origin`. *Note:* it never checks that `origin` matches the record, so with R8 the two can disagree. This waits for the R8 fix. |
| `modules/nsot/hooks.py:43-204`, `modules/nsot/repo.py:1485-1549`, `app.py:247-253` | Every commit is handed to the hooks. Nothing needs a remote. `_report_empty_registry` is quiet with no remote (`hooks.py:86-87`). |
| `modules/readers/remote_publication.py:118-123`, `:173-188`, `:250-252` | No remote: state `no_remote`, "no remote: the history is on this host only", grey. A list with no repository is skipped. |
| `modules/nsot/remote.py:124-148`, `:580-646`, `:875-1071`, `:1220-1269`; `modules/remote_setup.py:81-159`; `routes/remote.py:41-79`; `routes/remote_v2.py:38-116` | The remote's own actions (Connect, Verify, Push now, acknowledge, auto-push). Each needs a remote, and each is reached only from History's Remote set-up, which a person opens by choice. Fine once R1 to R7 are fixed. |
| `templates/v2/_remote_setup.html:26-27`, `templates/v2/_history_remote.html:18` | "Set up the remote…": a quiet invitation, never a row. *Note:* "deploy key" is GitHub's word (Gitea and GitLab use it too). |
| `templates/v2/_history_remote.html:12` | "No repository yet: the network's first commit makes it": about the local repository, not a remote. |
| `templates/v2/_network_delete.html:18`, `modules/network_admin.py:108-110` | A network's removal says the remote keeps its copy, only when there is one. |
| `modules/settings_schema.py:253-261`, `modules/settings_scope.py:113-116` | `nsot_git_*` keys: declared DEAD except the author name and email. Nothing reads a remote from settings. |
| `modules/settings_schema.py:305-308`, `:329` | `require_identity_for_publish_remote`, `require_person_for_publish_remote`: gates on a person's push, not a requirement for a remote. |
| `modules/nsot/config_check.py:1-12`, `scripts/nmas-config-check:9,20` | GitHub named in docstrings only; the check runs locally. |
| `scripts/host-steps/c725-config-pipeline.sh`, `deploy/config-repo/nmas-config-check.yml` | A GitHub Actions check for a config repository: an operator's own optional host step, never registered as owed (`modules/host_steps.py` has no c725), so nothing nags. GitHub-only by nature; a Gitea or GitLab twin would be its own optional step. |

## Wording only (manual and comments)

- **docs/manual/how-it-works/publish-remote.md:**
  - 19-24: "an owner and a repository follow GitHub's rules".
  - 32: a deploy key's write access.
  - 120-141: Verify, including privacy.
  - These follow R1, R2 and R5. **Must change with them.**
- **docs/manual/screens/history.md:** 19-20. Follows R12.
- **`modules/breakglass.py:18-20`:** a comment, "`config_repo` is pushed to a private GitHub
  remote". **Must change:** a remote is optional.
- **`modules/attention.py:2449`:** the heading "history committed and not on its remote (C223)"
  sits over `pushed_source`, which is the app's own repository. Mislabelled; **must change**
  (wording).

## Not a network's repository (out of scope)

The app's own release repository and its CI are GitHub by the project's choice, not a network's
remote:
- `modules/readers/app_pushed.py:50, 268`;
- `modules/attention.py:1875, 1923, 2593-2688`;
- `modules/readers/ci_verdict.py`;
- `templates/v2/_attention.html:86-87`, `_update.html`, `_installation.html`;
- `routes/update.py:144`, `modules/update_op.py`;
- `deploy/update/nmas-update:364`;
- `scripts/nmas-deploy:265-290, 410`, and the developer tools `scripts/nmas-ci-dispatch` and
  `scripts/nmas-ci-log`.

An installation that updates from elsewhere is Stage 10's concern (the release), not this
audit's.

## Where each goes

- **R10 and the foreign-changes half of R8:** C1315, post-Phase 7, with the edge kit's offline
  sync.
- **R14, and R9's nag replaced by a stated fact:** C1320, post-Phase 7.
- **R1 to R7, R11 to R13 and the wording:** C1321, post-Phase 7, "a remote of any kind":
  GitHub's checks gated on a GitHub remote, the remote's kind recorded, the publication states
  taken only from Mercury's own record.
