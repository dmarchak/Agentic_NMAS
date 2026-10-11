"""History › Query (C667; board A, AskLibrary, on the canvas page "History, Query"): ask the
network's history, starting from a question.

What the landing draws: what the history holds (the metrics' live store and whether a
long-term store answers past it, the logs' retention and the store's first day, each from
the setting or the reader that knows it, never assumed), and the ready-made questions, each
either opening its answer or said "not built yet". The board's saved views and "Ask your
own" are a later step of C667, said on the page as such.
"""

import logging

log = logging.getLogger(__name__)

#: The board's six ready-made questions, in its order: (key, title, what it answers, source).
#: A question opens its answer when `ANSWERS` names its route; the rest are said "not built
#: yet", never drawn as a link that goes nowhere.
QUESTIONS = (
    ("errors", "Interface errors and discards over time",
     "Which interfaces drop or corrupt packets, and since when", "metrics · per interface"),
    ("cpu", "CPU and memory trend", "Is a device getting busier, week on week",
     "metrics · per device"),
    ("neighbours", "Routing neighbour changes", "When OSPF and BGP neighbours went up and down",
     "metrics · per neighbour"),
    ("syslog", "Syslog by device",
     "Lines by severity and mnemonic, each device's lines one click away", "logs · per line"),
    ("restarts", "Restarts", "Each restart, planned or not, with its window",
     "metrics and logs"),
    ("telemetry", "Telemetry rates", "Is each device still streaming, and how much",
     "metrics · per device"),
)
#: The questions built, by the route that answers each.
ANSWERS = {"syslog": "v2.history_query_syslog"}


def _setting(list_name: str, key: str, default):
    from modules.list_settings import value
    try:
        return value(list_name, key, default)
    except Exception as exc:                          # noqa: BLE001
        log.warning("history query: %s could not be read for %s: %s", key, list_name, exc)
        return default


def coverage(list_name: str) -> dict:
    """What the history holds, each part from where it is known."""
    from modules import logs_page

    live = int(_setting(list_name, "metrics_live_retention_days", 90) or 90)
    long_term = bool((_setting(list_name, "grafana_history_datasource_uid", "") or "").strip())
    logs_days = int(_setting(list_name, "logs_retention_days", 90) or 90)
    st = logs_page.stored(list_name)
    value = st.get("value") or {}
    return {"metrics_live_days": live, "metrics_long_term": long_term,
            "logs_days": logs_days, "logs_state": st.get("state"),
            "logs_first_day": value.get("first_day", ""), "read_at": st.get("value_at", "")}


def library(list_name: str) -> dict:
    """The landing: the coverage, and each question with where it opens (or not yet)."""
    from flask import url_for

    qs = []
    for key, title, what, source in QUESTIONS:
        route = ANSWERS.get(key)
        qs.append({"key": key, "title": title, "what": what, "source": source,
                   "url": url_for(route) if route else ""})
    return {"coverage": coverage(list_name), "questions": qs, "list": list_name}
