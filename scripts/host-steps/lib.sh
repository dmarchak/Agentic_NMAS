# Shared by the host-step scripts in this folder (sourced, never run).
#
# The operator runs these on the NMAS host, as their own user; host writes stay theirs. Each
# script declares its checks up front (`plan`), runs its steps, then its checks; it stops at the
# first step or check that fails, saying what it wanted and what it got, and always ends with a
# summary naming every planned check PASS, FAIL or NOT RUN.
#
#   step  "what it does"   'command'                  a failing command stops the script
#   check "name" MODE WANT 'command'                  MODE: eq | has | lacks | re | ge | rc0
#
# Commands are bash strings run with pipefail. A value in REDACT (a secret the script holds) is
# masked in anything printed.

set -uo pipefail

SCRIPT_NAME=$(basename "$0")
CHECKOUT=$(cd "$(dirname "$0")/../.." && pwd)
_PLAN=()
_PASSED=()
_FAILED=""
REDACT=""

_mask() {
    local text=$1
    if [ -n "$REDACT" ]; then
        text=${text//"$REDACT"/<redacted>}
    fi
    printf '%s' "$text"
}

plan() {
    _PLAN=("$@")
}

summary() {
    local n state any_fail=0
    echo
    echo "== SUMMARY: $SCRIPT_NAME"
    for n in "${_PLAN[@]}"; do
        state="NOT RUN"
        if printf '%s\n' "${_PASSED[@]+"${_PASSED[@]}"}" | grep -qxF -- "$n"; then
            state="PASS"
        elif [ "$n" = "$_FAILED" ]; then
            state="FAIL"
            any_fail=1
        fi
        printf '  %-8s %s\n' "$state" "$n"
    done
    if [ -n "$_FAILED" ] && [ "$any_fail" = 0 ]; then
        echo "  FAIL     $_FAILED"
    fi
    if [ -z "$_FAILED" ]; then
        echo "== RESULT: PASS (${#_PASSED[@]} of ${#_PLAN[@]} checks)"
    else
        echo "== RESULT: FAIL at: $_FAILED"
    fi
}

_stop() {
    _FAILED=$1
    # ON_FAIL: a script's undo, run when a step or check fails and before the summary (the
    # venv swap points the link back: section 8.3's rollback on failure). It prints its own
    # proof; the result stays FAIL, naming what failed.
    if [ -n "${ON_FAIL:-}" ]; then
        echo "== ON FAILURE: ${ON_FAIL_WHAT:-undo}"
        echo "   $ $(_mask "$ON_FAIL")"
        bash -o pipefail -c "$ON_FAIL" || echo "ON FAILURE: the undo itself failed (exit $?)"
    fi
    summary
    exit 1
}

step() {
    local what=$1 cmd=$2
    echo "== STEP: $what"
    echo "   $ $(_mask "$cmd")"
    if ! bash -o pipefail -c "$cmd"; then
        echo "STEP FAILED: $what"
        _stop "step: $what"
    fi
}

check() {
    local name=$1 mode=$2 want=$3 cmd=$4 got rc ok=0
    got=$(bash -o pipefail -c "$cmd" 2>&1)
    rc=$?
    case $mode in
        eq)    [ "$got" = "$want" ] && ok=1 ;;
        has)   printf '%s' "$got" | grep -qF -- "$want" && ok=1 ;;
        lacks) printf '%s' "$got" | grep -qF -- "$want" || ok=1 ;;
        re)    printf '%s' "$got" | grep -qE -- "$want" && ok=1 ;;
        ge)    [[ "$got" =~ ^[0-9]+$ ]] && [ "$got" -ge "$want" ] && ok=1 ;;
        rc0)   [ "$rc" = 0 ] && ok=1 ;;
        *)     echo "unknown check mode $mode"; _stop "$name" ;;
    esac
    if [ "$ok" = 1 ]; then
        echo "PASS  $name"
        _PASSED+=("$name")
    else
        echo "FAIL  $name"
        echo "      wanted ($mode): $(_mask "$want")"
        echo "      got (exit $rc): $(_mask "$(printf '%s' "$got" | head -c 600)")"
        _stop "$name"
    fi
}

not_root() {
    check "run as the operator's own user, not root" eq "no" '[ "$(id -u)" = 0 ] && echo yes || echo no'
}
