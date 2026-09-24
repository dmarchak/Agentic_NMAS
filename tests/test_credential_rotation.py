"""Credential rotation: generation, the confirm fingerprint, and the states.

The states matter most. "Did it work" has five answers here, and two of them
are easy to conflate in a way that destroys a completed change: a device that
rotated but whose new password has not reached the startup file is **rotated**,
and reverting it to fix that would undo real work to solve a bookkeeping
problem.
"""

import math
import os
import sys

import pytest

from cryptography.fernet import InvalidToken

from modules.nsot import credential_rotation as cr


class TestGeneration:
    def test_length_and_entropy(self):
        assert cr.LENGTH == 32
        assert len(cr.CHARSET) == 78
        assert 32 * math.log2(len(cr.CHARSET)) > 200

    def test_the_charset_excludes_what_the_cli_would_eat(self):
        for ch in "? \"'\\`|":
            assert ch not in cr.CHARSET, ch

    def test_the_charset_excludes_the_router_db_delimiter(self):
        """':' would produce an unparseable Oxidized row.

        The helper refuses it rather than corrupting the file, so the failure
        is safe — but it lands AFTER the device is rotated and committed,
        stranding the credential live with the boot copy behind. At 32 chars
        from 79, that was 1 - (78/79)**32 = 33.5% of rotations.
        """
        assert ":" not in cr.CHARSET

    def test_no_charset_character_can_break_a_router_db_row(self):
        """Every character, checked against the file format it lands in."""
        for ch in cr.CHARSET:
            assert ch not in ":\n\r", ch
            assert ch.isprintable(), ch

    def test_the_charset_excludes_what_OUR_REDACTOR_cannot_mask(self):
        """`redact._VALUE` refuses a token starting with these.

        A password beginning with `[` would not be positionally masked in a
        log — a defensive measure added elsewhere constraining the generator
        here, which is invisible until it is in a log file.
        """
        from modules import redact

        for ch in "[]<>()":
            assert ch not in cr.CHARSET, ch
            # And prove the coupling rather than restating it.
            line = f"snmp-server community {ch}notmasked RO"
            assert redact.redact_positional(line) == line

    def test_a_generated_password_is_always_maskable(self):
        from modules import redact

        for _ in range(25):
            pw = cr.generate_password("r2")
            out = redact.redact_positional(
                f"username admin privilege 15 algorithm-type scrypt secret {pw}")
            assert pw not in out
            assert "<redacted:user_password>" in out

    def test_no_surrounding_whitespace(self):
        for _ in range(25):
            pw = cr.generate_password("r2")
            assert pw == pw.strip()

    def test_passwords_are_unique(self):
        seen = {cr.generate_password("r2") for _ in range(50)}
        assert len(seen) == 50

    def test_it_uses_secrets_not_random(self):
        import inspect
        source = inspect.getsource(cr)
        assert "secrets.choice" in source
        assert "random.choice" not in source

    def test_a_guard_rejection_retries_but_a_programming_error_does_not(
            self, monkeypatch):
        """A broad except turns 'called it wrong' into a confident wrong answer.

        The first version caught Exception, swallowed a TypeError from calling
        assert_printable with the wrong arity, retried a hundred times, and
        reported that the charset disagreed with the guards.
        """
        def _boom(*a, **k):
            raise TypeError("wrong arity")
        monkeypatch.setattr("modules.nsot.hostvars.assert_printable", _boom)

        with pytest.raises(TypeError):
            cr.generate_password("r2")


class TestTheCommandAndItsMask:
    def test_the_command_matches_what_was_verified_on_the_device(self):
        cmd = cr.rotation_command("admin", 15, "SECRET")
        assert cmd == "username admin privilege 15 algorithm-type scrypt secret SECRET"

    def test_no_privilege_renders_without_the_clause(self):
        assert cr.rotation_command("bob", None, "S") == \
            "username bob algorithm-type scrypt secret S"

    def test_the_masked_form_carries_no_value(self):
        masked = cr.masked_command("admin", 15)
        assert "<generated>" in masked
        assert masked.startswith("username admin privilege 15 algorithm-type scrypt")


class TestTheConfirmFingerprint:
    BASE = dict(device_identity="uid:r2", username="admin", privilege=15,
                entry_kind="secret",
                user_line="username admin privilege 15 secret 5 $1$a$b")

    def test_it_is_stable(self):
        assert cr.operation_fingerprint(**self.BASE) == \
            cr.operation_fingerprint(**self.BASE)

    def test_it_does_not_depend_on_the_password(self):
        """The operator cannot confirm bytes they may not see."""
        import inspect
        source = inspect.getsource(cr.operation_fingerprint)
        # The BODY, not the docstring — which explains the exclusion and so
        # naturally contains the word.
        body = source.split('"""')[-1]
        assert "password" not in body

    @pytest.mark.parametrize("field,value", [
        ("device_identity", "uid:r3"),
        ("username", "operator"),
        ("privilege", 1),
        ("entry_kind", "password"),
        ("user_line", "username admin privilege 15 secret 5 $1$DIFFERENT$x"),
    ])
    def test_every_bound_property_moves_it(self, field, value):
        changed = dict(self.BASE, **{field: value})
        assert cr.operation_fingerprint(**changed) != \
            cr.operation_fingerprint(**self.BASE)

    def test_every_parameter_is_required(self):
        """A default is what let rotate() omit entry_kind and never match.

        plan() passed it, rotate() did not, and both ran — producing hashes
        that could never agree. Every confirmation on that path was refused,
        safely and permanently. A missing input must be a TypeError, not a
        different answer.
        """
        import inspect
        sig = inspect.signature(cr.operation_fingerprint)
        defaulted = [n for n, p in sig.parameters.items()
                     if p.default is not inspect.Parameter.empty]
        assert defaulted == [], f"these can be silently omitted: {defaulted}"

    def test_whitespace_in_the_line_does_not_move_it(self):
        """Rendering differences are not changes."""
        spaced = dict(self.BASE,
                      user_line="  username   admin  privilege 15 "
                                "secret 5   $1$a$b  ")
        assert cr.operation_fingerprint(**spaced) == \
            cr.operation_fingerprint(**self.BASE)

    def test_the_secret_token_is_still_bound(self):
        """Normalising it away would let the credential change underneath."""
        other = dict(self.BASE,
                     user_line="username admin privilege 15 secret 5 $1$a$OTHER")
        assert cr.operation_fingerprint(**other) != \
            cr.operation_fingerprint(**self.BASE)

    def test_the_whole_capture_is_NOT_bound(self, wired):
        """A re-saved golden must not invalidate a confirmation.

        The capture hash covers an entire configuration, which changes for
        reasons that have nothing to do with this operation — a Save All, a
        timestamp line, an NTP clock-period drift. Refusing on those is safe
        and still wrong.
        """
        first = cr.fingerprint_for(cr.preflight("Lab", "r2"))
        wired["golden_line"] = ORIGINAL_LINE   # unchanged user line...
        pre = cr.preflight("Lab", "r2")
        pre["capture"] = pre["capture"] + "\nntp clock-period 17179860\n"
        assert cr.fingerprint_for(pre) == first

    def test_plan_and_rotate_use_the_same_function(self):
        """The defect, stated structurally: there must be ONE producer."""
        import ast
        import io as _io

        tree = ast.parse(_io.open("modules/nsot/credential_rotation.py",
                                  encoding="utf-8").read())
        callers = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and \
                        getattr(call.func, "id", "") == "operation_fingerprint":
                    callers.setdefault(node.name, 0)
                    callers[node.name] += 1
        assert set(callers) == {"fingerprint_for"}, (
            f"operation_fingerprint is called from {sorted(callers)} — every "
            "caller but fingerprint_for can drift from the others")

    def test_changing_the_charset_moves_it(self, monkeypatch):
        before = cr.operation_fingerprint(**self.BASE)
        monkeypatch.setattr(cr, "CHARSET", cr.CHARSET + "?")
        assert cr.operation_fingerprint(**self.BASE) != before


class TestPersistenceFailureIsNotRotationFailure:
    """Amendment 3, made structural rather than remembered."""

    def test_the_states_are_distinct(self):
        states = {cr.ROTATED_PERSISTED, cr.ROTATED_UNVERIFIED, cr.REVERTED,
                  cr.REVERT_FAILED, cr.NOT_STARTED}
        assert len(states) == 5

    def test_a_persistence_failure_is_recognised_as_rotated(self):
        result = {"state": cr.ROTATED_UNVERIFIED, "device": "r2"}
        assert cr.persistence_failed(result) is True

        summary = cr.summarise(result)
        assert "ROTATED and committed" in summary
        assert "not reverted" in summary.lower()
        assert "redeploy would boot the OLD password" in summary

    def test_a_verify_failure_reports_the_device_unchanged(self):
        summary = cr.summarise({"state": cr.REVERTED, "device": "r2"})
        assert "restored and proven" in summary
        assert "device is unchanged" in summary

    def test_a_failed_revert_says_locked_out_and_where_to_go(self):
        summary = cr.summarise({"state": cr.REVERT_FAILED, "device": "r2"})
        assert "MAY BE LOCKED OUT" in summary
        assert "serial console" in summary

    def test_success_claims_redeploy_survival_only_when_persisted(self):
        assert "survives redeploy" in cr.summarise(
            {"state": cr.ROTATED_PERSISTED, "device": "r2"})
        assert "survives redeploy" not in cr.summarise(
            {"state": cr.ROTATED_UNVERIFIED, "device": "r2"})

    def test_a_local_fault_may_never_be_reported_as_a_device_verdict(self):
        """The rule the r2 run broke, stated where it cannot drift."""
        import inspect
        assert "requires having asked the device" in inspect.getdoc(cr)
        summary = cr.summarise({"state": cr.REVERTED_UNPROVEN, "device": "r2"})
        assert "MAY BE LOCKED OUT" not in summary
        assert "local fault" in summary

    def test_only_the_verify_step_is_named_as_reverting(self):
        """Documented in one place so the rule cannot drift."""
        import inspect
        assert cr.VERIFY == "verify_new_credential"
        assert "Only :data:`VERIFY` failing reverts" in inspect.getdoc(cr)


ORIGINAL_LINE = "username admin privilege 15 password OldPlaintext"
ORIGINAL_PLAINTEXT = "OldPlaintext"
#: A stored type-5 hash, as a switch's original line carries.
ORIGINAL_HASH = "$1$salt$hash"
POST_CONFIG = "username admin privilege 15 secret 9 $9$saltsalt$hashhash"


class NetmikoAuthenticationException(Exception):
    """Named to match the real one — the classifier keys on the class NAME."""


