"""The console session's state machine: what the console shows, and the ONE thing allowed next.

docs/LAB9_PLAN.md section 8 (out-of-band ZTP for legacy devices), pieces 3 and 6. Pure: no
socket, no sleep, no wall clock. A driver (O2) feeds it the console's bytes as they arrive
(`feed`) and tells it when time passes with nothing arriving (`tick`), each with the time now;
the machine answers with a `Decision`: the state it reads and one action, `wait`, `send` (the
plan's next bytes), `done` or `abort`.

**The plan is the only source of bytes.** It is given at construction: steps, each "in this
state, send these bytes", and the states it may end in. The machine never returns bytes that are
not the plan's next step, never sends in a state the plan's next step does not name, and sends
each step once. On anything unexpected it ABORTS, with a reason naming the state expected and
the state found, and aborted is terminal:
- a login prompt (`Username:`, `Password:`) or a pager (`--More--`), whatever the plan;
- another prompt than the plan's next (a state out of the plan's order);
- an unrecognised prompt (a partial line no pattern names) still there after the quiet period;
- no expected state within the step's bound (`step_timeout_s`, from the start or the last send);
- an IOS REFUSAL (`refusal`: a `%` line the profile does not name a message) anywhere in what
  the console printed since the last send, found wherever the session would act (send its next
  step, or end): nothing is typed and nothing ends "done" past a line the device refused
  (C1593), and `refused` names the line and IOS's words.

**What decides the state** is the newest line received SINCE the last send (so the prompt a
step answered never answers the next step too), skipping blank lines, the echo of what was sent,
and the profile's `ignore` lines (a syslog message).
- **A prompt is read only from the unterminated last line, and only once the console has been
  quiet for the settle interval** (`settle_s`). A prompt waits for input on its own line; a line
  still arriving is not yet anything. Found building this against the real boot text: a chunk
  ending inside an output line (`<redacted>` before its `.`) read as a `>` prompt, and a boot's
  `#####` progress line would read as `#`.
- **A complete line** reads only as a message state (`press_return`, `boot`), else as output
  (the device is talking: wait).
- A settled partial line no pattern names is an unknown prompt, which aborts once the quiet
  period passes. Nothing received for the quiet period reads as `idle`, a state a plan may name
  (to wake a console).

Telnet IAC sequences, NUL and other control bytes are stripped, CR and CRLF become line breaks,
and a sequence or prompt split across chunks is joined before it is read. `transcript()` gives
what was received and sent, in order, masked by modules.redact.redact_text.
"""

from dataclasses import dataclass, field

from modules import redact
from modules.nsot import console_profiles as P

#: The machine's own states beside the profile's prompt states.
IDLE = "idle"          # nothing received since the last send, for the quiet period
WAITING = "waiting"    # nothing decides yet: nothing received, or a line still arriving
OUTPUT = "output"      # a complete line no message pattern names: the device is talking
UNKNOWN = "unknown"    # a settled partial line no pattern names: a prompt the profile lacks
DONE = "done"
ABORTED = "aborted"

#: States that abort whatever the plan says: a login prompt asks for a credential, which never
#: crosses the console, and a pager waits for a key no plan sends.
ALWAYS_ABORT = (P.LOGIN_USER, P.LOGIN_PASSWORD, P.MORE)
#: States a plan's step may send in.
SENDABLE = (IDLE, P.SETUP_DIALOG, P.PRESS_RETURN, P.USER_EXEC, P.PRIV_EXEC, P.CONFIG,
            P.COPY_DESTINATION)
#: States a plan may end in.
FINAL = (P.SETUP_DIALOG, P.PRESS_RETURN, P.USER_EXEC, P.PRIV_EXEC, P.CONFIG)
#: The prompts found at attach that say what the console was left at.
PROMPTS = (P.SETUP_DIALOG, P.PRESS_RETURN, P.USER_EXEC, P.PRIV_EXEC, P.CONFIG, P.LOGIN_USER,
           P.LOGIN_PASSWORD, P.MORE)
#: The states a COMPLETE line may read as: messages printed whole, never a prompt waiting.
LINE_STATES = (P.PRESS_RETURN, P.BOOT)

#: Telnet's interpret-as-command byte and the commands that carry an option byte or a block.
IAC, SB, SE = 0xFF, 0xFA, 0xF0
OPTION_COMMANDS = (0xFB, 0xFC, 0xFD, 0xFE)   # WILL, WONT, DO, DONT


@dataclass(frozen=True)
class Step:
    expect: str
    send: bytes


