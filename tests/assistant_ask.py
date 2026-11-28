"""The assistant chat's press, for tests (the chat, 2026-11-28: Send starts a job and answers at
once with its turn; routes/assistant_v2.ask, modules/ai/assistant_turns.py). Not a test module.

`ask(client, data, ...)` posts the question as a page's Send does, waits for the turn's job by
its id (`capture_job.wait`, never a sleep), then reads the turn as the panel re-reads it
(``GET /v2/assistant/turn/<id>``) and returns that response: what a person sees once the answer
is drawn. A question refused at once (empty, too long) or a refused press is answered by the
post itself, which is returned as it is.
"""
import re

#: The longest a test waits for one turn's job: the fake provider answers at once, so a turn
#: ends in well under a second; 30 s is far past it, and a job that hangs fails by name.
WAIT_S = 30


def turn_id(body: str) -> str:
    m = re.search(r'id="asst-turn-(t-[0-9a-f]{16})"', body)
    return m.group(1) if m else ""


def wait_all(timeout: float = WAIT_S) -> None:
    """Every assistant job still running in this process, ended (or the wait fails)."""
    from modules.ai import assistant_turns
    from modules.nsot import capture_job

    with capture_job._lock:
        jobs = [k for k, v in capture_job._jobs.items()
                if v["kind"] == assistant_turns.KIND and v["state"] == "running"]
    for job in jobs:
        assert capture_job.wait(job, timeout), f"the assistant's job {job} did not end in {timeout} s"


def ask(client, data: dict, query_string=None, headers=None):
    """The press and its drawn turn: the turn's response once its job ended, else the post's."""
    r = client.post("/v2/assistant/ask", data=data, query_string=query_string,
                    headers=headers or {})
    body = r.get_data(as_text=True)
    turn = turn_id(body)
    if r.status_code != 200 or not turn or 'data-turn-state="working"' not in body:
        return r
    wait_all()
    return client.get(f"/v2/assistant/turn/{turn}", query_string=query_string,
                      headers=headers or {})