class _Router:
    """The device itself: it accepts exactly one password at a time.

    The point of modelling this at all is that a fresh login must be judged by
    what the device would do, not by a stubbed verdict. A dict carrying an
    encrypted password, or a password the push never set, fails here the way
    it would fail on hardware.
    """

    #: Verbatim from r2, IOS-XE 17.06.01a.
    REFUSAL = ("ERROR: Can not have both a user password and a user secret.\n"
               "Please choose one or the other.\n")
    CONFIRM = ("This operation will remove all username related configurations "
               "with same name.Do you want to continue? [confirm]")

    def __init__(self, password=ORIGINAL_PLAINTEXT):
        self.password = password
        self.logins = []            # every kwargs dict ConnectHandler received
        self.running = ORIGINAL_LINE
        self.entry = "password"     # which kind of entry the account holds
        self.exists = True
        self.stores = "9"           # what the running config shows after a push
        self.honours_new_secret = True   # False: stores it, won't authenticate
        self.dead = False           # refuses every credential
        self.local_fault = None     # raised before any "connection" happens
        self.awaiting_confirm = False
        # hash token -> the plaintext that produced it. A `secret 5 $1$…`
        # line does not CONTAIN a password, it names one. The fake used to
        # treat the token after `secret` as the plaintext, so re-sending a
        # stored hash set the password to the type digit. That made the
        # switch revert — which restores exactly such a line — untestable.
        self.hashes = {ORIGINAL_HASH: ORIGINAL_PLAINTEXT}

    def login(self, **kwargs):
        if self.local_fault is not None:
            raise self.local_fault
        self.logins.append(dict(kwargs))
        if self.dead or not self.exists \
                or kwargs.get("password") != self.password:
            raise NetmikoAuthenticationException(
                f"Authentication to device {kwargs.get('ip')} failed")
        return _Conn(self)

    def full_config(self):
        """A plausible whole running-config, as `show running-config` gives.

        The fake used to answer every read with the same short string, so a
        rotation that stored a FILTERED read as the golden looked identical to
        one that stored the real thing. That is how two devices' goldens were
        replaced by a two-line fragment with every test passing.
        """
        body = "\n".join(f"interface GigabitEthernet0/{n}\n"
                          f" description link {n}\n ip address 203.0.113.{n} "
                          "255.255.255.0\n no shutdown"
                          for n in range(1, 9))
        return ("version 17.6\nhostname r2\n!\n"
                f"{self.running}\n!\n{body}\n!\n"
                "router ospf 1\n network 203.0.113.0 0.0.0.255 area 0\n!\n"
                "line vty 0 4\n transport input ssh\n!\nend\n")

    def apply(self, line):
        """Apply one config line; return what the device would print.

        This models the behaviour measured on r2 rather than the behaviour the
        command's name suggests. Setting a secret on a username that already
        holds a ``password`` entry is REFUSED — well-formed, so no
        ``% Invalid input``, just a plain-English decline and no change. Every
        device in the fleet is in that state, so the original one-command
        rotation could not have worked on any of them.
        """
        line = line.strip()
        if self.awaiting_confirm:
            self.awaiting_confirm = False
            self.exists = False
            self.running = ""
            return ""

        parts = line.split()
        if parts[:2] == ["no", "username"]:
            if not self.exists:
                return ""
            self.awaiting_confirm = True
            return self.CONFIRM

        if parts[:1] != ["username"]:
            return ""

        for keyword in ("secret", "password", "nopassword"):
            if keyword in parts:
                break
        else:
            return ""

        if keyword == "nopassword":
            self.entry = "nopassword"
            self.exists = True
            self.running = line
            return ""

        value = parts[parts.index(keyword) + 1]

        # `secret <digit> <hash>`: a stored hash being pasted back, not a
        # plaintext. The accepted password is whatever produced that hash.
        if keyword == "secret" and value.isdigit() and len(parts) > \
                parts.index(keyword) + 2:
            token = parts[parts.index(keyword) + 2]
            if self.exists and self.entry == "password":
                return self.REFUSAL
            self.exists, self.entry = True, "secret"
            self.running = line
            self.password = self.hashes.get(token, "\0unknown-hash")
            return ""

        if keyword == "password":
            # Symmetric: the device refuses a password over a secret entry for
            # the same reason it refuses a secret over a password one. This is
            # what the REVERT walks into after a successful push.
            if self.exists and self.entry == "secret":
                return self.REFUSAL
            self.exists, self.entry = True, "password"
            self.running, self.password = line, value
            return ""

        # keyword == "secret"
        if self.exists and self.entry == "password":
            return self.REFUSAL           # refused; nothing changes

        self.exists, self.entry = True, "secret"
        if "algorithm-type" in parts:
            # IOS hashes it: the running config never shows the plaintext
            # again, which is why the verify must carry the value from memory.
            token = f"$9${abs(hash(value)) % 10**8}$hashhash"
            self.hashes[token] = value
            self.running = (f"username {parts[1]} privilege 15 "
                            f"secret {self.stores} {token}")
        else:
            token = f"$1${abs(hash(value)) % 10**8}$md5"
            self.hashes[token] = value
            self.running = (f"username {parts[1]} privilege 15 "
                            f"secret 5 {token}")
        if self.honours_new_secret:
            self.password = value
        return ""


class _Conn:
    """A fresh Netmiko connection to a _Router."""

    def __init__(self, router):
        self.router = router
        self.disconnected = False

    def enable(self):
        return ""

    def send_command(self, command="", *a, **k):
        if "running-config" in command and "include" not in command:
            return self.router.full_config()
        return "hostname r2\n" + self.router.running

    def disconnect(self):
        self.disconnected = True


class _Session:
    """A stand-in for the held-open original session.

    Holding a reference to the router is what makes the push real: the line it
    accepts is the line that changes which password a later fresh login needs.
    """

    def __init__(self, fail_on=None, router=None):
        self.sent = []
        self.fail_on = fail_on or []
        self.disconnected = False
        self.router = router
        self.in_config = False

    def send_config_set(self, commands, **kw):
        out = ""
        for line in commands:
            out += self._one(line)
        return out or "ok"

    # --- the timing API push_rotation actually uses ----------------------
    #
    # send_config_set cannot answer a [confirm] prompt: it waits for a prompt
    # that never comes. The real push drives config mode by hand, so the fake
    # has to offer the same surface.

    def config_mode(self):
        self.in_config = True
        return ""

    def exit_config_mode(self):
        self.in_config = False
        return ""

    def send_command_timing(self, command, **kw):
        if command.strip() in ("", "\n"):          # answering [confirm]
            return self.router.apply("") if self.router else ""
        return self._one(command)

    def _one(self, line):
        self.sent.append(line)
        for needle in self.fail_on:
            if needle in line:
                raise RuntimeError(f"device rejected: {needle}")
        return self.router.apply(line) if self.router is not None else ""

    def send_command(self, command="", *a, **k):
        if "running-config" in command and "include" not in command:
            return self.router.full_config() if self.router else ""
        return "clock"

    def disconnect(self):
        self.disconnected = True