@dataclass(frozen=True)
class Plan:
    steps: tuple
    final: tuple

    def __post_init__(self):
        check_plan(self)


@dataclass(frozen=True)
class Decision:
    state: str
    action: str            # "wait", "send", "done" or "abort"
    data: bytes = b""
    reason: str = ""


def check_plan(plan: Plan) -> None:
    """A plan's steps each send one line (printable ASCII ended by CR) in a sendable state, and
    its end states are prompts; else ValueError naming the step."""
    if not plan.final:
        raise ValueError("a plan names at least one state it may end in")
    for state in plan.final:
        if state not in FINAL:
            raise ValueError(f"a plan may not end in {state!r}; it may end in {list(FINAL)}")
    for i, step in enumerate(plan.steps, 1):
        if step.expect not in SENDABLE:
            raise ValueError(f"step {i} sends in {step.expect!r}; a step may send only in "
                             f"{list(SENDABLE)}")
        if not isinstance(step.send, bytes) or not step.send.endswith(b"\r"):
            raise ValueError(f"step {i} sends {step.send!r}: one line ended by CR")
        if any(not 0x20 <= b <= 0x7E for b in step.send[:-1]):
            raise ValueError(f"step {i} sends {step.send!r}: printable ASCII only before the CR")


class Cleaner:
    """Console bytes to text: telnet IAC sequences and control bytes removed, CR and CRLF made
    line breaks, a sequence split across chunks held until it completes."""

    def __init__(self):
        self._pending = b""     # an IAC sequence not yet complete
        self._cr = False        # the last byte was a CR (a following LF is the same break)

    def _drop_iac(self, data: bytes) -> bytes:
        data = self._pending + data
        self._pending = b""
        out = bytearray()
        i = 0
        while i < len(data):
            if data[i] != IAC:
                out.append(data[i])
                i += 1
                continue
            end = sequence_end(data, i)
            if end is None or end > len(data):
                self._pending = data[i:]              # the rest of it is still coming
                break
            if data[i + 1] == IAC:
                out.append(IAC)                       # an escaped 0xFF, a data byte
            i = end
        return bytes(out)

    def feed(self, data: bytes) -> str:
        """The text *data* carries, given what earlier chunks left pending."""
        text = []
        for b in self._drop_iac(data):
            after_cr, self._cr = self._cr, b == 0x0D
            if b == 0x0A and after_cr:
                continue                              # CRLF: the CR already broke the line
            if b in (0x0D, 0x0A):
                text.append("\n")
            elif b == 0x09 or 0x20 <= b <= 0x7E:
                text.append(chr(b))
            elif b >= 0x80:
                text.append("?")                     # not ASCII: shown, never matched as text
        return "".join(text)


def sequence_end(data: bytes, i: int):
    """The index just after the telnet command that starts at `data[i]` (an IAC), or None while
    its end has not arrived: IAC IAC and two-byte commands are 2 bytes, an option 3, and a
    subnegotiation runs to its IAC SE."""
    if i + 1 >= len(data):
        return None
    cmd = data[i + 1]
    if cmd in OPTION_COMMANDS:
        return i + 3
    if cmd == SB:
        se = data.find(bytes((IAC, SE)), i + 2)
        return None if se == -1 else se + 2
    return i + 2


def classify(line: str, profile, states: tuple = P.PROMPT_STATES) -> str:
    """The first of *states* (in PROMPT_STATES' order) whose pattern *line* matches, or ""."""
    for state in states:
        for pattern in profile.prompts[state]:
            if pattern.search(line):
                return state
    return ""


def ignored(line: str, profile) -> bool:
    """Whether *line* is one the profile says never decides a state (a syslog message)."""
    return any(p.search(line) for p in profile.ignore)


def refusal(line: str, profile) -> str:
    """IOS's words when *line* is a refusal, else "" (C1593).

    **A refusal is a line whose first character, after its indent, is ``%``, and that the
    profile does not name as a message.** IOS answers a line it will not take with a ``%`` line
    of its own: ``% Invalid input detected at '^' marker.``, ``% Incomplete command.``,
    ``% Ambiguous command: "..."``, ``% Unknown command or computer name, ...``, and its file
    errors ``%Error opening tftp://...``; every other ``%`` line (``% Bad IP address ...``,
    ``%Warning: ...``) is one too, since refusing by resemblance is safe. The messages are the
    profile's ``ignore`` lines, its one home for them: a syslog message
    (``%LINK-3-UPDOWN: ...``, ``%SYS-5-CONFIG_I: ...``: ``%`` then the facility in capitals, a
    severity digit and a mnemonic, then a colon, no space after the ``%``), a timestamped one
    (which does not begin with ``%``), and the informational lines a fetched bootstrap prints
    (``% The key modulus size is 2048 bits``, ``% Generating 2048 bit RSA keys, ...``).
    `console_profiles.validate` refuses an ``ignore`` pattern that matches a refusal."""
    text = line.strip()
    if not text.startswith("%") or ignored(text, profile):
        return ""
    return text


