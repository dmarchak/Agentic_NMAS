"""C3330: the logs-tail reader's forward read is bounded, so a failed read can never make the
next one longer (modules/readers/logs_tail.py, `_forward`).

The incident (2026-11-12, measured on the host): from 14:36 UTC every read of `logs-tail`
failed. The newest line held moves only on a success, so each later read asked from further
back, for every device, timed out, and asked further back again. Held here, on r3's and s3's
real lines (test_logs_buffer's corpus and its fake Loki, which answers each query by its own
time range, stages and limit), counted, never timed:

- a reader whose reads fail N times asks the same bounded range each time, never more than the
  tail's own window (the first read's), however long it has failed;
- after the success the buffer says what it missed (``missed``: from the newest line it held
  to where the read began), and the backfill fills it, paged, after which ``missed`` is gone
  and the lines the device sent while the reader failed are held.
"""

import pytest

from modules import logs_buffer as B
from modules.readers import logs_tail as T
from tests.test_logs_buffer import CONFIG, CORPUS, NOW, FakeLoki, data, fill  # noqa: F401

NS = 10 ** 9


class Failing(FakeLoki):
    """Loki as it was from 14:36: every ask recorded, and none answered."""

    def ask(self, path, **p):
        self.asked.append(dict(p, path=path))
        raise RuntimeError("Loki did not answer within 5 s (loki/api/v1/query_range)")


class TestTheForwardReadIsBounded:
    def test_failed_reads_ask_the_same_bounded_range_however_long_they_fail(self, data):
        v1 = fill()
        loki = Failing()
        spans = []
        # Fifty failed reads, the clock moving past the window and on to 45 minutes after the
        # newest line held: the last good value stays, as reader_job keeps it (rule 3).
        for i in range(1, 51):
            t = NOW + 54 * i
            del loki.asked[:]
            with pytest.raises(RuntimeError):
                T.read("Lab", loki=loki, clock=lambda t=t: t, previous=v1)
            (first,) = loki.asked[:1]
            spans.append((int(first["end"]) - int(first["start"])) // NS)
        assert len(spans) == 50 and max(spans) <= T.WINDOW_SECONDS, spans
        # Once the newest held is older than the window, every read asks exactly the window.
        late = [s for i, s in enumerate(spans, 1) if 54 * i > T.WINDOW_SECONDS + 60]
        assert late and set(late) == {T.WINDOW_SECONDS}, spans
        # Before the fix the 50th read asked from the newest held, 45 minutes and more.
        assert spans[-1] < 54 * 50

    def test_after_the_success_it_says_what_it_missed_and_the_backfill_fills_it(
            self, data, monkeypatch):
        v1 = fill()
        held_to = v1["buffer"]["lines"]["to"]
        # r3 changed its configuration twice while every read failed, 20 and 30 minutes on.
        gap = [(held_to + m * 60 * NS, CONFIG.replace("vty0", f"vty{m}")) for m in (20, 30)]
        loki = FakeLoki(CORPUS + gap)
        # One line a backfill page, so the fill is seen a read at a time.
        monkeypatch.setattr(T, "BACKFILL_LIMIT", 1)
        back = held_to / NS + 45 * 60
        v2 = T.read("Lab", loki=loki, clock=lambda: back, previous=v1)
        (first,) = loki.asked[:1]
        assert int(first["start"]) == int((back - T.WINDOW_SECONDS) * NS), "bounded on recovery"
        lines = v2["buffer"]["lines"]
        assert lines["missed"] == {"from": held_to, "to": int((back - T.WINDOW_SECONDS) * NS)}
        held = {e["ns"] for e in B.load(v2["buffer"]["store"], "r3")["lines"]}
        assert not {ns for ns, _l in gap} <= held, "the gap is not held yet: it is said"
        v, t, reads = v2, back, 1
        while "missed" in v["buffer"]["lines"] and reads < 20:
            t += 5
            v = T.read("Lab", loki=loki, clock=lambda t=t: t, previous=v)
            reads += 1
        assert "missed" not in v["buffer"]["lines"], v["buffer"]["lines"]
        # One older page a read, the two gap lines and the boundary's: a few reads, counted.
        assert 2 <= reads <= 5, reads
        held = {e["ns"] for e in B.load(v["buffer"]["store"], "r3")["lines"]}
        assert {ns for ns, _l in gap} <= held