def _live_fields(state):
    """What preflight() derives from the live read, mirrored for the fake."""
    live = state.get("live_override")
    if live is not None:
        ok, line = live["ok"], live.get("line", "")
    else:
        ok, line = True, state["router"].running
    kind = cr.entry_kind(line) if ok else ""
    golden_kind = cr.entry_kind(state["golden_line"])
    if not ok:
        note = "the device could not be read — falling back to the two-command form"
    elif golden_kind != kind:
        note = (f"the golden records a '{golden_kind or 'unknown'}' entry, the "
                f"device has a '{kind}' one — the DEVICE decides the program, "
                f"and this device's golden is stale")
    else:
        note = ""
    return {"live_read_ok": ok, "live_line": line, "entry_kind": kind,
            "original_line": line if ok else state["golden_line"],
            "discrepancy": note}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Everything around the device replaced; the sequence itself is real."""
    repo = tmp_path / "config_repo"
    (repo / ".nsot").mkdir(parents=True)

    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "username": "admin", "password": "enc", "secret": "enc"}

    # `plan()` calls `platform_of()`, which resolves the list's CSV through
    # `get_list_data_dir()` -- and that calls `os.makedirs()`, so merely
    # asking where list "Lab" lives creates `data/lists/lab/` in the working
    # checkout. Added in Stage 1.7 and caught by conftest's data-directory
    # guard once that directory stopped already existing.
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(tmp_path))

    router = _Router()
    state = {"router": router, "session": _Session(router=router),
             "commit_ok": True, "golden_line": ORIGINAL_LINE}

    # Mocked at the Netmiko boundary, NOT above it. The connection dict that
    # verify_new_credential builds is therefore exercised for real — which is
    # the whole reason this fixture exists in this shape. See
    # TestTheConnectionDict.
    import netmiko
    monkeypatch.setattr(netmiko, "ConnectHandler",
                        lambda **kw: state["router"].login(**kw))
    monkeypatch.setattr(cr, "_SLEEP", lambda _s: None)

    # `**kw` so the stub does not have to be edited for every parameter the
    # real `preflight` grows — it gained `device` and `capture` for the
    # onboarding path, and a fixed-arity lambda made 48 tests fail with a
    # TypeError rather than with anything about rotation. Third stub-signature
    # drift in this stage, and the first caught immediately, because the real
    # signature changed rather than the caller's idea of it.
    monkeypatch.setattr(cr, "preflight", lambda ln, hn, **kw: {
        "ok": True, "device": hn, "repo": str(repo), "device_row": device,
        "mgmt_ip": device["ip"], "identity": "uid:r2", "username": "admin",
        "privilege": "15", "current_line": state["golden_line"],
        "capture": "hostname r2\n" + state["golden_line"], "checks": [],
        # preflight does the live read; the fake device is the source of
        # truth for it, exactly as on hardware. Computed the same way the
        # real preflight computes it, so the stub cannot quietly disagree
        # with the thing it stands in for.
        **_live_fields(state),
    })
    monkeypatch.setattr(cr, "open_original_session", lambda d: state["session"])
    monkeypatch.setattr(cr, "_commit",
                        lambda *a, **k: {"ok": state["commit_ok"],
                                         "commit": "abc123"})
    monkeypatch.setattr("modules.device.decrypt_field", lambda v: "OldPlaintext")
    state["repo"] = str(repo)
    state["device"] = device
    return state


def _fingerprint(state):
    """Through the SAME function the plan and the apply use.

    This helper used to build the hash itself, which is the very duplication
    that let plan() and rotate() drift apart — a test that recomputes a value
    independently cannot notice two producers disagreeing.
    """
    return cr.fingerprint_for(cr.preflight("Lab", "r2"))


class TestTheFiveStates:
    def test_success_is_pending_persist_until_persistence_runs(self, wired):
        """The commit does not claim redeploy survival — persist() does."""
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.ROTATED_PENDING_PERSIST
        assert "survives redeploy" not in cr.summarise(result)
        assert any(s["name"] == cr.VERIFY and s["ok"] for s in result["steps"])

    def test_a_verify_failure_reverts_and_proves_it(self, wired):
        # The device stores the new secret but will not authenticate with it.
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        assert ORIGINAL_LINE in wired["session"].sent, "the original was re-sent"
        assert "device is unchanged" in cr.summarise(result)

    def test_a_failed_revert_says_locked_out(self, wired):
        """Only this — the device ASKED and REFUSING — may claim a lockout."""
        wired["router"].dead = True
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERT_FAILED
        assert "MAY BE LOCKED OUT" in cr.summarise(result)
        assert "serial console" in cr.summarise(result)
        assert wired["router"].logins, "the device was actually asked"

    def test_a_revert_push_failure_is_still_a_lockout_risk(self, wired):
        """Device-side: the original never went back. The danger is real."""
        wired["router"].honours_new_secret = False
        wired["session"].fail_on = [ORIGINAL_PLAINTEXT]
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERT_FAILED
        assert "revert command failed" in result["reason"]
        assert "MAY BE LOCKED OUT" in cr.summarise(result)

    def test_each_revert_failure_names_its_own_cause(self, wired):
        """One state, three causes — the summary must not assert the wrong one."""
        assert "refused the original" in cr.summarise(
            {"state": cr.REVERT_FAILED, "device": "r2",
             "reason": "the device refused the original credential after the revert"})
        assert "revert command failed" in cr.summarise(
            {"state": cr.REVERT_FAILED, "device": "r2",
             "reason": "the revert command failed — recover on the console"})

    def test_a_verify_that_could_not_run_is_not_a_lockout(self, wired):
        """The r2 defect: a LOCAL fault reported as the device's verdict.

        Nothing reached the device — no socket was opened — so the one thing
        the result may not do is say the device might be lost.
        """
        wired["router"].local_fault = InvalidToken("bad Fernet ciphertext")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED_UNPROVEN
        assert wired["router"].logins == [], "no connection was attempted"
        assert ORIGINAL_LINE in wired["session"].sent, "the revert still ran"
        summary = cr.summarise(result)
        assert "MAY BE LOCKED OUT" not in summary
        assert "LOCAL" in summary.upper()

    def test_a_local_fault_is_retried_while_the_session_is_open(self, wired):
        """Inconclusive is not a verdict: try again before acting on it."""
        calls = {"n": 0}
        real = wired["router"].login

        def _flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise InvalidToken("transient local fault")
            return real(**kwargs)

        wired["router"].login = _flaky
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert calls["n"] == 2, "the first attempt never reached the device"
        assert result["state"] == cr.ROTATED_PENDING_PERSIST

    def test_an_auth_refusal_is_not_retried(self, wired):
        """A verdict is a verdict — retrying it only delays the revert."""
        wired["router"].honours_new_secret = False
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        with_new = [k for k in wired["router"].logins
                    if k["password"] != ORIGINAL_PLAINTEXT]
        assert len(with_new) == 1, "one refusal, one attempt"

    def test_a_rejected_push_changes_nothing(self, wired):
        wired["session"] = _Session(fail_on=["algorithm-type scrypt"],
                                    router=wired["router"])
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.NOT_STARTED
        assert "device is untouched" in cr.summarise(result)

    def test_a_stale_confirmation_is_refused_before_the_push(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint="not-the-hash")

        assert result["state"] == cr.NOT_STARTED
        assert wired["session"].sent == [], "nothing may reach the device"
        assert "re-run the plan" in result["reason"]

    def test_no_original_session_means_no_push(self, wired, monkeypatch):
        """Without a revert path, the push must not happen at all."""
        def _boom(device):
            raise OSError("ssh refused")
        monkeypatch.setattr(cr, "open_original_session", _boom)

        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.NOT_STARTED
        assert "no way to revert" in result["reason"]


class TestTheStagingAndTheCacheOrdering:
    def test_the_plaintext_is_staged_before_the_push(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [s["name"] for s in result["steps"]]
        assert names.index("stage") < names.index("push")

    def test_the_redaction_cache_is_invalidated_before_the_push(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [s["name"] for s in result["steps"]]
        assert names.index("invalidate_redaction_cache") < names.index("push")

    def test_staging_is_cleared_on_success_and_on_revert(self, wired):
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert cr.staged_plaintext(wired["repo"], "r2") is None

        # Back to the pre-rotation state: the first pass left the device
        # holding a secret whose plaintext only that pass knew.
        wired["router"].running = ORIGINAL_LINE
        wired["router"].entry = "password"
        wired["router"].password = ORIGINAL_PLAINTEXT
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_staging_is_cleared_when_the_revert_fails(self, wired):
        """The worst outcome still leaves no password lying in the repo."""
        wired["router"].dead = True
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERT_FAILED
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_staging_is_cleared_when_the_verify_could_not_run(self, wired):
        wired["router"].local_fault = InvalidToken("bad ciphertext")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED_UNPROVEN
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_a_staged_password_round_trips(self, tmp_path):
        repo = str(tmp_path)
        cr.stage_plaintext(repo, "r2", "RecoverMe123")
        assert cr.staged_plaintext(repo, "r2") == "RecoverMe123"

    def test_the_stage_file_is_owner_only(self, tmp_path):
        import os
        path = cr.stage_plaintext(str(tmp_path), "r2", "RecoverMe123")
        assert os.stat(path).st_mode & 0o777 == 0o600

    def test_the_device_must_store_a_type_9(self, wired):
        """A device that stored type 5 is not what was asked for."""
        wired["router"].stores = "5"
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED


class TestTheConnectionDict:
    """The r2 defect: the dict handed to Netmiko, not the verdict above it.

    The first hardware run pushed correctly, held the session correctly, and
    reverted correctly — then reported that the device might be locked out,
    because ``verify_new_credential`` built a device dict carrying a PLAINTEXT
    password and passed it to ``with_temp_connection``, which Fernet-decrypts
    whatever it is given. ``InvalidToken`` was raised before any socket opened.

    Every test here mocks at the Netmiko boundary, so the dict construction is
    exercised rather than stepped over. The old fixture replaced
    ``verify_new_credential`` wholesale, which is exactly why nothing caught it.
    """

    def test_the_new_password_reaches_netmiko_in_plaintext(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.ROTATED_PENDING_PERSIST

        logins = wired["router"].logins
        assert len(logins) == 1
        sent = logins[0]["password"]
        assert sent == wired["router"].password
        assert sent != wired["device"]["password"], "the stored form is ciphertext"

    def test_the_revert_verify_uses_the_decrypted_original(self, wired):
        """Decrypted once, by the caller — never handed on to decrypt again."""
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        assert wired["router"].logins[-1]["password"] == ORIGINAL_PLAINTEXT
        assert all(k["password"] != "enc" for k in wired["router"].logins)

    def test_no_encrypted_field_is_handed_to_netmiko(self, wired):
        """`secret` is the field that made this survivable by accident."""
        wired["router"].honours_new_secret = False
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        for kwargs in wired["router"].logins:
            assert "enc" not in kwargs.values()

    def test_the_verify_path_never_touches_with_temp_connection(
            self, wired, monkeypatch):
        """The regression, stated as the rule rather than as its symptom.

        with_temp_connection() decrypts; the verify holds plaintext. Routing
        one through the other is the defect, so the path may not reach it at
        all — including on the revert.
        """
        import modules.connection as conn

        def _forbidden(*a, **k):
            raise AssertionError("the verify must not decrypt what it holds")

        monkeypatch.setattr(conn, "with_temp_connection", _forbidden)
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED

    def test_the_dict_carries_what_netmiko_needs(self, wired):
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        kwargs = wired["router"].logins[0]
        assert kwargs["device_type"] == "cisco_xe"
        assert kwargs["ip"] == "203.0.113.12"
        assert kwargs["username"] == "admin"

    def test_an_auth_refusal_is_classified_as_a_device_verdict(self, wired):
        out = cr.verify_new_credential(wired["device"], "admin", "WrongOne")
        assert out["ok"] is False
        assert out["attempted"] is True, "the device answered"

    def test_a_fernet_failure_is_classified_as_a_local_fault(self, wired):
        wired["router"].local_fault = InvalidToken("bad ciphertext")
        out = cr.verify_new_credential(wired["device"], "admin", "AnyPassword")
        assert out["ok"] is False
        assert out["attempted"] is False, "nothing was asked of the device"

    def test_an_unrecognised_error_takes_the_alarming_side(self, wired):
        """The two ways to be wrong are not symmetrical.

        A false lockout warning costs a console trip. A false "local fault"
        leaves a device that may really be unreachable without one.
        """
        class SomethingNobodyListed(Exception):
            pass

        wired["router"].local_fault = SomethingNobodyListed("?")
        out = cr.verify_new_credential(wired["device"], "admin", "pw")
        assert out["attempted"] is True
        assert out["recognised"] is False

    def test_an_unrecognised_verdict_says_it_was_a_fallback(self, wired):
        class SomethingNobodyListed(Exception):
            pass

        wired["router"].local_fault = SomethingNobodyListed("?")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERT_FAILED
        assert "UNRECOGNISED" in result["reason"]
        assert "SomethingNobodyListed" in result["reason"]

    def test_both_classifications_are_positive(self):
        """Neither answer may be reached by default alone."""
        assert cr.classify_failure("InvalidToken") == {
            "attempted": False, "recognised": True}
        assert cr.classify_failure("NetmikoAuthenticationException") == {
            "attempted": True, "recognised": True}
        assert cr.classify_failure("WhoKnows")["recognised"] is False

    def test_a_timeout_is_a_device_verdict_not_a_local_fault(self, wired):
        """Unreachable is a fact about the device; retrying it is not free."""
        class NetmikoTimeoutException(Exception):
            pass

        wired["router"].local_fault = NetmikoTimeoutException("timed out")
        out = cr.verify_new_credential(wired["device"], "admin", "AnyPassword")
        assert out["attempted"] is True


class TestTheConnectionParameters:
    """The verify must negotiate exactly like every other connection.

    Connecting directly fixed the decrypt defect and introduced a second risk:
    a second set of ConnectHandler kwargs. If they ever diverge — a legacy KEX
    or host-key algorithm for older IOS, a timeout, a device-type quirk added
    where one failure was noticed — the verify fails for a TRANSPORT reason,
    the classifier reads a connection failure as a device verdict, and a
    rotation that actually succeeded is reverted.

    The fake router cannot catch this: it models the credential exchange, not
    the negotiation. So it is pinned as a property of the parameters instead.
    """

    def test_verify_matches_the_normal_path_in_every_field_but_the_secret(self):
        from modules.connection import connection_params, stored_connection_params

        row = {"device_type": "cisco_xe", "ip": "203.0.113.12",
               "username": "admin", "password": "enc-pw", "secret": "enc-sec"}

        import modules.connection as conn
        real = conn.decrypt_field
        conn.decrypt_field = lambda v: {"enc-pw": "OldPw", "enc-sec": "OldEn"}[v]
        try:
            normal = stored_connection_params(row)
        finally:
            conn.decrypt_field = real

        verify = connection_params(dict(row, username="admin"),
                                   password="FreshPlaintext")

        assert set(normal) == set(verify), "same fields, or one path is special"
        differing = {k for k in normal if normal[k] != verify[k]}
        assert differing == {"password", "secret"}, (
            f"the verify negotiates differently in: {differing - {'password', 'secret'}}")

    def test_the_held_session_and_the_verify_use_one_builder(self):
        """Both rotation sites, not just the one that broke."""
        import inspect
        for func in (cr.open_original_session, cr.verify_new_credential):
            src = inspect.getsource(func)
            assert "connection_params" in src, f"{func.__name__} builds its own"
            assert "device_type=" not in src, f"{func.__name__} hand-rolls kwargs"

    def test_no_caller_hand_rolls_connecthandler_kwargs(self):
        """A sixth site would reintroduce exactly this divergence.

        Structural rather than textual: every ConnectHandler call on these two
        modules must take ``**params`` and name no keyword of its own.
        """
        import ast
        import io

        offenders = []
        for path in ("modules/connection.py",
                     "modules/nsot/credential_rotation.py"):
            tree = ast.parse(io.open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name != "ConnectHandler":
                    continue
                named = [k.arg for k in node.keywords if k.arg is not None]
                if named:
                    offenders.append(f"{path}:{node.lineno} names {named}")

        assert not offenders, (
            "ConnectHandler parameters built outside connection_params(): "
            + "; ".join(offenders))

    def test_connection_params_is_the_only_place_fast_cli_is_set(self):
        import ast
        import io

        tree = ast.parse(io.open("modules/connection.py", encoding="utf-8").read())
        users = [n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and n.id == "FAST_CLI"]
        assert len(users) == 1, f"FAST_CLI read at {len(users)} places: {users}"

    def test_the_secret_defaults_to_the_password(self):
        """Rotation sets both to the new value; the default must not surprise."""
        from modules.connection import connection_params
        params = connection_params(
            {"device_type": "cisco_xe", "ip": "203.0.113.12", "username": "a"},
            password="X")
        assert params["secret"] == "X"

    def test_a_plaintext_password_is_never_decrypted_by_the_builder(self):
        """The builder does not guess which kind of value it was handed."""
        from modules.connection import connection_params
        params = connection_params(
            {"device_type": "cisco_xe", "ip": "203.0.113.12", "username": "a"},
            password="Not-A-Fernet-Token")
        assert params["password"] == "Not-A-Fernet-Token"


class TestTheEnableSecretIsNotTheLoginPassword:
    """Found by the hardware probe, one config change from being a live bug.

    The rotation changes the ``username`` line and nothing else, so a device's
    enable secret is whatever it already was. Passing the NEW login password
    as ``secret`` is wrong the moment a device has a separate one — and it
    fails in the worst direction, because netmiko's ``enable()`` raises
    ``ValueError``, which the name table reads as a local fault. A rotation
    that actually succeeded would be reverted.

    No device in this fleet has an enable secret today, which is exactly why
    it passed on r2 and would have kept passing until Part 2 added one to
    close the serial-console hole.
    """

    def test_the_stored_enable_secret_is_used_not_the_new_password(self, wired):
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        kwargs = wired["router"].logins[0]
        assert kwargs["secret"] == "OldPlaintext", (
            "the verify offered the NEW password as the enable secret")
        assert kwargs["password"] != kwargs["secret"], (
            "login and enable credentials are separate things")

    def test_an_empty_enable_secret_is_passed_through_not_substituted(self):
        """Measured on r2: the stored field decrypts to "".

        The normal path passes that empty string, so this one must too. The
        property being defended is sameness, not correctness-in-isolation.
        """
        import modules.device as dev
        real = dev.decrypt_field
        dev.decrypt_field = lambda v: ""
        try:
            assert cr.enable_secret({"secret": "gAAAAAB-ciphertext"}) == ""
        finally:
            dev.decrypt_field = real

    def test_a_row_with_no_enable_secret_reuses_the_login_password(self):
        assert cr.enable_secret({"secret": ""}) is None
        assert cr.enable_secret({}) is None

        from modules.connection import connection_params
        params = connection_params(
            {"device_type": "cisco_ios", "ip": "203.0.113.12", "username": "a"},
            password="New", secret=None)
        assert params["secret"] == "New"

    def test_a_failure_after_login_is_a_device_verdict(self, wired):
        """netmiko raises ValueError from enable(). We are logged IN."""
        class _NoEnable:
            def enable(self):
                raise ValueError("Failed to enter enable mode.")

            def send_command(self, *a, **k):
                raise AssertionError("never reached")

            def disconnect(self):
                pass

        wired["router"].login = lambda **kw: _NoEnable()
        out = cr.verify_new_credential(wired["device"], "admin", "pw")

        assert out["attempted"] is True, "a login that succeeded is not local"
        assert out["recognised"] is True
        assert out["stage"] == "after_login"

    def test_a_post_login_failure_never_reads_as_a_local_fault(self, wired):
        """The classifier must not get a vote once we are authenticated."""
        assert cr.classify_failure("ValueError")["attempted"] is False
        # ...and yet:
        class _NoEnable:
            def enable(self):
                raise ValueError("Failed to enter enable mode.")

            def disconnect(self):
                pass

        wired["router"].login = lambda **kw: _NoEnable()
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        # The revert-verify hits the same broken enable, so the device really
        # did refuse — REVERT_FAILED is the honest answer. What matters is
        # that it is a DEVICE verdict either way, never REVERTED_UNPROVEN.
        assert result["state"] == cr.REVERT_FAILED
        assert result["state"] != cr.REVERTED_UNPROVEN, (
            "a device that answered must not be reported as a local fault")
        assert "UNRECOGNISED" not in result["reason"]

    def test_the_connect_stage_is_still_classified_by_name(self, wired):
        """Before a connection exists, a name is all there is."""
        wired["router"].local_fault = InvalidToken("bad ciphertext")
        out = cr.verify_new_credential(wired["device"], "admin", "pw")
        assert out["stage"] == "connect"
        assert out["attempted"] is False


class TestTheDeviceRefusesASecretOverAPassword:
    """Measured on r2, IOS-XE 17.06.01a. The reason the rotation never worked.

    Pushing a secret at a username that already holds a ``password`` entry is
    refused::

        ERROR: Can not have both a user password and a user secret.
        Please choose one or the other.

    The command is well-formed, so there is no ``% Invalid input``. The device
    declines it, keeps the old line, and the old credential goes on working.
    Every device in this fleet carries ``password 0 <x>``, so every one of
    them would have refused — r2 was not unlucky, and no amount of changing
    the password would have helped.

    ``secret 0`` without ``algorithm-type`` is refused identically, which is
    what rules out the keyword rather than the coexistence.
    """

    def test_the_old_one_command_form_is_refused(self, wired):
        """The fake now reproduces the hardware, so the old form fails here."""
        router = wired["router"]
        out = router.apply(
            "username admin privilege 15 algorithm-type scrypt secret NewPw")
        assert "Can not have both" in out
        assert router.entry == "password", "nothing changed"
        assert router.password == ORIGINAL_PLAINTEXT, "the old value survives"

    def test_the_refusal_is_not_an_invalid_input_error(self, wired):
        """Which is exactly why the old error pattern missed it."""
        out = wired["router"].apply(
            "username admin privilege 15 algorithm-type scrypt secret NewPw")
        assert "% Invalid" not in out
        assert "Incomplete" not in out

    def test_rotation_commands_removes_the_account_first(self):
        cmds = cr.rotation_commands("admin", 15, "NewPw")
        assert len(cmds) == 2
        assert cmds[0] == "no username admin"
        assert cmds[1] == ("username admin privilege 15 "
                           "algorithm-type scrypt secret NewPw")

    def test_the_masked_program_shows_the_deletion_too(self):
        """The operator confirms what is sent, including the removal."""
        masked = cr.masked_commands("admin", 15)
        assert masked[0] == "no username admin"
        assert "<generated>" in masked[1]
        assert not any("NewPw" in m for m in masked)

    def test_the_fingerprint_still_describes_the_credential(self):
        """Prefixing a deletion must not change what the operator confirms."""
        assert cr.rotation_command("admin", 15, "X") == (
            "username admin privilege 15 algorithm-type scrypt secret X")

    def test_a_full_rotation_now_lands_a_secret(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.ROTATED_PENDING_PERSIST
        assert wired["router"].entry == "secret"
        assert wired["router"].password != ORIGINAL_PLAINTEXT

    def test_the_old_credential_stops_working(self, wired):
        """login OLD: False on hardware. The point of the whole operation."""
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        with pytest.raises(NetmikoAuthenticationException):
            wired["router"].login(ip="203.0.113.12", username="admin",
                                  password=ORIGINAL_PLAINTEXT)


class TestTheConfirmScreenShowsTheWholeProgram:
    """What the operator confirms must be what is sent — both lines of it.

    The program became two commands when the device turned out to refuse a
    secret over an existing password entry. `plan()` went on reporting
    `new_form` from `masked_command` (singular), so the confirm screen showed
    only the credential line and the line that DELETES the account was never
    displayed. The most alarming command in the program was the invisible one.
    """

    def test_the_plan_carries_the_whole_masked_program(self, wired):
        plan = cr.plan("Lab", "r2")
        assert plan["new_program"] == ["no username admin",
                                       "username admin privilege 15 "
                                       "algorithm-type scrypt secret <generated>"]

    def test_the_plan_program_matches_what_rotate_actually_sends(self, wired):
        """The two must not be able to drift apart."""
        plan = cr.plan("Lab", "r2")
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        sent = [c for c in wired["session"].sent if c.strip()]
        shown = plan["new_program"]
        assert len(sent) == len(shown)
        assert sent[0] == shown[0], "the deletion must be shown verbatim"
        assert sent[1].startswith("username admin privilege 15 "
                                  "algorithm-type scrypt secret ")
        assert "<generated>" in shown[1], "the value is masked, the shape is not"

    def test_the_program_never_shows_a_real_secret(self, wired):
        plan = cr.plan("Lab", "r2")
        for line in plan["new_program"]:
            assert ORIGINAL_PLAINTEXT not in line
            assert "<generated>" in line or line.startswith("no username")

    def test_the_fingerprint_still_binds_what_determines_the_program(self):
        """Both commands derive from username and privilege, which are bound.

        So showing the whole program needs no fingerprint change — but if the
        program ever stops being a function of bound inputs, this is the test
        that should start failing.
        """
        a = cr.rotation_commands("admin", 15, "x")
        b = cr.rotation_commands("admin", 15, "y")
        assert [l.replace("x", "").replace("y", "") for l in a] == \
               [l.replace("x", "").replace("y", "") for l in b]
        assert cr.rotation_commands("other", 15, "x")[0] == "no username other"


class TestTheConsumerReportNamesTheDefaultTarget:
    """A caveat and a consequence are different things on the screen.

    yang-push-sub.py holds a literal password, so the rotation cannot update
    it — always reported. What was missing is WHICH device it points at. It
    takes a host argument with a fallback default, so rotating that default's
    credential stops the no-argument invocation working. For most devices that
    is a caveat; for the default target it is a consequence.
    """

    SCRIPT = ('import sys\n'
              'HOST = sys.argv[1] if len(sys.argv) > 1 else "203.0.113.11"\n'
              'X = 1\n'
              'with connect(host=HOST, username="admin", password="literal"):\n'
              '    pass\n')

    def _report(self, tmp_path, monkeypatch, mgmt_ip):
        script = tmp_path / "yang-push-sub.py"
        script.write_text(self.SCRIPT, encoding="utf-8")
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: (str(script)
                                               if k == "yang_push_script" else d))
        return next(c for c in cr.consumer_report("x", mgmt_ip)
                    if c["name"] == "yang-push-sub.py")

    def test_the_default_target_is_named_as_such(self, tmp_path, monkeypatch):
        entry = self._report(tmp_path, monkeypatch, "203.0.113.11")
        assert "DEFAULT TARGET" in entry["action"]
        assert "no argument will fail" in entry["action"]

    def test_another_device_is_reported_as_unaffected_by_default(
            self, tmp_path, monkeypatch):
        entry = self._report(tmp_path, monkeypatch, "203.0.113.99")
        assert "another device" in entry["action"]
        assert "DEFAULT TARGET" not in entry["action"]

    def test_the_line_number_is_found_not_hardcoded(self, tmp_path, monkeypatch):
        """It was pinned at 'line 21' in a string."""
        entry = self._report(tmp_path, monkeypatch, "203.0.113.11")
        assert "line 4" in entry["where"], entry["where"]

    def test_an_unconfigured_script_degrades_to_the_generic_warning(
            self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: "" if k == "yang_push_script" else d)
        entry = next(c for c in cr.consumer_report("x", "203.0.113.11")
                     if c["name"] == "yang-push-sub.py")
        assert "may break" in entry["action"]
        assert "set yang_push_script" in entry["where"]

    def test_a_missing_file_does_not_raise(self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: ("/nonexistent/yang.py"
                                               if k == "yang_push_script" else d))
        entry = next(c for c in cr.consumer_report("x", "203.0.113.11")
                     if c["name"] == "yang-push-sub.py")
        assert entry["action"].startswith("NOT updated")


class TestTheRevertHitsTheSameRefusalMirrored:
    """After a successful push the account holds a SECRET entry.

    The original line sets a password, and the device's objection is symmetric
    — so a one-line revert is declined, and the failure the revert exists to
    recover from becomes a real lockout. Found because the fake was taught the
    device's actual rule rather than the one the command names imply.
    """

    def test_a_one_line_revert_would_be_refused(self, wired):
        router = wired["router"]
        router.entry, router.exists = "secret", True
        out = router.apply(ORIGINAL_LINE)
        assert "Can not have both" in out, "the mirrored refusal"

    def test_the_revert_removes_the_account_first(self, wired):
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        sent = wired["session"].sent
        assert "no username admin" in sent
        assert sent.index("no username admin") < sent.index(ORIGINAL_LINE)

    def test_the_original_credential_works_again_after_the_revert(self, wired):
        wired["router"].honours_new_secret = False
        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert wired["router"].entry == "password"
        assert wired["router"].login(
            ip="203.0.113.12", username="admin", password=ORIGINAL_PLAINTEXT)


class TestARefusedPushIsNotASuccessfulOne:
    """The rotation recorded a successful push of a command the device declined."""

    def test_push_rotation_raises_on_a_refusal(self, wired):
        session = _Session(router=wired["router"])
        with pytest.raises(cr.RotationRefused) as excinfo:
            cr.push_rotation(session, [
                "username admin privilege 15 algorithm-type scrypt secret X"])
        assert "Can not have both" in str(excinfo.value)

    def test_a_refused_push_leaves_the_device_untouched(self, wired):
        wired["session"] = _Session(router=wired["router"])
        # Force the old, refused shape through the real rotate() path.
        import modules.nsot.credential_rotation as mod
        original = mod.rotation_commands
        mod.rotation_commands = lambda u, p, pw, kind="": [
            f"username {u} privilege {p} algorithm-type scrypt secret {pw}"]
        try:
            result = cr.rotate("Lab", "r2",
                               confirmed_fingerprint=_fingerprint(wired))
        finally:
            mod.rotation_commands = original

        assert result["state"] == cr.NOT_STARTED
        assert "Can not have both" in result["reason"]
        assert wired["router"].entry == "password"
        assert cr.staged_plaintext(wired["repo"], "r2") is None

    def test_only_the_current_output_can_trigger_a_confirm_answer(self, wired):
        """Found in a hardware transcript: a second, unasked-for Enter.

        The check searched the ACCUMULATED transcript, so the `no username`
        prompt was still in range after the next command and was answered
        twice. Harmless at a config prompt, and exactly the stray keystroke
        that gets eaten as the answer to some later prompt.
        """
        session = _Session(router=wired["router"])
        cr.push_rotation(session, cr.rotation_commands("admin", 15, "NewPw"))

        blanks = [c for c in session.sent if c.strip() == ""]
        assert len(blanks) == 0, (
            f"answers are sent via send_command_timing, not recorded as "
            f"commands; got {blanks}")
        assert wired["router"].entry == "secret"

    def test_a_second_command_is_not_eaten_as_the_confirm_answer(self, wired):
        """If the prompt consumed it, the account would be absent, not secret."""
        session = _Session(router=wired["router"])
        cr.push_rotation(session, cr.rotation_commands("admin", 15, "NewPw"))
        assert wired["router"].exists is True
        assert wired["router"].entry == "secret"

    def test_push_rotation_answers_the_confirm_prompt(self, wired):
        """An unanswered [confirm] leaves the session mid-dialogue."""
        session = _Session(router=wired["router"])
        cr.push_rotation(session, cr.rotation_commands("admin", 15, "NewPw"))
        assert wired["router"].awaiting_confirm is False
        assert wired["router"].entry == "secret"

    def test_the_error_pattern_matches_the_real_refusal(self):
        import re
        from modules.pipeline import IOS_ERROR_PATTERN

        real = ("R2(config)#username admin privilege 15 algorithm-type scrypt "
                "secret X\n"
                "ERROR: Can not have both a user password and a user secret.\n"
                "Please choose one or the other.\n")
        assert re.search(IOS_ERROR_PATTERN, real)
        assert re.search(IOS_ERROR_PATTERN,
                         "% Invalid input detected at '^' marker.")

    def test_the_error_pattern_does_not_fire_on_echoed_config(self):
        """Netmiko echoes commands after the prompt, so only output starts a line."""
        import re
        from modules.pipeline import IOS_ERROR_PATTERN

        for benign in (
            "R2(config-if)#description ERROR: link flaps under load",
            "R2(config)#banner motd ^C report any ERROR: to noc ^C",
            "R2(config)#ip access-list extended ERROR-DROP",
            "R2(config)#username x privilege 15 secret Ab%Errors",
        ):
            assert not re.search(IOS_ERROR_PATTERN, benign), benign


class TestTheChainMakesOxidizedRereadRouterDb:
    """The defect that stranded r2: writing router.db is not enough.

    Measured on Oxidized 0.37.0 with the CORRECT credential already in the
    file: every fetch failed AuthenticationFailed, GET /reload did not change
    that, and a container restart made the very next fetch succeed. Net::SSH
    from inside the container authenticated with that same row throughout,
    under Oxidized's own option set — so the credential was never wrong. A
    live node object holds its credential in memory.

    The chain had no reload step at all, so `confirm_fetch` was always polling
    an Oxidized that could not have picked the change up.
    """

    BASE = dict(mgmt_ip="203.0.113.12", username="admin", password="pw",
                hostname="r2", new_hash="9 $9$salt$hash",
                after_iso="2026-09-21 08:00:00", platform="cisco_ios")

    def test_the_reload_stage_runs_between_the_write_and_the_fetch(self, monkeypatch):
        order = []
        monkeypatch.setattr(cr, "update_oxidized_row",
                            lambda *a, **k: order.append("write") or {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: order.append("reload") or {"ok": True})
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: order.append("fetch") or {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": True, "matches": 1})

        cr.persist({"device": "r2", "state": cr.ROTATED_UNVERIFIED, "steps": []},
                   **self.BASE)
        assert order == ["write", "reload", "fetch"], (
            "a fetch before the reload polls an Oxidized holding the old "
            "credential")

    def test_a_failed_reload_stops_before_the_fetch(self, monkeypatch):
        """Otherwise the fetch fails for a reason that looks nothing like it."""
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": False, "error": "no such container"})
        called = []
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: called.append(1) or {"ok": True})

        out = cr.persist({"device": "r2", "state": cr.ROTATED_UNVERIFIED,
                          "steps": []}, **self.BASE)
        assert called == []
        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert [s["name"] for s in out["persistence"]][-1] == "oxidized_reload"

    def test_the_reload_never_runs_a_subprocess(self, monkeypatch):
        """The app must not drive Docker. Structural, not a promise.

        The app user is in the `docker` group, which is root-equivalent, so a
        container restart issued by the web process would hand root-equivalent
        capability to anything that compromised it — and it would interrupt
        every other device's fetch on every rotation. Measured: GET /reload
        refreshes a credential on its own, so none of that is needed.
        """
        import subprocess
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_url": "http://x"}.get(k, d))

        def _forbidden(*a, **k):
            raise AssertionError("reload_oxidized must not shell out")

        monkeypatch.setattr(subprocess, "run", _forbidden)
        monkeypatch.setattr(subprocess, "Popen", _forbidden)

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: type("R", (), {"read": lambda s: b"[]"})())
        assert cr.reload_oxidized()["ok"] is True

    def test_no_docker_command_is_reachable_from_the_module(self):
        """A default of `docker restart oxidized` used to live in settings."""
        import ast
        import io as _io

        tree = ast.parse(_io.open("modules/nsot/credential_rotation.py",
                                  encoding="utf-8").read())
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        code_strings = [v for v in literals if "\n" not in v and len(v) < 200]
        assert not [v for v in code_strings if "docker" in v.lower()], (
            "a docker command is reachable as a string literal again")

        from modules.settings_schema import DEFAULTS
        assert "docker" not in DEFAULTS.get("oxidized_reload_command", "").lower()

    def test_the_reload_is_not_ok_until_the_node_list_is_served(self, monkeypatch):
        """A fetch queued against a reloading Oxidized goes nowhere."""
        import urllib.request
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_url": "http://x"}.get(k, d))
        calls = {"n": 0}

        def _urlopen(url, **k):
            calls["n"] += 1
            if "nodes.json" in str(url):
                raise OSError("still reloading")
            return type("R", (), {"read": lambda s: b"ok"})()

        monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
        out = cr.reload_oxidized(timeout=0.01, sleep=lambda _s: None)
        assert out["ok"] is False
        assert "node list not served" in out["error"]

    def test_a_failed_reload_call_is_reported_not_swallowed(self, monkeypatch):
        import urllib.request
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_url": "http://x"}.get(k, d))
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
        out = cr.reload_oxidized()
        assert out["ok"] is False
        assert "/reload failed" in out["error"]


class TestEveryPersistStageIsIdempotent:
    """The recovery path re-runs the chain, so it MEETS finished stages.

    r2 was rotated, its router.db row written, and a later stage failed. The
    persist-only command then refused at the FIRST stage — "expected exactly
    one changed row, changed: none" — because that row was already correct. A
    recovery tool that fails on the state it was built to recover from is not
    a recovery tool.

    ``oxidized_row`` runs the REAL helper as a subprocess here, against a
    temporary router.db, because it is the stage whose idempotence was broken
    and a stub would only assert what the stub was told.
    """

    HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "nmas-oxidized-cred")
    BASE = dict(mgmt_ip="10.255.1.12", username="admin", password="Fresh9Value",
                hostname="r2", new_hash="9 $9$salt$hash", platform="cisco_ios")

    @pytest.fixture
    def world(self, tmp_path, monkeypatch):
        db = tmp_path / "router.db"
        db.write_text("10.255.1.11:ios:admin:Old1\n"
                      "10.255.1.12:ios:admin:Old1\n"
                      "10.255.1.21:ios:admin:Old1\n", encoding="utf-8")
        calls = {"reload": 0, "fetch": 0, "sync": 0, "startup": 0}

        def _row(ip, user, pw, **kw):
            import json as _json
            import subprocess as _sp
            proc = _sp.run([sys.executable, self.HELPER, "--file", str(db),
                            "--ip", ip, "--no-backup"],
                           input=_json.dumps({"username": user, "password": pw}),
                           capture_output=True, text=True, timeout=30)
            try:
                return _json.loads(proc.stdout or "{}")
            except ValueError:
                return {"ok": False, "error": proc.stderr[:120]}

        monkeypatch.setattr(cr, "update_oxidized_row", _row)
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: calls.__setitem__("reload", calls["reload"] + 1)
                            or {"ok": True, "mechanism": "rest_reload"})
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: calls.__setitem__("fetch", calls["fetch"] + 1)
                            or {"ok": True, "end": "2026-09-21 09:24:09 UTC"})
        monkeypatch.setattr(cr, "run_sync",
                            lambda **k: calls.__setitem__("sync", calls["sync"] + 1)
                            or {"ok": True, "rc": 0})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: calls.__setitem__("startup", calls["startup"] + 1)
                            or {"ok": True, "matches": 1})
        return {"db": db, "calls": calls}

    def _run(self):
        return cr.persist({"device": "r2", "state": cr.ROTATED_UNVERIFIED,
                           "steps": []},
                          after_iso=cr.utc_now(), **self.BASE)

    def test_running_persist_twice_reaches_persisted_both_times(self, world):
        """The test the r2 failure asks for, end to end."""
        first = self._run()
        assert first["state"] == cr.ROTATED_PERSISTED, first.get("persistence")

        second = self._run()
        assert second["state"] == cr.ROTATED_PERSISTED, second.get("persistence")
        assert all(st["ok"] for st in second["persistence"])

    def test_the_second_run_reports_the_row_as_already_current(self, world):
        self._run()
        second = self._run()

        row = next(st for st in second["persistence"] if st["name"] == "oxidized_row")
        assert row["ok"] is True
        assert row.get("already_current") is True
        assert row.get("changed") == 0

    def test_the_second_run_rewrites_nothing(self, world):
        self._run()
        before = world["db"].read_text(encoding="utf-8")
        self._run()
        assert world["db"].read_text(encoding="utf-8") == before

    def test_every_stage_still_runs_on_the_second_pass(self, world):
        """Idempotent is not 'skipped'. The outcome is re-established."""
        self._run()
        self._run()
        assert world["calls"] == {"reload": 2, "fetch": 2, "sync": 2,
                                  "startup": 2}

    def test_the_first_run_actually_changed_the_row(self, world):
        """Otherwise 'already current' could be hiding a write that never was."""
        first = self._run()
        row = next(st for st in first["persistence"] if st["name"] == "oxidized_row")
        assert row.get("changed") == 1
        assert row.get("already_current") is not True
        assert "Fresh9Value" in world["db"].read_text(encoding="utf-8")


class TestTimestampsAreTimezoneAware:
    """`confirm_fetch` decides "after the rotation" by comparing datetimes.

    A naive value on either side is either a TypeError or — worse — a silent
    comparison between two different clocks that answers confidently. The
    symptom would be a fetch that looks like it never arrived.
    """

    def test_utc_now_is_aware(self):
        assert cr.utc_now().tzinfo is not None

    def test_oxidized_format_parses_with_and_without_the_suffix(self):
        """Measured on the live REST API: '2026-09-21 09:12:44 UTC'."""
        with_suffix = cr.as_utc("2026-09-21 09:12:44 UTC")
        without = cr.as_utc("2026-09-21 09:12:44")
        assert with_suffix == without
        assert with_suffix.tzinfo is not None

    def test_iso_forms_parse_too(self):
        assert cr.as_utc("2026-09-21T09:12:44+00:00") == \
            cr.as_utc("2026-09-21 09:12:44 UTC")

    def test_a_naive_datetime_is_assumed_utc_not_local(self):
        from datetime import datetime, timezone
        naive = datetime(2026, 9, 21, 9, 12, 44)
        assert cr.as_utc(naive) == datetime(2026, 9, 21, 9, 12, 44,
                                            tzinfo=timezone.utc)

    def test_every_parsed_value_is_comparable_with_every_other(self):
        """The property that matters: no mix can raise."""
        values = [cr.utc_now(), cr.as_utc("2026-09-21 09:12:44 UTC"),
                  cr.as_utc("2026-09-21T09:12:44+00:00")]
        for a in values:
            for b in values:
                assert isinstance(a >= b, bool)

    def test_confirm_fetch_accepts_a_fetch_after_the_start(self, monkeypatch):
        self._drive(monkeypatch, end="2026-09-21 09:24:09 UTC",
                    start="2026-09-21 09:24:00", expect=True)

    def test_confirm_fetch_rejects_a_fetch_from_before_the_start(self, monkeypatch):
        """A stale success must not be read as this run's."""
        self._drive(monkeypatch, end="2026-09-21 09:23:00 UTC",
                    start="2026-09-21 09:24:00", expect=False)

    def _drive(self, monkeypatch, *, end, start, expect):
        import json as _json
        import urllib.request

        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_url": "http://x"}.get(k, d))
        payload = _json.dumps([{"name": "10.255.1.12",
                                "last": {"status": "success", "end": end}}]).encode()

        def _urlopen(url, **k):
            return type("R", (), {"read": lambda s: payload})()

        monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
        out = cr.confirm_fetch("10.255.1.12", cr.as_utc(start), attempts=1,
                               base_delay=0, sleep=lambda _s: None)
        assert out["ok"] is expect, out