def refused_in(text: str, profile) -> tuple:
    """``(line, before)``: the FIRST refusal among *text*'s lines and the line before it that is
    neither blank nor IOS's caret line (what was refused, where IOS printed it), or
    ``("", "")``."""
    before = ""
    for raw in text.split("\n"):
        words = refusal(raw, profile)
        if words:
            return words, before
        stripped = raw.strip()
        if stripped and stripped != "^":
            before = stripped
    return "", ""


def read_state(text: str, profile, echo: str) -> tuple:
    """`(state, line, partial)` for *text* received since the last send: the newest line that
    decides (not blank, not the echo of *echo*, not an ignored line), the state it reads as,
    and whether it is the line still arriving (no break after it yet); `("", "", False)` when
    no line decides. Only that unterminated line may read as a prompt."""
    lines = text.split("\n")
    last = len(lines) - 1
    for index in reversed(range(len(lines))):
        line = lines[index].strip()
        if not line or line == echo or ignored(line, profile):
            continue
        if index == last:
            # The echo of the line just sent, still arriving (a vIOS-L2 echoed a copy line up
            # to its source URL and paused over 5 s before the rest and its question, C1638):
            # not a prompt, so the step's own bound applies, never the unknown prompt's quiet.
            if echo and echo.startswith(line):
                return "", line, True
            return (classify(line, profile) or UNKNOWN), line, True
        # A prompt followed by the device's own syslog and nothing else (printed after its prompt
        # with no new prompt: a switch's `%LINK-3-UPDOWN` after its `(config-if)#` prompt, C1636)
        # is still the prompt the device waits at. Only an ignored line after it counts: a bare
        # line break after a prompt keeps the settle rule (only the unterminated line).
        after = [t.strip() for t in lines[index + 1:] if t.strip()]
        if after and all(ignored(t, profile) for t in after):
            state = classify(line, profile)
            if state:
                return state, line, False
        return (classify(line, profile, LINE_STATES) or OUTPUT), line, False
    return "", "", False


