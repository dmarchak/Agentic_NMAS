#!/usr/bin/env bash
# C788 (the operator, 2026-10-14: rotate now, and move the secret out of the URL). Loki's
# storage URL carried MinIO's loki-writer key inline (`s3: http://<user>:<secret>@<host>/loki`
# in /etc/loki/local-config.yaml), and a survey printed it once. The operator's, on the NMAS
# host, as their own user (sudo asked once), outside 08:30 to 09:10 UTC:
#     bash <checkout>/scripts/host-steps/c788-loki-writer-rotate.sh
#
#   1. a dated copy of Loki's configuration and the container's definition, with this step's
#      helper beside them (/var/backups/loki/writer-rotate-<stamp>, root's, mode 700);
#   2. MinIO's root password asked, hidden (the root user read from /etc/default/minio);
#   3. loki-writer's policy kept to the loki bucket alone (C584's loki-only, the same JSON);
#   4. a NEW secret generated here (never typed, never printed, never on a command line);
#   5. Loki's storage block rewritten: `endpoint`, `bucketnames`, and `access_key_id` and
#      `secret_access_key` read from the environment (`${...}`, `-config.expand-env=true`), the
#      keys in /etc/loki/loki-s3.env (root's, mode 600); no credential in any URL; Loki itself
#      verifies the result before anything changes;
#   6. the new secret set on loki-writer, then the container recreated as it is measured today
#      (2026-10-15: plain `docker run`, no compose) plus `--env-file` and `-config.expand-env`.
# A failure from 6 on puts everything back before the summary (ON_FAIL): the old secret on
# loki-writer, the copied configuration, no env file, the container as it was. By hand later:
#     bash <checkout>/scripts/host-steps/c788-loki-writer-undo.sh /var/backups/loki/writer-rotate-<stamp>
#
# Where the key lives afterwards: the env file (root's) and the container's environment, which
# `docker inspect loki` shows to root and the docker group, as any container variable is. The
# dated copy keeps the OLD key (root's, mode 700) for the undo; it is refused by MinIO once this
# passes. The old key is read only by keys.py, from the copy, and never printed.
. "$(dirname "$0")/lib.sh"

PY=${NMAS_PY:-/opt/mercury-venv/bin/python}
CONFIG=/etc/loki/local-config.yaml
ENVFILE=/etc/loki/loki-s3.env
MINIO_ENV=/etc/default/minio
IMAGE=grafana/loki:3.3.2
COPY=/var/backups/loki/writer-rotate-$(date -u +%Y%m%dT%H%M%SZ)
DIR=$(mktemp -d)
chmod 700 "$DIR"
LOG="$DIR/out.log"
TRACE_PID=""
trap '[ -n "$TRACE_PID" ] && kill "$TRACE_PID" 2>/dev/null; rm -rf "$DIR"' EXIT
# Everything printed is kept, so the last check can read this run's whole output for a secret.
exec > >(tee -a "$LOG") 2>&1
export PY CONFIG ENVFILE MINIO_ENV IMAGE COPY DIR LOG

cat > "$DIR/keys.py" <<'PY'
"""C788's helper: what the step needs from the old storage URL and the new key, printing only
what it is asked. The OLD key is read from the dated copy, the NEW one from standard input;
neither is ever printed (old-to-mc writes the old one to mc's standard input, in the undo).

    keys.py endpoint|bucket|user COPY      the old URL's host:port, bucket, or user
    keys.py old-to-mc COPY                 "<user>\\n<old secret>\\n", for mc's standard input
    keys.py old-refused COPY               refused (<code>) | ANSWERED | UNREADABLE (<what>)
    keys.py differs COPY                   (new on stdin) differs | SAME
    keys.py rewrite COPY OUT               the configuration with no credential in a URL
    keys.py clean COPY FILE                (new on stdin) clean | FOUND: <what>
    keys.py absent COPY LOG CONFIG         (new on stdin) absent | FOUND: <where>
    keys.py new-objects ENDPOINT BUCKET USER SINCE   (new on stdin) objects modified since SINCE
    keys.py trace FILE BUCKET              puts=<n> signers=<users> refused=<n>, Loki's PUTs
"""
import re
import sys
from urllib.parse import unquote, urlsplit