#: Wording that must never appear during a run that succeeds. Each of these
#: was, at some point, printed at a moment when it was not true.
FAILURE_WORDING = [
    "FAILED", "Nothing is retrying", "fix the cause", "MAY BE LOCKED OUT",
    "recover on the console", "serial console", "do not redeploy",
    "REFUSED", "could not", "did not verify", "may be locked out",
]


class TestNoFailureWordingDuringASuccessfulRun:
    """Fourth status message in a week that described the wrong state.

    The end-of-rotation summary printed the FAILED-persistence wording —
    "Persistence to the startup config FAILED at the persistence chain.
    Nothing is retrying ... fix the cause" — *before persistence had started*,
    on a run that then succeeded. An operator reading it would have stopped a
    run that was about to work.

    The cause was not the wording. `ROTATED_UNVERIFIED` meant both "not
    attempted yet" and "attempted and failed", and one string cannot carry two
    states — so the summary had to guess, and guessed failure. Fixing the
    sentence would have left the next reader of that state to guess again.
    :data:`ROTATED_PENDING_PERSIST` makes the two distinguishable, which is
    the only reason the message can now be right.
    """

    def test_the_state_between_rotate_and_persist_says_what_happens_next(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        summary = cr.summarise(result)

        assert result["state"] == cr.ROTATED_PENDING_PERSIST
        assert "runs next" in summary
        for word in FAILURE_WORDING:
            assert word not in summary, f"{word!r} before persistence started"

    def test_every_state_a_successful_run_passes_through_is_clean(self, wired):
        """The whole happy path, not just its ends."""
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        summaries = [cr.summarise(result)]
        result["state"] = cr.ROTATED_PERSISTED
        summaries.append(cr.summarise(result))

        for summary in summaries:
            for word in FAILURE_WORDING:
                assert word not in summary, f"{word!r} in {summary!r}"

    def test_a_successful_persist_prints_no_failure_wording(self, monkeypatch):
        for name, value in (("update_oxidized_row", {"ok": True}),
                            ("reload_oxidized", {"ok": True,
                                                 "mechanism": "rest_reload"}),
                            ("confirm_fetch", {"ok": True, "end": "x"}),
                            ("run_sync", {"ok": True}),
                            ("verify_startup_file", {"ok": True, "matches": 1})):
            monkeypatch.setattr(cr, name, (lambda v: (lambda *a, **k: v))(value))

        out = cr.persist({"device": "r2", "state": cr.ROTATED_PENDING_PERSIST,
                          "steps": []},
                         mgmt_ip="203.0.113.12", username="admin",
                         password="pw", hostname="r2",
                         new_hash="9 $9$s$h", after_iso=cr.utc_now(),
                         platform="cisco_ios")
        assert out["state"] == cr.ROTATED_PERSISTED
        summary = cr.summarise(out)
        for word in FAILURE_WORDING:
            assert word not in summary, f"{word!r} in a successful summary"
        assert "survives redeploy" in summary

    def test_failure_wording_appears_only_after_persistence_actually_failed(
            self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row",
                            lambda *a, **k: {"ok": False, "error": "no sudo"})
        out = cr.persist({"device": "r2", "state": cr.ROTATED_PENDING_PERSIST,
                          "steps": []},
                         mgmt_ip="203.0.113.12", username="admin",
                         password="pw", hostname="r2",
                         new_hash="9 $9$s$h", after_iso=cr.utc_now(),
                         platform="cisco_ios")

        assert out["state"] == cr.ROTATED_UNVERIFIED
        summary = cr.summarise(out)
        assert "FAILED" in summary
        assert "Nothing is retrying" in summary
        assert "oxidized_row" in summary, "it must name the stage"

    def test_entering_persist_is_what_makes_attempted_true(self, monkeypatch):
        """Not reaching a stage: crossing the threshold."""
        result = {"device": "r2", "state": cr.ROTATED_PENDING_PERSIST,
                  "steps": []}
        seen = {}

        def _first_stage(*_a, **_k):
            # The state must already say "attempted" by the time the FIRST
            # stage runs — not only once one of them has failed.
            seen["state_on_entry"] = result["state"]
            return {"ok": False, "error": "no sudo"}

        monkeypatch.setattr(cr, "update_oxidized_row", _first_stage)
        cr.persist(result, mgmt_ip="203.0.113.12", username="admin",
                   password="pw", hostname="r2", new_hash="9 $9$s$h",
                   after_iso=cr.utc_now(), platform="cisco_ios")
        assert seen["state_on_entry"] == cr.ROTATED_UNVERIFIED
        assert result["state"] == cr.ROTATED_UNVERIFIED

    def test_rotation_succeeded_covers_every_post_rotation_state(self):
        """"Is the device rotated" must not depend on the persistence phase."""
        for state in (cr.ROTATED_PENDING_PERSIST, cr.ROTATED_UNVERIFIED,
                      cr.ROTATED_PERSISTED):
            assert cr.rotation_succeeded({"state": state}) is True
        for state in (cr.REVERTED, cr.REVERT_FAILED, cr.REVERTED_UNPROVEN,
                      cr.NOT_STARTED):
            assert cr.rotation_succeeded({"state": state}) is False

    def test_persistence_failed_is_not_true_before_it_is_attempted(self):
        assert cr.persistence_failed({"state": cr.ROTATED_PENDING_PERSIST}) is False
        assert cr.persistence_failed({"state": cr.ROTATED_UNVERIFIED}) is True

    def test_every_state_has_its_own_summary(self):
        """A state with no message falls through to "unknown state"."""
        for state in (cr.ROTATED_PERSISTED, cr.ROTATED_PENDING_PERSIST,
                      cr.ROTATED_UNVERIFIED, cr.REVERTED, cr.REVERT_FAILED,
                      cr.REVERTED_UNPROVEN, cr.NOT_STARTED):
            summary = cr.summarise({"state": state, "device": "r2"})
            assert "unknown state" not in summary, state
            assert summary.startswith("r2: ")


class TestTheGoldenIsTheWholeConfigNotTheVerifyRead:
    """The rotation replaced two devices' goldens with a two-line fragment.

    `verify_new_credential()` reads ``show running-config | include ^username``
    — the right command for proving a login and reading back one hash. Its
    output was then passed straight to `save_golden()` as the post-rotation
    capture, so the NSoT recorded r1 and r2 as devices with no interfaces, no
    routing and no services:

        r1  8879 bytes / 337 lines  ->  134 bytes / 2 lines
        r2  8718 bytes / 331 lines  ->  134 bytes / 2 lines

    Every guard held. The commit was well-formed, the trailers were right, the
    tags were right, and the content was wrong — because one read was serving
    two purposes and only one of them had a length nobody would question.
    """

    def _commits(self, wired):
        saved = {}
        import modules.nsot.credential_rotation as mod
        real = mod._commit

        def _spy(list_name, repo, hostname, device, username, privilege,
                 password, new_hash, post_config, actor, **kw):
            saved["config"] = post_config
            return {"ok": True, "commit": "abc123"}

        mod._commit = _spy
        try:
            result = cr.rotate("Lab", "r2",
                               confirmed_fingerprint=_fingerprint(wired))
        finally:
            mod._commit = real
        return result, saved.get("config", "")

    def test_the_committed_golden_is_the_whole_config(self, wired):
        _result, config = self._commits(wired)

        assert len(config.splitlines()) > 20, "a golden is not two lines"
        assert "interface GigabitEthernet0/1" in config
        assert "router ospf 1" in config
        assert config.rstrip().endswith("end")

    def test_the_committed_golden_is_not_the_verify_read(self, wired):
        """The exact substitution that happened."""
        _result, config = self._commits(wired)
        verify_read = cr.verify_new_credential(
            wired["device"], "admin", wired["router"].password,
            secret=cr.enable_secret(wired["device"]))["config"]

        assert config != verify_read
        assert len(config) > len(verify_read) * 5

    def test_the_capture_is_a_separate_unfiltered_read(self, wired):
        """`| include` in the golden read is the defect, restated."""
        asked = []
        session = _Session(router=wired["router"])
        real = session.send_command
        session.send_command = lambda c="", *a, **k: (asked.append(c)
                                                      or real(c, *a, **k))
        cr.capture_running_config(session)

        assert asked, "it must actually read"
        assert all("include" not in c for c in asked), asked
        assert any(c.strip() == "show running-config" for c in asked), asked

    def test_a_short_capture_leaves_the_golden_alone(self, wired, monkeypatch):
        """The guard: never overwrite a config with a fragment."""
        monkeypatch.setattr(cr, "capture_running_config",
                            lambda _s: "username admin privilege 15 secret 9 $9$x")
        _result, config = self._commits(wired)

        assert config == "", (
            f"a fragment reached the golden path: {config!r}")

    def test_a_short_capture_still_records_the_credential(self, wired, monkeypatch):
        """The rotation happened. Skipping the commit would lose the password.

        Returning early on a bad capture would leave the new credential on the
        device and in the staging file and nowhere else — which is exactly the
        crash window the staging file exists to cover.
        """
        monkeypatch.setattr(cr, "capture_running_config", lambda _s: "")
        committed = {}
        import modules.nsot.credential_rotation as mod
        real = mod._commit
        mod._commit = lambda *a, **k: committed.setdefault("ran", True) and \
            {"ok": True, "commit": "abc"} or {"ok": True, "commit": "abc"}
        try:
            result = cr.rotate("Lab", "r2",
                               confirmed_fingerprint=_fingerprint(wired))
        finally:
            mod._commit = real

        assert committed.get("ran") is True, "the credential must still be recorded"
        assert result["state"] == cr.ROTATED_PENDING_PERSIST
        assert result["golden_updated"] is False

    def test_looks_like_a_full_config_rejects_what_got_committed(self):
        fragment = ("! Golden config — r1 (10.255.1.11)\n"
                    "username admin privilege 15 secret 9 $9$abc$def\n")
        assert cr.looks_like_a_full_config(fragment) is False
        assert cr.looks_like_a_full_config("") is False

    def test_looks_like_a_full_config_accepts_a_real_one(self, wired):
        assert cr.looks_like_a_full_config(wired["router"].full_config()) is True

    def test_a_failed_capture_is_reported_as_a_step(self, wired, monkeypatch):
        monkeypatch.setattr(cr, "capture_running_config", lambda _s: "")
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        names = [st["name"] for st in result["steps"]]
        assert "golden_capture" in names
        step = next(st for st in result["steps"] if st["name"] == "golden_capture")
        assert step["ok"] is False
        assert "LEFT UNCHANGED" in step.get("detail", "")


class TestTheProgramIsConditionalOnTheDevicesEntryKind:
    """One command over a secret, two over a password. Measured both ways.

    IOS-XE 17.06, secret over a PASSWORD entry:
        ERROR: Can not have both a user password and a user secret.
    vIOS-L2 15.2, secret over a SECRET entry:
        accepted silently; secret 5 -> secret 9; new works, old dead.

    So the deletion is required by the password case and by nothing else.
    Sending it anyway would delete and recreate an account for no reason,
    opening a window in which it does not exist and raising a [confirm]
    prompt — both risk, no benefit.
    """

    def test_one_command_over_a_secret(self):
        assert cr.rotation_commands("admin", 15, "X", "secret") == [
            "username admin privilege 15 algorithm-type scrypt secret X"]

    def test_two_commands_over_a_password(self):
        assert cr.rotation_commands("admin", 15, "X", "password") == [
            "no username admin",
            "username admin privilege 15 algorithm-type scrypt secret X"]

    def test_an_unknown_kind_gets_the_two_command_form(self):
        """Which works in BOTH states, so it is the safe answer."""
        for unknown in ("", None, "surprise"):
            assert cr.rotation_commands("admin", 15, "X", unknown or "")[0] == \
                "no username admin"

    def test_entry_kind_reads_the_line(self):
        assert cr.entry_kind("username admin privilege 15 secret 5 $1$a$b") == "secret"
        assert cr.entry_kind("username admin privilege 15 password 0 x") == "password"
        assert cr.entry_kind("") == ""
        assert cr.entry_kind("hostname r1") == ""

    def test_the_fingerprint_binds_the_entry_kind(self):
        """The program is a function of it, so a confirmation must cover it."""
        common = dict(device_identity="uid:x", username="admin", privilege=15,
                      user_line="username admin privilege 15 secret 5 $1$a$b")
        assert cr.operation_fingerprint(**common, entry_kind="secret") != \
            cr.operation_fingerprint(**common, entry_kind="password")

    def test_the_plan_program_matches_the_wire_over_a_secret(self, wired):
        """plan == wire, the SECRET path."""
        wired["router"].entry = "secret"
        wired["router"].running = ("username admin privilege 15 "
                                   "secret 5 $1$salt$hash")
        plan = cr.plan("Lab", "r2")
        assert plan["entry_kind"] == "secret"
        assert len(plan["new_program"]) == 1

        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        sent = [c for c in wired["session"].sent if c.strip()]
        assert len(sent) == 1, sent
        assert sent[0].startswith("username admin privilege 15 "
                                  "algorithm-type scrypt secret ")
        assert "no username" not in " ".join(sent)

    def test_the_plan_program_matches_the_wire_over_a_password(self, wired):
        """plan == wire, the PASSWORD path."""
        plan = cr.plan("Lab", "r2")
        assert plan["entry_kind"] == "password"
        assert len(plan["new_program"]) == 2

        cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        sent = [c for c in wired["session"].sent if c.strip()]
        assert sent[0] == "no username admin"
        assert len(sent) == 2

    def test_the_live_read_beats_the_golden(self, wired):
        """A stale golden must not choose the program."""
        # Golden says password (the fixture's ORIGINAL_LINE); device says secret.
        wired["router"].running = "username admin privilege 15 secret 5 $1$a$b"
        plan = cr.plan("Lab", "r2")

        assert plan["entry_kind"] == "secret"
        assert len(plan["new_program"]) == 1
        assert "golden" in plan["discrepancy"]
        assert "stale" in plan["discrepancy"]

    def test_an_unreadable_device_falls_back_and_says_so(self, wired):
        wired["live_override"] = {"ok": False, "line": ""}
        plan = cr.plan("Lab", "r2")

        assert plan["entry_kind"] == ""
        assert len(plan["new_program"]) == 2, "the form correct in either state"
        assert "could not be read" in plan["discrepancy"]

    def test_a_kind_that_changed_since_the_confirm_refuses(self, wired):
        """What was confirmed would no longer be what is sent."""
        plan = cr.plan("Lab", "r2")            # password -> two commands
        fingerprint = plan["fingerprint"]
        # The device now holds a secret instead.
        wired["router"].entry = "secret"
        wired["router"].running = ("username admin privilege 15 "
                                   "secret 5 $1$salt$hash")

        result = cr.rotate("Lab", "r2", confirmed_fingerprint=fingerprint)
        assert result["state"] == cr.NOT_STARTED
        # The FINGERPRINT catches it, before a session is even opened —
        # because the entry kind is bound into it. The re-check on the held
        # session is defence in depth for a change that lands in between.
        assert "does not match" in result["reason"]
        assert wired["session"].sent == [], "nothing may reach the device"


class TestTheRevertIsConditionalToo:
    """Restoring a pasted hash is not the same operation as typing a password.

    Measured on vIOS-L2, restoring `username X privilege 15 secret 5 $1$…`
    over a live `secret 9`: the line comes back byte-identical and the old
    password authenticates again — in ONE command, and also in two.
    """

    ORIGINAL_SECRET = f"username admin privilege 15 secret 5 {ORIGINAL_HASH}"
    ORIGINAL_PASSWORD = "username admin privilege 15 password 0 OldPlaintext"

    def test_one_command_when_the_original_sets_a_secret(self):
        assert cr.revert_commands("admin", self.ORIGINAL_SECRET) == [
            self.ORIGINAL_SECRET]

    def test_two_commands_when_the_original_sets_a_password(self):
        assert cr.revert_commands("admin", self.ORIGINAL_PASSWORD) == [
            "no username admin", self.ORIGINAL_PASSWORD]

    def test_the_switch_revert_restores_the_line_verbatim(self, wired):
        """A hash cannot be retyped; it must go back exactly."""
        wired["router"].entry = "secret"
        wired["router"].running = self.ORIGINAL_SECRET
        wired["router"].honours_new_secret = False

        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))
        assert result["state"] == cr.REVERTED
        assert self.ORIGINAL_SECRET in wired["session"].sent
        assert "no username admin" not in wired["session"].sent, (
            "a secret over a secret needs no deletion, on the revert either")

    def test_the_router_revert_still_deletes_first(self, wired):
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["state"] == cr.REVERTED
        sent = wired["session"].sent
        assert "no username admin" in sent
        assert sent.index("no username admin") < sent.index(ORIGINAL_LINE)