@dataclass
class ConsoleSession:
    """One console session driven by one plan (`continue_with` adds the next, once done)."""
    profile: object
    plan: Plan
    start: float
    settle_s: float = 0.5
    quiet_s: float = 5.0
    step_timeout_s: float = 600.0
    values: dict = None            # redact_text's known values (None: the installation's)
    state: str = WAITING
    attach_state: str = None       # the first prompt seen before any line was typed
    refused: dict = None           # {"line", "words", "before"}: the refusal that stopped it
    _cleaner: Cleaner = field(default_factory=Cleaner)
    _text: str = ""
    _mark: int = 0                 # where the text since the last send begins
    _index: int = 0                # the plan's next step
    _since: float = None           # when the current wait began (start, or the last send)
    _heard: float = None           # when text last arrived (or the wait began)
    _typed: bool = False           # a line other than a bare CR has been sent
    _echo: str = ""
    _events: list = field(default_factory=list)
    _reason: str = ""

    def __post_init__(self):
        if not 0 < self.settle_s < self.quiet_s < self.step_timeout_s:
            raise ValueError(f"the bounds must rise: 0 < settle_s {self.settle_s} < quiet_s "
                             f"{self.quiet_s} < step_timeout_s {self.step_timeout_s}")
        self._since = self._heard = self.start

    # ── inputs ───────────────────────────────────────────────────────────────────────────
    def feed(self, data: bytes, now: float) -> Decision:
        """Console bytes arrived at *now*."""
        text = self._cleaner.feed(data)
        if text:
            self._events.append(("rx", text))
            self._text += text
            if text.strip():
                self._heard = now
        return self._decide(now)

    def tick(self, now: float) -> Decision:
        """Time passed with nothing arriving."""
        return self._decide(now)

    def continue_with(self, plan: Plan, now: float) -> Decision:
        """The next plan, only once this one is done; the prompt it ended on answers its first
        step, and its wait is bounded from *now*."""
        if self.state != DONE:
            raise ValueError(f"continue_with needs state {DONE!r}; the session is {self.state!r}")
        self.plan, self._index, self._since = plan, 0, now
        return self._next(now)

    # ── the decision ─────────────────────────────────────────────────────────────────────
    def expected(self) -> str:
        """What the plan waits for next, in words."""
        if self._index < len(self.plan.steps):
            return (f"{self.plan.steps[self._index].expect} (step {self._index + 1} of "
                    f"{len(self.plan.steps)})")
        return "one of " + ", ".join(self.plan.final) + " (the plan's end)"

    def _abort(self, reason: str) -> Decision:
        self.state, self._reason = ABORTED, reason
        self._events.append(("abort", reason))
        return Decision(ABORTED, "abort", reason=reason)

    def _decide(self, now: float) -> Decision:
        if self.state == DONE:
            return Decision(DONE, "done", reason=self._reason)
        if self.state == ABORTED:
            return Decision(ABORTED, "abort", reason=self._reason)
        return self._next(now)

    def _next(self, now: float) -> Decision:
        """The decision from what the console shows now (the session not yet done or aborted)."""
        found, line, partial = read_state(self._text[self._mark:], self.profile, self._echo)
        silent = now - self._heard
        quiet = silent >= self.quiet_s
        if not found:
            found = IDLE if quiet else WAITING
        elif partial and silent < self.settle_s:
            found = WAITING                       # a line still arriving is not yet anything
        self.state = found
        if found in PROMPTS and self.attach_state is None and not self._typed:
            self.attach_state = found
        if found in ALWAYS_ABORT:
            return self._abort(f"expected {self.expected()}, found {found}: {line!r}")
        if found == UNKNOWN and quiet:
            return self._abort(f"expected {self.expected()}, found an unknown prompt {line!r} "
                               f"after {self.quiet_s:g} s quiet")
        if self._index < len(self.plan.steps):
            step = self.plan.steps[self._index]
            if found == step.expect:
                return self._refused() or self._send(step, now)
            if found in FINAL:
                return self._abort(f"expected {self.expected()}, found {found}: {line!r} (out "
                                   "of the plan's order)")
        elif found in self.plan.final:
            stop = self._refused()
            if stop is not None:
                return stop
            self.state = DONE
            self._reason = f"ended in {found}"
            return Decision(DONE, "done", reason=self._reason)
        elif found in FINAL:
            return self._abort(f"expected {self.expected()}, found {found}: {line!r}")
        if now - self._since >= self.step_timeout_s:
            return self._abort(f"expected {self.expected()} within {self.step_timeout_s:g} s, "
                               f"found {found}" + (f": {line!r}" if line else ""))
        return Decision(found, "wait")

    def _refused(self):
        """The abort when the console refused what was sent last (C1593), else None. Asked
        wherever the session would act on a prompt (send the next step, or end), so nothing is
        typed and nothing ends "done" after a refusal; the text since the last send is read
        whole, every line of it, so a refusal followed by more output is still found."""
        words, before = refused_in(self._text[self._mark:], self.profile)
        if not words:
            return None
        self.refused = {"line": self._echo, "words": words, "before": before}
        what = (f"{self._echo!r} was refused" if self._echo
                else "the console answered the last send with a refusal")
        return self._abort(f"{what}: {words!r}"
                           + (f" (after {before!r})" if before and before != self._echo else ""))

    def _send(self, step: Step, now: float) -> Decision:
        self._index += 1
        self._mark = len(self._text)
        self._since = self._heard = now
        self._echo = step.send[:-1].decode().strip()  # check_plan: printable ASCII
        if self._echo:
            self._typed = True
        self._events.append(("tx", step.send))
        return Decision(step.expect, "send", data=step.send)

    # ── what happened ────────────────────────────────────────────────────────────────────
    def received_since_send(self) -> str:
        """The text received since the last send (a command's output and the prompt after it)."""
        return self._text[self._mark:]

    def sent(self) -> bytes:
        """Every byte sent, in order."""
        return b"".join(data for kind, data in self._events if kind == "tx")

    def transcript(self) -> str:
        """What was received and sent, in order, masked by redact_text."""
        parts = []
        for kind, data in self._events:
            if kind == "rx":
                parts.append(data)
            elif kind == "tx":
                parts.append(f"\n>>> sent {data.decode()!r}\n")
            elif kind == "abort":
                parts.append(f"\n>>> aborted: {data}\n")
        return redact.redact_text("".join(parts), self.values)
