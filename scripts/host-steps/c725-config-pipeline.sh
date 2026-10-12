#!/usr/bin/env bash
# C725 (docs/OPEN_FINDINGS.md): the config repository's pipeline. Installs into a list's config
# repository, through Mercury's own commit path (`repo.commit`, under the repository lock, with
# `stage_exactly`) and its own push (`remote.push`), two files:
#   .github/workflows/nmas-config-check.yml   this checkout's deploy/config-repo/nmas-config-check.yml
#   .nsot/nmas-pin                            repository=<owner>/<name> and sha=<this checkout's HEAD>
# so every push touching golden/, host_vars/, templates/, profiles/ or dhcp/ runs, on GitHub,
# the check Mercury runs before it commits (scripts/nmas-config-check), from the release the
# host runs. Before installing, the check is run once over the repository as it stands
# (read-only, isolated from data/) and its result printed: a failure there is the first run's
# result too. Nothing else in the repository moves. Run on the NMAS host, as the operator's
# own user (LIST defaults to the current list):
#     LIST=<list name> bash <checkout>/scripts/host-steps/c725-config-pipeline.sh
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
export PYTHONDONTWRITEBYTECODE=1
ACTOR="${ACTOR:-$(id -un) (host shell, C725)}"
export DIR
DIR=$(mktemp -d)

LIST=${LIST:-$(cd "$CHECKOUT" && "$PY" -c 'from modules.config import get_current_list_name; print(get_current_list_name())')}
REPO=$(cd "$CHECKOUT" && "$PY" -c 'import os, sys; from modules.config import list_data_path; print(os.path.join(list_data_path(sys.argv[1]), "config_repo"))' "$LIST")
SHA=$(git -C "$CHECKOUT" rev-parse HEAD)
# owner/name from the checkout's origin (https://github.com/o/n(.git), or the ssh form
# [<user>@]<host>:o/n.git, the host an ssh alias too: the NMAS host's origin is one, measured
# 2026-10-12); the URL itself is never printed.
REPOSITORY=$(git -C "$CHECKOUT" remote get-url origin | sed -E 's#^(https://([^@/]*@)?github\.com/|([A-Za-z0-9_.-]+@)?[A-Za-z0-9_.-]+:)##; s#\.git$##')
printf 'repository=%s\nsha=%s\n' "$REPOSITORY" "$SHA" > "$DIR/nmas-pin"
echo "   list: $LIST; pin: $REPOSITORY at $SHA"

cat > "$DIR/install.py" <<'PY'
"""Write the workflow and the pin, commit exactly them through Mercury's commit path, push."""
import os
import shutil
import sys

checkout, list_name, repo, workflow, pin, actor = sys.argv[1:7]
sys.path.insert(0, checkout)
from modules import redact  # noqa: E402
from modules.nsot import remote, repo as R  # noqa: E402

FILES = {".github/workflows/nmas-config-check.yml": workflow, ".nsot/nmas-pin": pin}
with R.repo_lock(repo):
    for rel, src in FILES.items():
        os.makedirs(os.path.dirname(os.path.join(repo, rel)), exist_ok=True)
        shutil.copyfile(src, os.path.join(repo, rel))
    staged = R.stage_exactly(repo, list(FILES))
    _rc, status, _e = R.git(repo, "status", "--porcelain", "--", *FILES)
    if not status.strip():
        print("already installed: both files are committed as they are")
        sha = ""
    else:
        rc, sha, err = R.commit(repo, "pipeline: the config check on every push (C725)\n\n"
                                f"Actor: {actor}\nTool: c725-config-pipeline.sh\n"
                                "Source: pipeline\n", paths=staged, publish_now=False)
        if rc != 0:
            print("commit failed: " + redact.redact_text(err))
            sys.exit(1)
        print(f"committed {sha}")
got = remote.push(list_name, actor=actor, repo_dir=repo)
print("push: " + ("ok" if got.get("ok") else
                  "REFUSED: " + redact.redact_text(str(got.get("error")))[:400]))
sys.exit(0 if got.get("ok") else 1)
PY

plan "run as the operator's own user, not root" \
     "the list's config repository is a git repository with a commit" \
     "the pin names a public repository and a 40-hex commit" \
     "the pinned commit is on GitHub (public, no token)" \
     "the workflow is committed at HEAD as shipped" \
     "the pin is committed at HEAD" \
     "the config repository's working tree holds no change to either file"

not_root
check "the list's config repository is a git repository with a commit" rc0 "" \
    "git -C '$REPO' rev-parse --verify -q HEAD"
check "the pin names a public repository and a 40-hex commit" re \
    '^repository=[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+ sha=[0-9a-f]{40}$' "tr '\n' ' ' < '$DIR/nmas-pin' | sed 's/ \$//'"
check "the pinned commit is on GitHub (public, no token)" eq "200" \
    "curl -s -o /dev/null -w '%{http_code}' --max-time 20 'https://api.github.com/repos/$REPOSITORY/commits/$SHA'"

step "run the check over the repository as it stands (read-only; its result is printed, never a stop)" \
    "'$PY' '$CHECKOUT/scripts/nmas-config-check' '$REPO' --report '$DIR/report.json' | tail -12 || true"
step "install the workflow and the pin, commit them as $ACTOR, push" \
    "cd '$CHECKOUT' && '$PY' '$DIR/install.py' '$CHECKOUT' '$LIST' '$REPO' '$CHECKOUT/deploy/config-repo/nmas-config-check.yml' '$DIR/nmas-pin' '$ACTOR'"

check "the workflow is committed at HEAD as shipped" eq "$(git hash-object "$CHECKOUT/deploy/config-repo/nmas-config-check.yml")" \
    "git -C '$REPO' rev-parse HEAD:.github/workflows/nmas-config-check.yml"
check "the pin is committed at HEAD" eq "$(git hash-object "$DIR/nmas-pin")" \
    "git -C '$REPO' rev-parse HEAD:.nsot/nmas-pin"
check "the config repository's working tree holds no change to either file" eq "" \
    "git -C '$REPO' status --porcelain -- .github/workflows/nmas-config-check.yml .nsot/nmas-pin"
echo "   The first run starts with this push (the pin and the workflow are in its paths): the config repository's Actions tab, workflow nmas-config-check."
summary