class TestPromptUndetectIsNamedInThePersistSummary:
    """A fleet-wide Oxidized issue must not read as a rotation failure.

    PromptUndetect means Oxidized authenticated and then failed to match its
    prompt regexp. Measured across the switches it affects s1 and s2 equally
    (179 vs 178 failures, same kinds), predates the rotations, and says
    nothing about the credential. An operator who cannot tell it apart from a
    credential problem will investigate the device instead of re-running the
    persist-only command, which is all it needs.
    """

    def _fetch(self, monkeypatch, payload):
        import json
        import urllib.request
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"oxidized_url": "http://x"}.get(k, d))
        blob = json.dumps(payload).encode()
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: type("R", (), {"read": lambda s: blob})())
        return cr.confirm_fetch("10.255.1.21", cr.utc_now(), attempts=1,
                                base_delay=0, sleep=lambda _s: None)

    def test_prompt_undetect_is_named_and_says_what_to_do(self, monkeypatch):
        out = self._fetch(monkeypatch, [{"name": "10.255.1.21", "last": {
            "status": "no_connection",
            "error": "Oxidized::PromptUndetect raised"}}])

        assert out["ok"] is False
        assert out["cause"] == "PromptUndetect"
        assert "rotation itself succeeded" in out["error"]
        assert "persist-only" in out["error"]

    def test_an_auth_failure_is_named_differently(self, monkeypatch):
        """That one IS credential-related and must not be waved off."""
        out = self._fetch(monkeypatch, [{"name": "10.255.1.21", "last": {
            "status": "no_connection",
            "error": "Net::SSH::AuthenticationFailed"}}])

        assert out["cause"] == "AuthenticationFailed"
        assert "credential-related" in out["error"]
        assert "rotation itself succeeded" not in out["error"]

    def test_an_unrecognised_failure_keeps_the_plain_message(self, monkeypatch):
        out = self._fetch(monkeypatch, [{"name": "10.255.1.21", "last": {
            "status": "no_connection", "error": "something else"}}])

        assert out["cause"] == ""
        assert out["error"] == "no successful fetch after the rotation"