S3_LINE = re.compile(r"^([ \t]*)s3:[ \t]*(\S+)[ \t]*$", re.M)
# A URL's userinfo; the masked form `scheme://***@` (scripts/nmas-host's) is not one.
USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://(?!\*\*\*@)[^/\s@]+@")
REFUSED = {"SignatureDoesNotMatch", "InvalidAccessKeyId", "AccessDenied"}


def old(path):
    text = open(path, encoding="utf-8").read()
    found = list(S3_LINE.finditer(text))
    if len(found) != 1:
        sys.exit(f"{path}: {len(found)} s3: URLs, wanted exactly one")
    return text, found[0], urlsplit(found[0].group(2))


def client(endpoint, user, secret):
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=f"http://{endpoint}", aws_access_key_id=user,
                        aws_secret_access_key=secret, region_name="us-east-1",
                        config=Config(retries={"max_attempts": 1}, connect_timeout=5,
                                      read_timeout=30))


def trace(path, bucket):
    """`mc admin trace -v`: one block per request, from its `[REQUEST <call>]` line. Counts
    PutObject requests to BUCKET, the users that signed them, and those answered 4xx or 5xx."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", open(path, encoding="utf-8", errors="replace").read())
    puts, refused, signers = 0, 0, set()
    for block in re.split(r"(?=\[REQUEST )", text)[1:]:
        call = re.match(r"\[REQUEST (\S+)\]", block).group(1)
        if call != "s3.PutObject" or not re.search(rf"\b(?:PUT|POST) /{re.escape(bucket)}/",
                                                   block):
            continue
        puts += 1
        who = re.search(r"Credential=([^/\s]+)/", block)
        signers.add(who.group(1) if who else "(unsigned)")
        status = re.search(r"\[RESPONSE\].*?\n\S*\s*(\d{3}) ", block, re.S)
        if not status or not status.group(1).startswith("2"):
            refused += 1
    return f"puts={puts} signers={','.join(sorted(signers)) or '-'} refused={refused}"


def main(argv):
    what = argv[1]
    if what == "trace":
        print(trace(argv[2], argv[3]))
        return
    if what == "new-objects":
        endpoint, bucket, user, since = argv[2], argv[3], argv[4], int(argv[5])
        import datetime
        s3 = client(endpoint, user, sys.stdin.read())
        t0 = datetime.datetime.fromtimestamp(since, datetime.timezone.utc)
        n, kw = 0, {"Bucket": bucket}
        while True:
            page = s3.list_objects_v2(**kw)
            n += sum(1 for o in page.get("Contents") or [] if o["LastModified"] >= t0)
            if not page.get("IsTruncated"):
                break
            kw["ContinuationToken"] = page["NextContinuationToken"]
        print(n)
        return
    text, m, u = old(argv[2])
    secret = unquote(u.password or "")
    if what == "endpoint":
        print(f"{u.hostname}:{u.port}")
    elif what == "bucket":
        print(u.path.strip("/"))
    elif what == "user":
        print(unquote(u.username or ""))
    elif what == "old-to-mc":
        sys.stdout.write(f"{unquote(u.username)}\n{secret}\n")
    elif what == "old-refused":
        try:
            client(f"{u.hostname}:{u.port}", unquote(u.username), secret).list_objects_v2(
                Bucket=u.path.strip("/"), MaxKeys=1)
            print("ANSWERED")
        except Exception as exc:  # noqa: BLE001 - every failure is named, none is a pass
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            print(f"refused ({code})" if code in REFUSED
                  else f"UNREADABLE ({code or type(exc).__name__})")
    elif what == "differs":
        print("SAME" if sys.stdin.read() == secret else "differs")
    elif what == "rewrite":
        ind = m.group(1)
        block = (f"{ind}endpoint: {u.hostname}:{u.port}\n"
                 f"{ind}bucketnames: {u.path.strip('/')}\n"
                 f"{ind}access_key_id: ${{LOKI_S3_ACCESS_KEY_ID}}\n"
                 f"{ind}secret_access_key: ${{LOKI_S3_SECRET_ACCESS_KEY}}")
        with open(argv[3], "w", encoding="utf-8") as fh:
            fh.write(text[:m.start()] + block + text[m.end():])
    elif what == "clean":
        new, body = sys.stdin.read(), open(argv[3], encoding="utf-8").read()
        found = [w for w, hit in (("a URL with userinfo", USERINFO.search(body)),
                                  ("the old secret", secret in body),
                                  ("the new secret", new in body),
                                  ("no ${LOKI_S3_SECRET_ACCESS_KEY}",
                                   "secret_access_key: ${LOKI_S3_SECRET_ACCESS_KEY}" not in body),
                                  ("no ${LOKI_S3_ACCESS_KEY_ID}",
                                   "access_key_id: ${LOKI_S3_ACCESS_KEY_ID}" not in body)) if hit]
        print("clean" if not found else "FOUND: " + ", ".join(found))
    elif what == "absent":
        new = sys.stdin.read()
        out = open(argv[3], encoding="utf-8", errors="replace").read()
        live = open(argv[4], encoding="utf-8").read()
        found = [w for w, hit in (("the old secret in the output", secret in out),
                                  ("the new secret in the output", new in out),
                                  ("a URL with userinfo in the output", USERINFO.search(out)),
                                  ("the old secret in the configuration", secret in live),
                                  ("the new secret in the configuration", new in live)) if hit]
        print("absent" if not found else "FOUND: " + ", ".join(found))
    else:
        sys.exit(f"unknown: {what}")


if __name__ == "__main__":
    main(sys.argv)
PY

cat > "$DIR/loki-only.json" <<'JSON'
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket","s3:ListBucketMultipartUploads"],"Resource":["arn:aws:s3:::loki"]},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],"Resource":["arn:aws:s3:::loki/*"]}]}
JSON

# recreate before|after: the container as measured today, or with the env file. The binds in the
# order `docker inspect` reads them back, so the check below and this agree.
recreate() {
    local extra=() largs=(-config.file=/etc/loki/local-config.yaml)
    if [ "$1" = after ]; then
        extra=(--env-file "$ENVFILE")
        largs+=(-config.expand-env=true)
    fi
    sudo docker rm -f loki >/dev/null
    sudo docker run -d --name loki --restart unless-stopped -p 3100:3100 \
        -v /var/lib/loki:/loki -v /etc/loki/local-config.yaml:/etc/loki/local-config.yaml:ro \
        "${extra[@]}" "$IMAGE" "${largs[@]}" >/dev/null
}
# ready: Loki answers /ready within 120 s (it waits 15 s after its ring is ready; its start
# itself was not measured).
ready() {
    local i
    for i in $(seq 1 60); do
        curl -sf http://127.0.0.1:3100/ready >/dev/null && return 0
        sleep 2
    done
    return 1
}
# policy_of USER: the policies attached, from mc's JSON field (C752: never grep the text).
policy_of() {
    mc admin user info lokiadm "$1" --json | python3 -c "import sys, json; print(json.load(sys.stdin).get('policyName') or '')"
}
# undo: what ON_FAIL runs, each part saying what it did.
undo() {
    sudo "$PY" "$COPY/keys.py" old-to-mc "$COPY/local-config.yaml" | mc admin user add lokiadm >/dev/null \
        && echo "  loki-writer's old key set again" || echo "  loki-writer's old key NOT set again"
    sudo install -m 640 -o root -g 10001 "$COPY/local-config.yaml" "$CONFIG" \
        && echo "  the copied configuration in place" || echo "  the configuration NOT put back"
    sudo rm -f "$ENVFILE" && echo "  the env file removed"
    recreate before && ready && echo "  Loki ready, as before" || echo "  Loki NOT ready after the undo"
    echo "  the old key: $(sudo "$PY" "$COPY/keys.py" old-refused "$COPY/local-config.yaml")"
}
export -f recreate ready policy_of undo

plan "run as the operator's own user, not root" \
     "outside the nightly backup window (08:30 to 09:10 UTC)" \
     "this is the NMAS host: Loki's container, MinIO's environment file, mc, Mercury's Python with boto3" \
     "the running Loki container is the one this step recreates" \
     "the dated copy reads back the same as the configuration" \
     "the storage URL's user is loki-writer, on the loki bucket" \
     "MinIO's root answers as an admin" \
     "loki-writer holds loki-only alone, and loki-only names the loki bucket alone" \
     "the new secret is 40 letters and digits and differs from the old" \
     "the new configuration holds no credential and no URL with userinfo" \
     "the new configuration changes only the storage URL's line (1 out, 4 in)" \
     "the env file is root's alone (600)" \
     "Loki verifies the new configuration with the env file" \
     "loki-writer still holds loki-only alone after its secret changed" \
     "Loki ready" \
     "Alloy's pushes land after the restart" \
     "new objects in the loki bucket since the restart, listed with the new key" \
     "Loki logged no access refusal since the restart" \
     "the old key is refused" \
     "the trace: Loki's writes since the restart signed by loki-writer alone, none refused" \
     "neither secret appears in this run's output or in the configuration"

not_root
check "outside the nightly backup window (08:30 to 09:10 UTC)" eq "outside" \
    'n=$(date -u +%H%M); [ "$n" -ge 0830 ] && [ "$n" -lt 0910 ] && echo inside || echo outside'
check "this is the NMAS host: Loki's container, MinIO's environment file, mc, Mercury's Python with boto3" eq "yes" \
    'sudo docker inspect loki >/dev/null 2>&1 && sudo test -f "$MINIO_ENV" && command -v mc >/dev/null && "$PY" -c "import boto3" 2>/dev/null && echo yes || echo no'
check "the running Loki container is the one this step recreates" eq "grafana/loki:3.3.2 [-config.file=/etc/loki/local-config.yaml] 3100 /var/lib/loki:/loki /etc/loki/local-config.yaml:/etc/loki/local-config.yaml:ro unless-stopped bridge 10001 env-as-image" \
    'echo "$(sudo docker inspect loki --format "{{.Config.Image}} {{.Args}} {{range \$p, \$b := .HostConfig.PortBindings}}{{(index \$b 0).HostPort}}{{end}} {{join .HostConfig.Binds \" \"}} {{.HostConfig.RestartPolicy.Name}} {{.HostConfig.NetworkMode}} {{.Config.User}}") $([ "$(sudo docker inspect loki --format "{{json .Config.Env}}")" = "$(sudo docker image inspect "$IMAGE" --format "{{json .Config.Env}}")" ] && echo env-as-image || echo env-differs)"'

step "a dated copy of Loki's configuration, the container's definition and this step's helper (root's, mode 700)" \
    'sudo install -d -m 700 "$COPY" && sudo cp -a "$CONFIG" "$COPY/local-config.yaml" && sudo docker inspect loki | sudo tee "$COPY/container.json" >/dev/null && sudo install -m 600 "$DIR/keys.py" "$COPY/keys.py"'
check "the dated copy reads back the same as the configuration" rc0 "" 'sudo cmp "$CONFIG" "$COPY/local-config.yaml"'
ENDPOINT=$(sudo "$PY" "$COPY/keys.py" endpoint "$COPY/local-config.yaml")
BUCKET=$(sudo "$PY" "$COPY/keys.py" bucket "$COPY/local-config.yaml")
export ENDPOINT BUCKET
check "the storage URL's user is loki-writer, on the loki bucket" eq "loki-writer loki" \
    'echo "$(sudo "$PY" "$COPY/keys.py" user "$COPY/local-config.yaml") $BUCKET"'

ROOT_USER=$(sudo grep -E '^MINIO_ROOT_USER=' "$MINIO_ENV" | head -1 | cut -d= -f2- | tr -d '"')
read -r -s -p "MinIO's root password, for $ROOT_USER (hidden): " ROOT_PW; echo
MC_HOST_lokiadm=$(printf '%s' "$ROOT_PW" | ROOT_USER=$ROOT_USER ENDPOINT=$ENDPOINT python3 -c "import sys, os, urllib.parse as u; print('http://' + u.quote(os.environ['ROOT_USER'], safe='') + ':' + u.quote(sys.stdin.read(), safe='') + '@' + os.environ['ENDPOINT'])")
unset ROOT_PW
export MC_HOST_lokiadm
check "MinIO's root answers as an admin" rc0 "" 'mc admin info lokiadm >/dev/null'

step "loki-only on loki-writer (C584's policy, the same JSON), attached before readwrite would leave" \
    'mc admin policy create lokiadm loki-only "$DIR/loki-only.json" >/dev/null && p=$(policy_of loki-writer) && { [[ ",$p," == *,loki-only,* ]] || mc admin policy attach lokiadm loki-only --user loki-writer >/dev/null; } && { [[ ",$p," != *,readwrite,* ]] || mc admin policy detach lokiadm readwrite --user loki-writer >/dev/null; }'
check "loki-writer holds loki-only alone, and loki-only names the loki bucket alone" eq "loki-only | arn:aws:s3:::loki arn:aws:s3:::loki/*" \
    'echo "$(policy_of loki-writer) | $(mc admin policy info lokiadm loki-only | grep -o "arn:aws:s3:::[a-z*/-]*" | sort -u | paste -sd " ")"'

NEW_SECRET=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 40)
REDACT=$NEW_SECRET
export NEW_SECRET
check "the new secret is 40 letters and digits and differs from the old" eq "differs" \
    '[[ "$NEW_SECRET" =~ ^[A-Za-z0-9]{40}$ ]] && printf "%s" "$NEW_SECRET" | sudo "$PY" "$COPY/keys.py" differs "$COPY/local-config.yaml"'

step "the new configuration, written beside the copy (Loki's group may read it, as the live one)" \
    'sudo "$PY" "$COPY/keys.py" rewrite "$COPY/local-config.yaml" "$COPY/local-config.new.yaml" && sudo chown root:10001 "$COPY/local-config.new.yaml" && sudo chmod 640 "$COPY/local-config.new.yaml"'
check "the new configuration holds no credential and no URL with userinfo" eq "clean" \
    'printf "%s" "$NEW_SECRET" | sudo "$PY" "$COPY/keys.py" clean "$COPY/local-config.yaml" "$COPY/local-config.new.yaml"'
check "the new configuration changes only the storage URL's line (1 out, 4 in)" eq "1 4" \
    'd=$(sudo diff "$COPY/local-config.yaml" "$COPY/local-config.new.yaml"); echo "$(grep -c "^<" <<<"$d") $(grep -c "^>" <<<"$d")"'
step "the env file, root's alone (600): the keys on install's standard input" \
    'printf "LOKI_S3_ACCESS_KEY_ID=loki-writer\nLOKI_S3_SECRET_ACCESS_KEY=%s\n" "$NEW_SECRET" | sudo install -m 600 -o root -g root /dev/stdin "$ENVFILE"'
check "the env file is root's alone (600)" eq "600 root root 2" \
    'echo "$(sudo stat -c "%a %U %G" "$ENVFILE") $(sudo grep -c "^LOKI_S3_" "$ENVFILE")"'
check "Loki verifies the new configuration with the env file" rc0 "" \
    'sudo docker run --rm --env-file "$ENVFILE" -v "$COPY/local-config.new.yaml:/etc/loki/local-config.yaml:ro" "$IMAGE" -config.file=/etc/loki/local-config.yaml -config.expand-env=true -verify-config >/dev/null 2>&1'

ON_FAIL=undo
ON_FAIL_WHAT="loki-writer's old key set again, the copied configuration, no env file, the container as it was"
step "the new secret on loki-writer (on mc's standard input)" \
    'printf "loki-writer\n%s\n" "$NEW_SECRET" | mc admin user add lokiadm >/dev/null'
check "loki-writer still holds loki-only alone after its secret changed" eq "loki-only" 'policy_of loki-writer'
RESTART=$(date -u +%s)
export RESTART
step "the new configuration in place and the container recreated with the env file" \
    'sudo install -m 640 -o root -g 10001 "$COPY/local-config.new.yaml" "$CONFIG" && recreate after'
# MinIO's trace from here, so every Loki write it sees is the new container's (stopped by its
# PID; `timeout` ends it in 20 minutes if this script dies first).
timeout 1200 mc admin trace -v lokiadm > "$DIR/trace.txt" 2>&1 &
TRACE_PID=$!
export TRACE_PID
check "Loki ready" rc0 "" 'ready'
# Alloy's lines reach Loki at about 3 a minute; the longest gap in the 24 hours before
# 2026-10-15 01:10 UTC was 300 s, so asked every 5 s for 750 s (2.5 times it).
check "Alloy's pushes land after the restart" ge 1 \
    'for i in $(seq 1 150); do n=$(curl -sG http://127.0.0.1:3100/loki/api/v1/query --data-urlencode "query=sum(count_over_time({job=~\".+\"}[$(( $(date -u +%s) - RESTART + 1 ))s]))" | python3 -c "import sys, json; r = json.load(sys.stdin)[\"data\"][\"result\"]; print(int(float(r[0][\"value\"][1])) if r else 0)" 2>/dev/null); [ "${n:-0}" -ge 1 ] && echo "$n" && exit 0; sleep 5; done; echo 0'
# A chunk is written when its stream is idle 2 minutes or it is 10 minutes old (this Loki's
# ingester settings); C584's trace saw 6 writes in 3 minutes. Asked every 30 s for 15 minutes,
# 1.5 times the configured longest.
check "new objects in the loki bucket since the restart, listed with the new key" ge 1 \
    'for i in $(seq 1 30); do n=$(printf "%s" "$NEW_SECRET" | "$PY" "$DIR/keys.py" new-objects "$ENDPOINT" "$BUCKET" loki-writer "$RESTART" 2>/dev/null); [ "${n:-0}" -ge 1 ] && echo "$n" && exit 0; sleep 30; done; echo 0'
check "Loki logged no access refusal since the restart" eq "0" \
    'sudo docker logs --since "$RESTART" loki 2>&1 | grep -ciE "AccessDenied|InvalidAccessKeyId|SignatureDoesNotMatch|access denied" || true'
check "the old key is refused" re "^refused \(" 'sudo "$PY" "$COPY/keys.py" old-refused "$COPY/local-config.yaml"'
# Loki works on the new key: no undo past here. The trace is read after this, so a trace this
# step misreads can fail the run but never undo a rotation that works.
ON_FAIL=""
kill "$TRACE_PID" 2>/dev/null
wait "$TRACE_PID" 2>/dev/null
TRACE_PID=""
check "the trace: Loki's writes since the restart signed by loki-writer alone, none refused" re "^puts=[1-9][0-9]* signers=loki-writer refused=0$" \
    '"$PY" "$DIR/keys.py" trace "$DIR/trace.txt" "$BUCKET"'
check "neither secret appears in this run's output or in the configuration" eq "absent" \
    'printf "%s" "$NEW_SECRET" | sudo "$PY" "$COPY/keys.py" absent "$COPY/local-config.yaml" "$LOG" "$CONFIG"'
unset NEW_SECRET MC_HOST_lokiadm
echo "== the dated copy, for c788-loki-writer-undo.sh: $COPY"
summary
