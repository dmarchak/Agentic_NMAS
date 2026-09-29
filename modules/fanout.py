"""Reads across devices, at once (the operator's standing rule, 2026-09-29).

READS across devices run concurrently by default; a serial read loop is a
defect unless it states why (CLAUDE.md, the Stage 7 plan section 2 item 7,
`tests/test_device_loops_state_why.py`). This is the one helper the
conversions use, so each read loop does not grow its own pool.

- Results come back in the ITEMS' order, whatever order the reads finish in,
  so a caller's output reads the same as the serial loop's did.
- A read that raises is that item's result alone (``Failed``), never the
  whole run's: one unreachable device must not hide the other eight.
- Bounded (`MAX_WORKERS`, a cap and not a measured optimum, the capture
  read's): a large list never opens every session at once.

WRITES do not use this. A write across devices runs concurrently only where
nothing depends on order, and the deploy batch is sequential on purpose (its
circuit breaker): the ordering is the safety.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, List, NamedTuple

log = logging.getLogger(__name__)

#: The same cap as the capture's reads (C188): one worker per device at the
#: fleet's size, bounded so a large list does not open every session at once.
MAX_WORKERS = 16


class Failed(NamedTuple):
    """One item's read raised: the exception, kept for the caller to report."""
    error: BaseException

    def __str__(self) -> str:
        return f"{type(self.error).__name__}: {self.error}"


def read_each(fn: Callable[[Any], Any], items: Iterable, *, name: str = "read",
              max_workers: int = MAX_WORKERS) -> List[Any]:
    """``[fn(item) or Failed(exc)]`` for every item, concurrently, in the items'
    order. *name* labels the threads, so a stack dump says what was running."""
    items = list(items)
    if not items:
        return []

    def one(item):
        try:
            return fn(item)
        except Exception as exc:              # noqa: BLE001
            log.debug("%s: one item failed: %s", name, exc)
            return Failed(exc)

    workers = max(1, min(max_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name) as pool:
        return list(pool.map(one, items))