class TestAConfirmationSurvivesAnUnchangedDevice:
    """s1 refused its own confirmation: "the device or the plan changed".

    Nothing had changed. `plan()` passed `entry_kind` to the fingerprint and
    `rotate()` did not, so the two computed different hashes from identical
    data and no confirmation on that path could ever match. It failed in the
    safe direction, and it was still a gate that could never open.

    Measured on s1 while diagnosing: four consecutive preflights produced the
    identical fingerprint 078fd91dcd2599a4 and identical values for every
    input. The inputs were never the unstable part.
    """

    def test_two_consecutive_preflights_agree(self, wired):
        first = cr.fingerprint_for(cr.preflight("Lab", "r2"))
        second = cr.fingerprint_for(cr.preflight("Lab", "r2"))
        assert first == second

    def test_they_agree_with_volatile_lines_in_the_capture(self, wired):
        """The device emits lines that differ every read. They must not count.

        `Last configuration change at ...`, `ntp clock-period`, and the
        byte-count banner all move on their own. A confirmation that binds
        them refuses changes it has no business refusing.
        """
        volatile = [
            "! Last configuration change at 09:41:02 UTC Sun Sep 21 2026",
            "ntp clock-period 17179860",
            "! NVRAM config last updated at 09:40:55 UTC Sun Sep 21 2026",
        ]
        first = cr.fingerprint_for(cr.preflight("Lab", "r2"))
        for i, line in enumerate(volatile):
            pre = cr.preflight("Lab", "r2")
            pre["capture"] = pre["capture"] + f"\n{line}\n"
            assert cr.fingerprint_for(pre) == first, line

    def test_a_plan_can_be_confirmed_end_to_end(self, wired):
        """The whole point: the gate must actually open."""
        plan = cr.plan("Lab", "r2")
        result = cr.rotate("Lab", "r2",
                           confirmed_fingerprint=plan["fingerprint"])

        assert result["state"] == cr.ROTATED_PENDING_PERSIST, result.get("reason")
        assert not any(st["name"] == "confirmation" and not st["ok"]
                       for st in result["steps"])

    def test_a_changed_username_line_still_refuses(self, wired):
        """Stability must not have been bought with blindness."""
        plan = cr.plan("Lab", "r2")
        # The credential on the device changes under the confirmation.
        wired["router"].running = ("username admin privilege 15 "
                                   "password SomethingElse")
        result = cr.rotate("Lab", "r2",
                           confirmed_fingerprint=plan["fingerprint"])

        assert result["state"] == cr.NOT_STARTED
        assert "does not match" in result["reason"]
        assert wired["session"].sent == [], "nothing may reach the device"

    def test_a_changed_entry_kind_still_refuses(self, wired):
        plan = cr.plan("Lab", "r2")
        wired["router"].running = ("username admin privilege 15 "
                                   "secret 5 $1$salt$hash")
        result = cr.rotate("Lab", "r2",
                           confirmed_fingerprint=plan["fingerprint"])

        assert result["state"] == cr.NOT_STARTED
        assert wired["session"].sent == []

    def test_a_confirmation_from_another_device_still_refuses(self, wired):
        plan = cr.plan("Lab", "r2")
        other = cr.operation_fingerprint(
            device_identity="uid:somewhere-else", username="admin",
            privilege=15, entry_kind="password", user_line=ORIGINAL_LINE)
        assert other != plan["fingerprint"]

        result = cr.rotate("Lab", "r2", confirmed_fingerprint=other)
        assert result["state"] == cr.NOT_STARTED


class TestPersistenceNeverReverts:
    BASE = dict(mgmt_ip="203.0.113.12", username="admin", password="pw",
                hostname="r2", new_hash="9 $9$salt$hash",
                after_iso="2026-09-21 08:00:00", platform="cisco_ios")

    def _result(self):
        return {"device": "r2", "state": cr.ROTATED_UNVERIFIED, "steps": []}

    def test_a_router_db_failure_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row",
                            lambda *a, **k: {"ok": False, "error": "no sudo"})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert out["persistence"][0]["ok"] is False
        assert "ROTATED and committed" in cr.summarise(out)
        # The message must be TERMINAL: the process has exited by the time it
        # is printed, so nothing is retrying and it must not say otherwise.
        assert "Retrying" not in cr.summarise(out)
        assert "Nothing is retrying" in cr.summarise(out)

    def test_a_fetch_failure_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": True, "mechanism": "restart",
                                         "verified": True})
        monkeypatch.setattr(cr, "confirm_fetch",
                            lambda *a, **k: {"ok": False, "error": "timeout"})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert [s["name"] for s in out["persistence"]] == \
            ["oxidized_row", "oxidized_reload", "fetch_confirmed"]

    def test_a_startup_file_miss_leaves_the_device_rotated(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": True, "mechanism": "restart",
                                         "verified": True})
        monkeypatch.setattr(cr, "confirm_fetch", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": False, "matches": 0})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_UNVERIFIED
        assert "redeploy would boot the OLD password" in cr.summarise(out)

    def test_the_full_chain_reaches_persisted(self, monkeypatch):
        monkeypatch.setattr(cr, "update_oxidized_row", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "reload_oxidized",
                            lambda **k: {"ok": True, "mechanism": "restart",
                                         "verified": True})
        monkeypatch.setattr(cr, "confirm_fetch", lambda *a, **k: {"ok": True})
        monkeypatch.setattr(cr, "run_sync", lambda **k: {"ok": True})
        monkeypatch.setattr(cr, "verify_startup_file",
                            lambda *a, **k: {"ok": True, "matches": 1})
        out = cr.persist(self._result(), **self.BASE)

        assert out["state"] == cr.ROTATED_PERSISTED
        assert "survives redeploy" in cr.summarise(out)

    def test_persist_never_touches_the_device(self):
        """Structural: nothing in the chain can send a command."""
        import inspect
        source = inspect.getsource(cr.persist)
        for forbidden in ("push_rotation", "_revert", "open_original_session",
                          "send_config_set"):
            assert forbidden not in source, forbidden

    def test_confirm_fetch_requires_success_AFTER_the_rotation(self, monkeypatch):
        """A stale success is not a fetch of the new config."""
        import json

        class _Resp:
            def __init__(self, payload):
                self._p = json.dumps(payload).encode()
            def read(self):
                return self._p
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        stale = [{"name": "203.0.113.12",
                  "last": {"status": "success", "end": "2026-09-21 07:00:00 UTC"}}]
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(stale))
        monkeypatch.setattr(cr, "_setting_rest", None, raising=False)

        out = cr.confirm_fetch("203.0.113.12", "2026-09-21 08:00:00",
                               attempts=2, base_delay=0, rest="http://x",
                               sleep=lambda s: None)
        assert out["ok"] is False
        assert "no successful fetch after the rotation" in out["error"]


class TestRotateCarriesWhatPersistNeeds:
    """persist() must not re-read the device to find the hash.

    The hash that matters is the one the VERIFY saw — re-deriving it from a
    later capture would ask the device again and could pick up a different
    answer, which defeats the point of having verified.
    """

    def test_the_verified_hash_is_carried(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert result["new_hash"].startswith("9 $9$")
        assert result["repo"]
        assert result["mgmt_ip"] == "203.0.113.12"
        assert result["username"] == "admin"

    def test_nothing_is_carried_when_the_rotation_did_not_happen(self, wired):
        wired["router"].honours_new_secret = False
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        assert "new_hash" not in result
        assert result["state"] == cr.REVERTED


class TestTheInteractiveScript:
    """The confirm lives in the script because the HTTP gates do not apply."""

    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "nmas-rotate-credential")

    def test_it_refuses_a_non_interactive_stdin(self):
        """A typed confirmation that can be piped in is not a confirmation."""
        import subprocess
        import sys

        proc = subprocess.run([sys.executable, self.SCRIPT, "--device", "r2"],
                              input="r2\n", capture_output=True, text=True)
        assert proc.returncode == 2
        assert "not a terminal" in proc.stderr

    def test_it_requires_the_exact_hostname(self):
        source = open(self.SCRIPT, encoding="utf-8").read()
        assert 'typed != device' in source
        assert "Nothing was sent" in source

    def test_it_records_a_distinct_actor_kind(self):
        """A local CLI session is not Access-verified, and must not look like it."""
        source = open(self.SCRIPT, encoding="utf-8").read()
        assert 'actor_kind="person_cli"' in source
        assert '"access_verified": False' in source
        assert "NOT Access-verified" in source

    def test_it_states_why_the_confirm_is_in_the_script(self):
        doc = open(self.SCRIPT, encoding="utf-8").read()
        assert "does not pass through them" in doc
        assert "bypass the gate" in doc


class TestTheOnboardingParameterisationGoesBothWays:
    """`rotate()` grew `device`, `capture` and `record` for the onboarding
    path. **A parameterisation can collapse to one behaviour and still
    pass**, so all three directions are pinned: the inventory path unchanged,
    the pending path recording to the override, and the inventory path still
    writing the CSV row.

    What is atomic is *"the device holds a new password"* and *"the tool has
    written that password where it can read it"*. What is NOT part of that
    unit is promotion, which claims something different — that the device is
    finished and belongs in the inventory — and happens later, reading the
    credential back out rather than being handed it down a call chain.

    The ordering below `preflight` is untouched: it is the lockout defence.
    """

    def _commit_args(self, monkeypatch):
        """Capture what `_commit` was asked to do, without doing it."""
        from modules.nsot import credential_rotation as cr

        seen = {}

        def _spy(list_name, repo, hostname, device, username, privilege,
                 password, new_hash, post_config, actor, **kw):
            seen.update(record=kw.get("record", "csv"), device=device,
                        password=password, hostname=hostname)
            return {"ok": True, "commit": "abc123"}

        monkeypatch.setattr(cr, "_commit", _spy)
        return seen

    def test_the_default_is_unchanged(self):
        """An inventory device rotates exactly as before: `record` defaults
        to csv and preflight looks the device up itself."""
        import inspect

        from modules.nsot import credential_rotation as cr

        sig = inspect.signature(cr.rotate)
        assert sig.parameters["record"].default == "csv"
        assert sig.parameters["device"].default is None
        assert sig.parameters["capture"].default == ""

        pre = inspect.signature(cr.preflight)
        assert pre.parameters["device"].default is None
        assert pre.parameters["capture"].default == ""

    def test_a_pending_device_records_to_the_override(self, tmp_path,
                                                      monkeypatch):
        """**And writes no CSV row.** A pending device has none — promotion
        writes it, last — so recording to the CSV would write into nothing
        and leave the tool holding a credential the device no longer
        accepts."""
        import modules.credentials as creds
        from modules.nsot import credential_rotation as cr

        # LISTS_DIR, not the function: `get_list_data_dir()` calls
        # os.makedirs, so merely resolving a path creates a list.
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr(creds, "_FILE", str(tmp_path / "creds.json"))
        wrote_csv = []
        monkeypatch.setattr("modules.device.write_devices_csv",
                            lambda *a, **k: wrote_csv.append(a))

        cr._commit("probe", str(tmp_path), "bp1",
                   {"ip": "203.0.113.31", "hostname": "bp1"}, "admin", 15,
                   "N3wR0tatedValue", "", "", "t", record="override")

        assert wrote_csv == [], "a pending rotation wrote a devices.csv"
        got = creds.resolve("203.0.113.31")
        assert got["ok"] is True
        assert got["source"] == "device-override"
        assert got["password"] == "N3wR0tatedValue"

    def test_an_inventory_device_still_writes_the_csv_row(self, tmp_path,
                                                          monkeypatch):
        """The other direction. Without this the parameterisation could have
        collapsed to 'always override' and every test above would pass."""
        from modules.nsot import credential_rotation as cr

        # LISTS_DIR, not the function: `get_list_data_dir()` calls
        # os.makedirs, so merely resolving a path creates a list.
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        wrote_csv = []
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: [{"hostname": "r2", "ip": "203.0.113.2",
                                        "password": "old", "secret": "old"}])
        monkeypatch.setattr("modules.device.write_devices_csv",
                            lambda rows, path: wrote_csv.append(rows))
        monkeypatch.setattr(cr, "_csv_path_for", lambda ln: str(tmp_path / "d.csv"))

        cr._commit("Lab", str(tmp_path), "r2",
                   {"ip": "203.0.113.2", "hostname": "r2"}, "admin", 15,
                   "N3wR0tatedValue", "", "", "t")

        assert wrote_csv, "an inventory rotation did not write the CSV row"
        row = next(r for r in wrote_csv[0] if r["hostname"] == "r2")
        assert row["password"] not in ("old", "N3wR0tatedValue"), (
            "the credential must be encrypted at rest in the CSV")

    def test_preflight_accepts_a_supplied_device_and_capture(self, monkeypatch):
        """`device_in_inventory` and `golden_config_present` were PROXIES —
        for "we know this device's address" and "we know what it looks
        like". A caller holding both has better answers than the stores."""
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr("modules.config.LISTS_DIR", "/tmp/nmas-nonexistent")
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: [])          # nothing in the inventory
        monkeypatch.setattr(cr, "helper_status", lambda: {"ok": True})
        monkeypatch.setattr(cr, "live_user_line",
                            lambda dev, user: {"ok": False, "line": "",
                                               "kind": ""})

        out = cr.preflight("probe", "bp1",
                           device={"ip": "203.0.113.31", "hostname": "bp1",
                                   "username": "admin"},
                           capture="hostname bp1\nusername admin privilege 15 "
                                   "password 0 boot\n!\nend\n")
        names = {c["name"] for c in out["checks"]}
        assert "device_supplied_by_caller" in names
        assert "capture_supplied_by_caller" in names
        assert "device_in_inventory" not in names, (
            "the inventory was consulted for a device that has no row")
        assert out["mgmt_ip"] == "203.0.113.31"
        assert "username admin" in out["capture"]


class TestSelfConfirmationAtItsOwnSite:
    """**`SELF_CONFIRMED`, tested where `rotate()` reads it.**

    Onboarding's phase 2 is one click running seven steps; there is no
    separate plan step, so there is no window between plan and apply for the
    fingerprint to protect, and `_phase_two_confirmation()` sends the shared
    sentinel rather than a hash.

    A control found this untested: deleting the branch from `rotate()` —
    exactly the live failure, where every phase-2 rotation refused with
    `failed_before_any_change` — left the whole suite green. Phase 2's own
    tests inject a stubbed `rotate`, so they cannot reach the comparison,
    and this file never sent the sentinel. **The seam between two tested
    halves, again.**
    """

    def test_the_sentinel_is_honoured_and_the_rotation_proceeds(self, wired):
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=cr.SELF_CONFIRMED)

        assert result["state"] == cr.ROTATED_PENDING_PERSIST, result.get("reason")
        assert "confirmation does not match" not in (result.get("reason") or "")

    def test_it_is_recorded_as_a_step_rather_than_passing_silently(self, wired):
        """A check that passed because it did not run must say so — that is
        what the fingerprint was added to stop."""
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=cr.SELF_CONFIRMED)

        rows = [s for s in result["steps"] if s["name"] == "confirmation"]
        assert len(rows) == 1, f"one confirmation step, got {rows}"
        assert rows[0]["ok"] is True
        assert "self-confirmed" in rows[0]["detail"]

    def test_an_ordinary_confirmation_still_records_no_such_detail(self, wired):
        """The control on the step text: a genuine comparison must not be
        reportable as self-confirmed."""
        result = cr.rotate("Lab", "r2", confirmed_fingerprint=_fingerprint(wired))

        rows = [s for s in result["steps"] if s["name"] == "confirmation"]
        assert len(rows) == 1, f"one confirmation step, got {rows}"
        assert "self-confirmed" not in rows[0]["detail"]

    def test_a_WRONG_fingerprint_is_still_refused(self, wired):
        """The control that matters. A branch honouring the sentinel must
        not honour anything else — otherwise it is not an exemption, it is
        the check removed."""
        result = cr.rotate("Lab", "r2", confirmed_fingerprint="not-the-hash")

        assert result["state"] == cr.NOT_STARTED
        assert "confirmation does not match" in result["reason"]
        assert not wired["session"].sent, "a refused rotation sent something"

    def test_the_sentinel_is_not_a_hash_anyone_could_arrive_at(self):
        """It is a literal, deliberately outside the hash's alphabet: a
        64-character hex digest can never equal it by accident."""
        assert ":" in cr.SELF_CONFIRMED
        assert cr.SELF_CONFIRMED != cr.fingerprint_for(
            {"capture": "", "device_row": {}, "entry_kind": "x"})


class TestThePersistenceChainFailsClosedOnAHalfDeploy:
    """**The window between the NMAS half and the sync half.**

    r6 lives in its own containerlab lab, so its startup config is at
    `labs/r6/configs/r6.cfg` while clab-sync writes to
    `labs/lab/configs/`. Fixing that needs a change in this repository (a
    device -> lab map) and a change in the sync script, and the two will not
    deploy in the same instant.

    **Measured, so it is known before starting rather than discovered
    between two commits:**

    * *NMAS half first.* The resolver points the checks at
      `labs/r6/configs/r6.cfg`, which **exists** — the operator wrote the
      bootstrap artefact there in phase 1 — and holds `password 0`, not the
      rotated `secret 9`. `verify_startup_file()` greps for the new hash,
      does not find it, and the chain stops. **Fails closed.**
    * *Sync half first.* The sync writes the right file, the checks still
      read `labs/lab/configs/r6.cfg`, which is absent, and the chain stops.
      A false negative — safe, and it would send somebody chasing a
      non-problem.

    **The first case is only safe because of the ORDERING**, and the
    ordering was written for a different reason. `verify_startup_applies()`
    on that same bootstrap file returns **`ok: True, applies: True`** — a
    `password` form *does* apply behind vrnetlab's injected line, and the
    device really does end up holding it. The function answers its own
    question truthfully; the question is not *"is this device reboot-safe
    with the credential NMAS holds"*. Presence runs first and returns early,
    so applicability is never reached — and that is a safety property this
    project inherited rather than designed, which is the third shape of that
    kind found in one night.

    So: pinned. Reorder these two stages, or call `startup_applies` alone,
    and the window stops failing closed.
    """

    def _stage_order(self):
        import inspect

        import modules.nsot.credential_rotation as cr

        src = inspect.getsource(cr.persist)
        return src

    def test_presence_is_checked_before_applicability(self):
        src = self._stage_order()
        assert src.index('"startup_file"') < src.index('"startup_applies"'), (
            "applicability now runs first — a bootstrap file reports "
            "`applies: True` and the half-deploy window stops failing closed")

    def test_a_failed_stage_returns_rather_than_continuing(self):
        """`if not _stage(...): return result` — the short-circuit is what
        stops `startup_applies` being reached on a stale file."""
        src = self._stage_order()
        window = src[src.index('"startup_file"'):src.index('"startup_applies"')]
        assert "return result" in window

    def test_applies_says_yes_to_a_bootstrap_file(self, monkeypatch):
        """**The reason the ordering matters**, asserted rather than
        described: the guard passes a file carrying the credential the
        rotation replaced."""
        import modules.nsot.credential_rotation as cr
        from modules.nsot.bootstrap_config import VRNETLAB_INJECTS_USER

        platform = sorted(VRNETLAB_INJECTS_USER)[0]
        monkeypatch.setattr(cr, "_ssh_read", lambda clab, cmd, **k: {
            "ok": True,
            "text": "hostname r6\nusername admin privilege 15 password 0 boot\n"})
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: "clabhost" if k == "clab_host" else (d or "x"))

        out = cr.verify_startup_applies("r6", platform=platform,
                                        username="admin")
        assert out["ok"] is True and out["applies"] is True
        assert out["kind"] == "password"

    def test_and_the_presence_check_says_no_to_the_same_file(self,
                                                             monkeypatch):
        """The stage that actually closes the window."""
        import modules.nsot.credential_rotation as cr

        class _P:
            returncode = 0
            stdout = "0\n"
            stderr = ""

        monkeypatch.setattr("subprocess.run", lambda *a, **k: _P())
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: "clabhost" if k == "clab_host" else (d or "x"))

        out = cr.verify_startup_file("r6", "secret 9 $9$rotated")
        assert out["ok"] is False
        assert out["matches"] == 0


class TestOneOwnerForTheOxidizedRestUrl:
    """Two settings keys named one fact, and only one had a form.

    `oxidized_url` (the integration client, Settings > Integrations) and
    `oxidized_rest_url` (read only by the persistence chain) were both the
    oxidized-web base URL — both fetch `nodes.json` from it. A second name for
    one thing is the shape this project keeps removing: `ListRef`, the
    `nmas-managed` slug, the device → lab map.
    """

    def _settings(self, monkeypatch, values):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: values.get(k, d))

    def test_the_surviving_key_is_oxidized_url(self, monkeypatch):
        self._settings(monkeypatch, {"oxidized_url": "http://ox:8888/"})
        base, refusal = cr._oxidized_rest_base()
        assert refusal is None
        assert base == "http://ox:8888", "the trailing slash is the client's job"

    def test_the_deprecated_key_is_read_by_nothing(self):
        """Parsed, not grepped — the module names it in its own docstring.

        A floor comes with it: the scan must find the surviving key being
        read, or it is a scan that could not run reporting no offenders.
        """
        import ast

        offenders, surviving = [], 0
        for path in ("modules/nsot/credential_rotation.py",
                     "modules/integrations/oxidized.py"):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and getattr(node.func, "id", "") == "get_setting"):
                    continue
                if not (node.args and isinstance(node.args[0], ast.Constant)):
                    continue
                key = node.args[0].value
                if key == "oxidized_rest_url":
                    offenders.append(f"{path}:{node.lineno}")
                if key == "oxidized_url":
                    surviving += 1
        assert surviving >= 1, ("no reader of oxidized_url was found — this "
                                "scan cannot distinguish 'collapsed' from "
                                "'could not run'")
        assert offenders == [], (
            f"oxidized_rest_url is still read at {offenders} — it is "
            "deprecated, and a second reader is how two keys come back")

    def test_a_set_legacy_key_names_the_move_and_adopts_nothing(self, monkeypatch):
        """It refuses. Copying the value across would be a settings write
        nobody asked for, and the rename would then be invisible."""
        written = []
        monkeypatch.setattr("modules.config.set_user_setting",
                            lambda *a, **k: written.append(a))
        self._settings(monkeypatch, {"oxidized_url": "",
                                     "oxidized_rest_url": "http://old:8888"})
        base, refusal = cr._oxidized_rest_base()
        assert base == ""
        assert "oxidized_url" in refusal["error"]
        assert "http://old:8888" in refusal["error"], \
            "the refusal must carry the value, or the operator has to go find it"
        assert written == [], "nothing may be adopted silently"

    def test_both_empty_names_the_surviving_key_only(self, monkeypatch):
        self._settings(monkeypatch, {"oxidized_url": "", "oxidized_rest_url": ""})
        _base, refusal = cr._oxidized_rest_base()
        assert "oxidized_url is not configured" in refusal["error"]
        assert "oxidized_rest_url" not in refusal["error"], \
            "a deprecated key named in a first-run refusal is advice to set it"

    def test_an_explicit_argument_still_wins(self, monkeypatch):
        self._settings(monkeypatch, {"oxidized_url": "http://from-settings"})
        base, refusal = cr._oxidized_rest_base("http://explicit")
        assert (base, refusal) == ("http://explicit", None)

    def test_configured_auth_this_path_cannot_send_is_a_named_refusal(
            self, monkeypatch):
        """A 401 during a credential rotation reads as the wrong credential.

        `OxidizedIntegration` sends basic auth; the persistence chain speaks
        urllib and sends none. Unauthenticated against an Oxidized with auth
        on gets a 401, reported as a failed reload — a credential error,
        during a credential rotation, about a different credential entirely.
        """
        self._settings(monkeypatch, {"oxidized_url": "http://ox:8888",
                                     "oxidized_username": "oxi"})
        base, refusal = cr._oxidized_rest_base()
        assert base == ""
        assert "cannot send" in refusal["error"]
        assert "oxi" in refusal["error"]

    def test_userinfo_in_the_url_is_accepted(self, monkeypatch):
        """urllib does send that, so refusing would be wrong."""
        self._settings(monkeypatch, {"oxidized_url": "http://u:p@ox:8888",
                                     "oxidized_username": "oxi"})
        base, refusal = cr._oxidized_rest_base()
        assert refusal is None and base == "http://u:p@ox:8888"

    def test_the_refusal_reaches_the_chain_stages(self, monkeypatch):
        """Both stages, because both had their own copy of the read."""
        self._settings(monkeypatch, {"oxidized_url": ""})
        reload_out = cr.reload_oxidized()
        assert reload_out["ok"] is False
        assert reload_out["mechanism"] == "rest_reload"
        assert "oxidized_url" in reload_out["error"]
        fetch_out = cr.confirm_fetch("192.0.2.1", "2026-01-01T00:00:00Z")
        assert fetch_out["ok"] is False
        assert "oxidized_url" in fetch_out["error"]
