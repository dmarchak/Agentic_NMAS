"""jenkins_runner.py

Jenkins CI integration — triggers a real Jenkins server build and polls
for the result.  All check logic lives in the Jenkinsfile on the server;
this module only manages the connection config and result persistence.

Per-list isolation
------------------
- data/jenkins_checks.json   — server connection settings (URL, user, api_key, token)
- data/lists/{slug}/jenkins_pipelines.json — job names registered to that list
- data/lists/{slug}/jenkins_results.json   — build results for that list's jobs
"""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_CONFIG_FILE  = os.path.join(_PROJECT_ROOT, "data", "jenkins_checks.json")

_DEFAULT_CONFIG = {
    "jenkins_url":     "",
    "jenkins_token":   "",
    "jenkins_user":    "",
    "jenkins_api_key": "",
}


# ---------------------------------------------------------------------------
# Server connection config  (global — not per-list)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as fh:
            cfg = json.load(fh)
        # Strip legacy jenkins_job key if present — it is now per-list
        cfg.pop("jenkins_job", None)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        save_config(_DEFAULT_CONFIG)
        return dict(_DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


# ---------------------------------------------------------------------------
# Per-list pipeline registry
# ---------------------------------------------------------------------------

def _get_list_dir() -> str:
    """Return the data dir for the currently active device list."""
    from modules.config import get_current_list_data_dir
    return get_current_list_data_dir()


def _pipelines_file() -> str:
    return os.path.join(_get_list_dir(), "jenkins_pipelines.json")


def _results_file() -> str:
    return os.path.join(_get_list_dir(), "jenkins_results.json")


def load_list_pipelines() -> list[str]:
    """Return the job names registered to the current device list."""
    try:
        with open(_pipelines_file(), encoding="utf-8") as fh:
            return json.load(fh).get("pipelines", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_list_pipelines(jobs: list[str]) -> None:
    path = _pipelines_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Preserve any existing schedules block when re-saving
    existing = {}
    try:
        with open(path, encoding="utf-8") as fh:
            existing = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    existing["pipelines"] = jobs
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)


# ---------------------------------------------------------------------------
# Per-pipeline schedule registry
# ---------------------------------------------------------------------------

def load_pipeline_schedules() -> dict:
    """Return {job_name: cron_expression} for all scheduled pipelines in this list."""
    try:
        with open(_pipelines_file(), encoding="utf-8") as fh:
            return json.load(fh).get("schedules", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_pipeline_schedule(job_name: str, cron_expression: str) -> None:
    """
    Persist the cron schedule for a pipeline locally (alongside the pipeline registry).
    Pass an empty string to clear the schedule entry.
    """
    path = _pipelines_file()
    data: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    schedules = data.get("schedules", {})
    if cron_expression:
        schedules[job_name] = cron_expression
    else:
        schedules.pop(job_name, None)
    data["schedules"] = schedules
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def extract_schedule_from_xml(xml: str) -> str:
    """
    Parse a Jenkins config.xml and return the TimerTrigger cron expression,
    or an empty string if no schedule is set.  Handles CDATA-wrapped specs.
    """
    import re
    m = re.search(r"<hudson\.triggers\.TimerTrigger>.*?<spec>(.*?)</spec>", xml, re.DOTALL)
    if not m:
        return ""
    spec = m.group(1).strip()
    # Strip CDATA wrapper if present: <![CDATA[H/30 * * * *]]>
    cdata = re.match(r"<!\[CDATA\[(.*?)]]>", spec, re.DOTALL)
    if cdata:
        spec = cdata.group(1).strip()
    return spec


# ---------------------------------------------------------------------------
# Local Groovy script cache — one .groovy file per job per list
# ---------------------------------------------------------------------------

def _groovy_path(job_name: str) -> str:
    """Return the local path for the cached Groovy script for a job in this list."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_name)
    return os.path.join(_get_list_dir(), f"{safe}.groovy")


def save_pipeline_script(job_name: str, script: str) -> None:
    """Write the Groovy pipeline script to a local .groovy file for this list."""
    path = _groovy_path(job_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    logger.info("Saved pipeline script for '%s' → %s", job_name, path)


def load_pipeline_script(job_name: str) -> str | None:
    """Return the locally cached Groovy script for a job, or None if not cached."""
    try:
        with open(_groovy_path(job_name), encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def delete_pipeline_script(job_name: str) -> None:
    """Remove the local Groovy cache file for a job."""
    try:
        os.remove(_groovy_path(job_name))
    except FileNotFoundError:
        pass


def _extract_groovy_from_xml(xml: str) -> str | None:
    """Pull the inline Groovy script out of a Jenkins config.xml, if present."""
    import re
    m = re.search(r"<script>(.*?)</script>", xml, re.DOTALL)
    if not m:
        return None
    # Unescape XML entities
    script = m.group(1)
    script = script.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return script.strip()


def register_pipeline(job_name: str) -> None:
    """Add a Jenkins job to the current list's pipeline registry (idempotent)."""
    jobs = load_list_pipelines()
    if job_name not in jobs:
        jobs.append(job_name)
        _save_list_pipelines(jobs)
        logger.info("Registered pipeline '%s' to current list", job_name)


def unregister_pipeline(job_name: str) -> None:
    """Remove a Jenkins job from the current list's pipeline registry."""
    jobs = [j for j in load_list_pipelines() if j != job_name]
    _save_list_pipelines(jobs)
    logger.info("Unregistered pipeline '%s' from current list", job_name)


# ---------------------------------------------------------------------------
# Per-list results persistence
# ---------------------------------------------------------------------------

def load_results() -> Optional[dict]:
    """
    Load build results for the current list.

    Structure returned:
    {
        "jenkins_pending": bool,       # True if any pipeline is building
        "jenkins_ok":      bool|None,  # True if all passed, False if any failed, None if no data
        "jenkins_build":   int|None,   # build number of the most recently completed job
        "jenkins_url":     str|None,   # URL of the most recently completed build
        "pipelines": {
            "<job-name>": {
                "jenkins_build":   int,
                "jenkins_result":  str,   # SUCCESS / FAILURE / ABORTED / …
                "jenkins_ok":      bool,
                "jenkins_pending": bool,
                "jenkins_url":     str,
                "jenkins_ran_at":  str,
                "jenkins_duration": int,
            },
            ...
        }
    }
    """
    try:
        with open(_results_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def is_jenkins_building() -> bool:
    """
    Return True if any registered pipeline for the current list is currently
    pending or building.  Used to gate SSH-heavy background tasks so they don't
    compete with Jenkins for VTY lines on network devices.
    """
    try:
        data = load_results()
        if not data:
            return False
        # Top-level flag
        if data.get("jenkins_pending"):
            return True
        # Belt-and-suspenders: check each pipeline entry
        for info in data.get("pipelines", {}).values():
            if isinstance(info, dict) and info.get("jenkins_pending"):
                return True
    except Exception:
        pass
    return False


def _save_results(summary: dict) -> None:
    try:
        path = _results_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
    except Exception:
        pass


def _recompute_summary(data: dict) -> dict:
    """Re-derive top-level jenkins_ok / jenkins_pending from per-pipeline entries."""
    pipes = data.get("pipelines", {})
    if not pipes:
        data.setdefault("jenkins_ok", None)
        data.setdefault("jenkins_pending", False)
        return data

    any_pending = any(p.get("jenkins_pending") for p in pipes.values())
    all_done    = [p for p in pipes.values() if p.get("jenkins_result") is not None]
    all_ok      = all(p.get("jenkins_ok") for p in all_done) if all_done else None

    # Use the most recently completed build for the badge link
    finished = sorted(
        [p for p in pipes.values() if p.get("jenkins_ran_at")],
        key=lambda p: p.get("jenkins_ran_at", ""),
        reverse=True,
    )

    data["jenkins_pending"] = any_pending
    data["jenkins_ok"]      = all_ok
    data["jenkins_build"]   = finished[0].get("jenkins_build") if finished else None
    data["jenkins_url"]     = finished[0].get("jenkins_url")   if finished else None
    return data


# ---------------------------------------------------------------------------
# Main entry point — trigger Jenkins
# ---------------------------------------------------------------------------

def run_checks(startup_delay: float = 0.0) -> dict:
    """
    Trigger all Jenkins pipelines registered to the current device list.

    startup_delay: seconds to wait first (used after a server restart so
    the app is fully up before Jenkins starts its HTTP checks).
    """
    if startup_delay > 0:
        time.sleep(startup_delay)

    config = load_config()
    jenkins_url = config.get("jenkins_url", "").strip()

    if not jenkins_url:
        return {
            "ok":      None,
            "message": "Jenkins not configured — set jenkins_url in Settings.",
        }

    jobs = load_list_pipelines()
    if not jobs:
        return {
            "ok":      None,
            "message": (
                "No pipelines are registered to this device list. "
                "Ask the AI to create a Jenkins pipeline for this list, "
                "or use jenkins_create_job / jenkins_link_pipeline."
            ),
        }

    triggered = []
    for job in jobs:
        try:
            _trigger_jenkins(config, job)
            triggered.append(job)
        except Exception as exc:
            logger.warning("Failed to trigger '%s': %s", job, exc)

    if not triggered:
        return {
            "ok":      False,
            "message": "Failed to trigger any Jenkins pipelines — check connection settings.",
        }

    return {
        "ok":          None,
        "triggered":   True,
        "triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "triggered_jobs": triggered,
        "message": (
            f"Triggered {len(triggered)} pipeline(s) on {jenkins_url}: "
            + ", ".join(triggered)
            + ". Results will appear in the Jenkins tab once the pipeline(s) complete."
        ),
    }


def format_summary(summary: dict) -> str:
    """Return a human-readable trigger summary suitable for the AI."""
    if summary.get("triggered"):
        jobs = ", ".join(summary.get("triggered_jobs", []))
        return (
            f"Jenkins pipeline(s) triggered at {summary.get('triggered_at', '')}: {jobs}\n"
            f"{summary.get('message', '')}\n"
            "Check the Jenkins tab or the Jenkins server UI for live stage output."
        )
    if summary.get("message"):
        return summary["message"]
    return "Jenkins status unknown."


# ---------------------------------------------------------------------------
# Real Jenkins trigger + result polling
# ---------------------------------------------------------------------------

def _clear_job_pending(job_name: str) -> None:
    """Clear the pending flag for a specific job in the current list's results."""
    try:
        data = load_results() or {}
        data.setdefault("pipelines", {})
        data["pipelines"].setdefault(job_name, {})["jenkins_pending"] = False
        _recompute_summary(data)
        _save_results(data)
    except Exception:
        pass


def _poll_jenkins_build(config: dict, job_name: str, queue_url: str) -> None:
    """Background thread: poll queue → build number → result, then update saved results."""
    base_url = config.get("jenkins_url", "").rstrip("/")
    user     = config.get("jenkins_user", "")
    key      = config.get("jenkins_api_key", "")

    import urllib.request, base64

    def _req(endpoint: str) -> dict:
        full = endpoint if endpoint.startswith("http") else f"{base_url}{endpoint}"
        full = full.rstrip("/") + "/api/json"
        req  = urllib.request.Request(full)
        if user and key:
            creds = base64.b64encode(f"{user}:{key}".encode()).decode()
            req.add_header("Authorization", f"Basic {creds}")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())

    # Capture the list dir at thread-start so list switches mid-poll don't corrupt results
    list_dir = _get_list_dir()

    def _save_to_list(data: dict) -> None:
        path = os.path.join(list_dir, "jenkins_results.json")
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except Exception:
            existing = {}
        existing.setdefault("pipelines", {})
        existing["pipelines"][job_name] = data
        _recompute_summary(existing)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, indent=2)
        except Exception:
            pass

    try:
        # 1. Poll queue until the build leaves and we have a build URL
        build_url = None
        build_num = None
        for _ in range(60):           # up to ~5 minutes waiting in queue
            time.sleep(5)
            try:
                data = _req(queue_url)
                if data.get("cancelled"):
                    logger.warning("Jenkins build for '%s' was cancelled from queue", job_name)
                    _save_to_list({"jenkins_pending": False, "jenkins_result": "ABORTED", "jenkins_ok": False})
                    return
                exec_info = data.get("executable")
                if exec_info:
                    build_url = exec_info.get("url", "").rstrip("/")
                    build_num = exec_info.get("number")
                    logger.info("Jenkins '%s' build #%s started", job_name, build_num)
                    break
            except Exception as e:
                logger.debug("Queue poll error (%s): %s", job_name, e)

        if not build_url:
            logger.warning("Jenkins '%s' never left queue after 5 minutes", job_name)
            _save_to_list({"jenkins_pending": False, "jenkins_result": "TIMEOUT", "jenkins_ok": False})
            return

        # 2. Poll build until it has a result (not None)
        for _ in range(120):          # up to ~10 more minutes
            time.sleep(5)
            try:
                bdata  = _req(build_url)
                result = bdata.get("result")
                if result is not None:
                    ok = result == "SUCCESS"
                    logger.info("Jenkins '%s' #%s finished: %s", job_name, build_num, result)
                    _save_to_list({
                        "jenkins_build":    build_num,
                        "jenkins_result":   result,
                        "jenkins_ok":       ok,
                        "jenkins_pending":  False,
                        "jenkins_url":      build_url + "/",
                        "jenkins_duration": bdata.get("duration", 0),
                        "jenkins_ran_at":   time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    return
            except Exception as e:
                logger.debug("Build poll error (%s): %s", job_name, e)

        logger.warning("Jenkins '%s' polling timed out", job_name)
        _save_to_list({"jenkins_pending": False, "jenkins_result": "TIMEOUT", "jenkins_ok": False})
    except Exception as exc:
        logger.warning("Jenkins poll thread error (%s): %s", job_name, exc)
        _save_to_list({"jenkins_pending": False})


def _trigger_jenkins(config: dict, job_name: str) -> None:
    url   = config.get("jenkins_url", "").rstrip("/")
    token = config.get("jenkins_token", "")
    user  = config.get("jenkins_user", "")
    key   = config.get("jenkins_api_key", "")
    if not url or not job_name:
        return
    try:
        import urllib.request, base64, threading
        from urllib.parse import quote
        trigger = f"{url}/job/{quote(job_name)}/build"
        if token:
            trigger += f"?token={token}"
        req = urllib.request.Request(trigger, method="POST")
        if user and key:
            creds = base64.b64encode(f"{user}:{key}".encode()).decode()
            req.add_header("Authorization", f"Basic {creds}")
        resp = urllib.request.urlopen(req, timeout=10)

        # Mark build as pending in this list's results
        data = load_results() or {}
        data.setdefault("pipelines", {})
        data["pipelines"].setdefault(job_name, {}).update({
            "jenkins_pending":     True,
            "jenkins_triggered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        _recompute_summary(data)
        _save_results(data)

        queue_url = (resp.headers.get("Location") or "").rstrip("/")
        if queue_url:
            threading.Thread(
                target=_poll_jenkins_build,
                args=(config, job_name, queue_url),
                daemon=True,
            ).start()
            logger.info("Jenkins job '%s' triggered — polling queue: %s", job_name, queue_url)
        else:
            logger.info("Jenkins job '%s' triggered (no queue URL returned)", job_name)
            def _clear_after_delay():
                time.sleep(300)
                _clear_job_pending(job_name)
            threading.Thread(target=_clear_after_delay, daemon=True).start()
    except Exception as exc:
        logger.warning("Jenkins trigger failed for '%s': %s", job_name, exc)
        raise


# ---------------------------------------------------------------------------
# Jenkins API helpers — job/pipeline management
# ---------------------------------------------------------------------------

def _jenkins_auth_headers(config: dict) -> dict:
    """Return Authorization header dict for Jenkins API calls."""
    import base64
    user = config.get("jenkins_user", "")
    key  = config.get("jenkins_api_key", "")
    if user and key:
        creds = base64.b64encode(f"{user}:{key}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}
    return {}


# Per-base-URL opener cache — each opener owns a cookie jar so that the crumb
# fetch (GET /crumbIssuer/api/json) and the subsequent POST share the same
# JSESSIONID, satisfying Jenkins' CSRF protection.
_opener_cache: dict = {}   # keyed by jenkins_url → OpenerDirector


def _get_opener(config: dict):
    """
    Return (or create) a urllib OpenerDirector with a cookie jar for the given
    Jenkins base URL.  Sharing one opener per URL guarantees session continuity.
    """
    import urllib.request, http.cookiejar
    base = config.get("jenkins_url", "").rstrip("/")
    if base not in _opener_cache:
        jar    = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        _opener_cache[base] = opener
        logger.debug("Created cookie-jar opener for %s", base)
    return _opener_cache[base]


def _fetch_crumb(config: dict, opener) -> dict:
    """
    Fetch a Jenkins CSRF crumb using *opener* (shared cookie jar).
    Returns a dict ready to merge into request headers, or {} if CSRF is
    disabled or the endpoint is unreachable.
    """
    import urllib.request, urllib.error
    base = config.get("jenkins_url", "").rstrip("/")
    url  = f"{base}/crumbIssuer/api/json"
    req  = urllib.request.Request(url, headers=_jenkins_auth_headers(config))
    try:
        resp  = opener.open(req, timeout=10)
        data  = json.loads(resp.read())
        field = data.get("crumbRequestField", "Jenkins-Crumb")
        value = data.get("crumb", "")
        logger.info("Jenkins CSRF crumb fetched: %s=%.8s...", field, value)
        return {field: value}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            logger.info("Jenkins CSRF disabled (crumbIssuer 404)")
        else:
            logger.warning("Crumb fetch HTTP %s - proceeding without crumb", exc.code)
        return {}
    except Exception as exc:
        logger.warning("Crumb fetch error (%s) - proceeding without crumb", exc)
        return {}


def _jenkins_request(config: dict, path: str, method: str = "GET",
                     data: bytes | None = None,
                     content_type: str | None = None) -> tuple[int, bytes, dict]:
    """
    Make an authenticated Jenkins HTTP request.

    When an API key (token) is configured, Jenkins >= 2.96 exempts the request
    from CSRF checks entirely — sending a crumb header in that case causes a
    mismatch (500) because the crumb is tied to a browser JSESSIONID, not to
    the API token session.  We therefore skip the crumb when api_key is set.

    When no API key is present (password-based auth) we fetch a crumb using a
    shared cookie-jar opener so that the crumb and the POST share the same
    JSESSIONID.

    Returns (status_code, response_body, response_headers).
    """
    import urllib.request, urllib.error
    base   = config.get("jenkins_url", "").rstrip("/")
    url    = f"{base}{path}"
    # When using an API token, CSRF is bypassed — do NOT send a crumb header.
    using_api_token = bool(config.get("jenkins_api_key", ""))

    def _attempt(opener) -> tuple[int, bytes, dict]:
        headers = _jenkins_auth_headers(config)
        if content_type:
            headers["Content-Type"] = content_type
        if method.upper() != "GET" and not using_api_token:
            # Only fetch crumb for password-based (non-token) auth
            headers.update(_fetch_crumb(config, opener))
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = opener.open(req, timeout=30)
            return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), {}

    opener = _get_opener(config)
    status, body, hdrs = _attempt(opener)

    # On 403/500 the session may have been invalidated — reset and retry once
    if status in (403, 500) and method.upper() != "GET":
        logger.info("Jenkins returned %s on POST - resetting session and retrying", status)
        _opener_cache.pop(base, None)
        opener = _get_opener(config)
        status, body, hdrs = _attempt(opener)

    return status, body, hdrs


def get_current_list_pipeline_status(config: dict) -> dict:
    """
    Return the pipelines registered to the current device list with their
    latest build results fetched from Jenkins in a single API call.
    """
    from modules.config import get_current_list_name
    list_name  = get_current_list_name()
    registered = load_list_pipelines()

    try:
        st, body, _ = _jenkins_request(
            config,
            "/api/json?tree=jobs[name,buildable,color,lastBuild[number,result]]",
        )
        server_jobs = (
            {j["name"]: j for j in json.loads(body).get("jobs", [])}
            if st == 200 else {}
        )
    except Exception:
        server_jobs = {}

    rows = []
    for job_name in registered:
        sj = server_jobs.get(job_name, {})
        lb = sj.get("lastBuild") or {}
        rows.append({
            "job_name":         job_name,
            "exists_on_server": job_name in server_jobs,
            "buildable":        sj.get("buildable", False),
            "last_result":      lb.get("result"),
            "last_build":       lb.get("number"),
        })

    return {"list_name": list_name, "registered": rows}


def sync_scheduled_build_results() -> int:
    """
    Poll Jenkins for the latest build result of every pipeline registered to
    the current list and update jenkins_results.json.

    Called by the event monitor so that scheduled (cron-triggered) Jenkins
    builds are visible to the app even when no manual trigger was issued.

    Returns the number of jobs updated.
    """
    config     = load_config()
    base_url   = config.get("jenkins_url", "").rstrip("/")
    if not base_url:
        return 0

    registered = load_list_pipelines()
    if not registered:
        return 0

    try:
        st, body, _ = _jenkins_request(
            config,
            "/api/json?tree=jobs[name,lastBuild[number,result,timestamp,duration]]",
        )
        if st != 200:
            return 0
        server_jobs = {j["name"]: j for j in json.loads(body).get("jobs", [])}
    except Exception as exc:
        logger.debug("sync_scheduled_build_results: API error: %s", exc)
        return 0

    # Load existing results so we only overwrite jobs in this list
    try:
        path = _results_file()
        with open(path, encoding="utf-8") as fh:
            existing: dict = json.load(fh)
    except Exception:
        existing = {}

    updated = 0
    for job_name in registered:
        sj = server_jobs.get(job_name)
        if not sj:
            continue
        lb = sj.get("lastBuild") or {}
        if not lb:
            continue

        build_num = lb.get("number")
        result    = lb.get("result")        # "SUCCESS" | "FAILURE" | None (running)
        if result is None:
            result = "RUNNING"

        prev = existing.get(job_name, {})
        if prev.get("build_number") == build_num and prev.get("result") == result:
            continue   # nothing changed

        ran_at = ""
        if lb.get("timestamp"):
            ran_at = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(lb["timestamp"] / 1000),
            )

        existing[job_name] = {
            "build_number":    build_num,
            "result":          result,
            "jenkins_ok":      result == "SUCCESS",
            "jenkins_result":  result,
            "jenkins_pending": result == "RUNNING",
            "jenkins_ran_at":  ran_at,
        }
        updated += 1
        logger.debug("sync_scheduled_build_results: %s build #%s → %s", job_name, build_num, result)

    if updated:
        _save_results(existing)
        logger.info("sync_scheduled_build_results: updated %d job(s)", updated)

    return updated


def list_jenkins_jobs(config: dict) -> list[dict]:
    """Return a list of all jobs on the server: [{name, url, color, buildable}]."""
    status, body, _ = _jenkins_request(config, "/api/json?tree=jobs[name,url,color,buildable]")
    if status != 200:
        raise RuntimeError(f"Jenkins returned HTTP {status}")
    data = json.loads(body)
    return data.get("jobs", [])


def get_job_config(config: dict, job_name: str) -> str:
    """Return the raw XML config for a Jenkins job."""
    from urllib.parse import quote
    status, body, _ = _jenkins_request(config, f"/job/{quote(job_name)}/config.xml")
    if status != 200:
        raise RuntimeError(f"Jenkins returned HTTP {status} for job '{job_name}'")
    return body.decode("utf-8")


def create_jenkins_job(config: dict, job_name: str, xml_config: str) -> None:
    """Create a new Jenkins pipeline job with the given XML config."""
    from urllib.parse import quote
    data = xml_config.encode("utf-8")
    status, body, _ = _jenkins_request(
        config,
        f"/createItem?name={quote(job_name)}",
        method="POST", data=data, content_type="application/xml",
    )
    if status not in (200, 201):
        # Jenkins sometimes returns HTTP 500 even when the job was actually created
        # (known platform behaviour).  Verify by checking if the job now exists.
        logger.warning(
            "create_jenkins_job: HTTP %s for '%s' — verifying job existence...",
            status, job_name,
        )
        try:
            check_status, _, _ = _jenkins_request(
                config, f"/job/{quote(job_name)}/api/json"
            )
            if check_status == 200:
                logger.info(
                    "create_jenkins_job: job '%s' exists on server despite HTTP %s — treating as success",
                    job_name, status,
                )
            else:
                raise RuntimeError(
                    f"Create job failed (HTTP {status}): {body.decode('utf-8', errors='replace')[:500]}"
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Create job failed (HTTP {status}): {body.decode('utf-8', errors='replace')[:500]}"
            ) from exc
    # Cache the Groovy script locally so the user can see/edit the pipeline definition
    script = _extract_groovy_from_xml(xml_config)
    if script:
        save_pipeline_script(job_name, script)


def update_jenkins_job(config: dict, job_name: str, xml_config: str) -> None:
    """Update the config of an existing Jenkins job."""
    from urllib.parse import quote
    data = xml_config.encode("utf-8")
    status, body, _ = _jenkins_request(
        config,
        f"/job/{quote(job_name)}/config.xml",
        method="POST", data=data, content_type="application/xml",
    )
    if status not in (200, 201):
        err_text = body.decode('utf-8', errors='replace')
        # Jenkins sometimes returns HTTP 500 even when the update was applied
        # (known platform behaviour).  Verify by reading back the actual config.xml
        # and checking that it matches what we sent (not just that the job exists).
        if status == 500:
            logger.warning(
                "update_jenkins_job: HTTP 500 for '%s' — verifying config was applied...",
                job_name,
            )
            try:
                verify_status, verify_body, _ = _jenkins_request(
                    config, f"/job/{quote(job_name)}/config.xml"
                )
                if verify_status == 200:
                    live_xml = verify_body.decode("utf-8", errors="replace")
                    # Check that key content from our update is present in the live config.
                    # We compare a snippet — the first non-trivial line — not full equality,
                    # because Jenkins may normalise whitespace/CDATA on round-trip.
                    import re as _re
                    # Extract first <spec> value from what we sent
                    sent_spec_m = _re.search(
                        r"<hudson\.triggers\.TimerTrigger>.*?<spec>(.*?)</spec>",
                        xml_config, _re.DOTALL
                    )
                    if sent_spec_m:
                        sent_spec = sent_spec_m.group(1).strip()
                        if sent_spec in live_xml or live_xml.find(sent_spec.replace("*", "\\*")) >= 0:
                            logger.info(
                                "update_jenkins_job: '%s' trigger verified in live config after HTTP 500",
                                job_name,
                            )
                            script = _extract_groovy_from_xml(xml_config)
                            if script:
                                save_pipeline_script(job_name, script)
                            return
                        else:
                            logger.error(
                                "update_jenkins_job: HTTP 500 for '%s' and trigger NOT found in live config — update failed",
                                job_name,
                            )
                    else:
                        # Not a trigger update — just verify the job is accessible
                        logger.info(
                            "update_jenkins_job: '%s' accessible after HTTP 500 — treating non-trigger update as success",
                            job_name,
                        )
                        script = _extract_groovy_from_xml(xml_config)
                        if script:
                            save_pipeline_script(job_name, script)
                        return
            except Exception as verify_exc:
                logger.warning("update_jenkins_job: verification fetch failed: %s", verify_exc)
        logger.error(
            "update_jenkins_job: HTTP %s for '%s'\nXML sent:\n%s\nJenkins response:\n%s",
            status, job_name, xml_config[:3000], err_text[:3000],
        )
        raise RuntimeError(
            f"Update job failed (HTTP {status}): {err_text[:2000]}"
        )
    # Update the local Groovy cache to stay in sync
    script = _extract_groovy_from_xml(xml_config)
    if script:
        save_pipeline_script(job_name, script)


def delete_jenkins_job(config: dict, job_name: str) -> None:
    """Delete a Jenkins job permanently."""
    from urllib.parse import quote
    status, body, _ = _jenkins_request(
        config, f"/job/{quote(job_name)}/doDelete", method="POST",
    )
    if status not in (200, 201, 302):
        raise RuntimeError(
            f"Delete job failed (HTTP {status}): {body.decode('utf-8', errors='replace')[:300]}"
        )
    # Remove local Groovy cache
    delete_pipeline_script(job_name)


def get_job_builds(config: dict, job_name: str, limit: int = 10) -> list[dict]:
    """Return recent builds for a job: [{number, result, timestamp, duration, url}]."""
    from urllib.parse import quote
    path = (
        f"/job/{quote(job_name)}/api/json"
        f"?tree=builds[number,result,timestamp,duration,url]{{0,{limit}}}"
    )
    status, body, _ = _jenkins_request(config, path)
    if status != 200:
        raise RuntimeError(f"Jenkins returned HTTP {status}")
    return json.loads(body).get("builds", [])


def delete_build(config: dict, job_name: str, build_number: int) -> None:
    """Delete a specific build from a Jenkins job by build number."""
    from urllib.parse import quote
    status, body, _ = _jenkins_request(
        config,
        f"/job/{quote(job_name)}/{build_number}/doDelete",
        method="POST",
    )
    if status not in (200, 201, 302, 404):
        raise RuntimeError(
            f"Delete build #{build_number} failed (HTTP {status}): "
            f"{body.decode('utf-8', errors='replace')[:300]}"
        )


def get_build_console(config: dict, job_name: str,
                      build_number: int | str | None = None) -> str:
    """
    Fetch the plain-text console log for a Jenkins build.

    build_number: specific build number, or None / 'last' for the most recent build,
                  or 'lastFailed' for the most recent failed build.
    """
    from urllib.parse import quote
    jname = quote(job_name)
    if build_number is None or str(build_number).lower() == "last":
        segment = "lastBuild"
    elif str(build_number).lower() in ("lastfailed", "last_failed", "failed"):
        segment = "lastFailedBuild"
    else:
        segment = str(int(build_number))

    status, body, _ = _jenkins_request(
        config, f"/job/{jname}/{segment}/consoleText"
    )
    if status == 404:
        raise RuntimeError(
            f"No build found for '{job_name}' (segment={segment}). "
            "Check the job name and build number."
        )
    if status != 200:
        raise RuntimeError(f"Jenkins returned HTTP {status} fetching console log")
    return body.decode("utf-8", errors="replace")


def wait_for_build_results(config: dict, timeout: int = 600,
                           stop_check=None) -> dict:
    """
    Block until all pending pipelines for the current list finish building,
    then return per-job results.  Console output is fetched automatically for
    any job that failed.

    Returns:
        {
          "timed_out": bool,
          "jobs": {
              "<job-name>": {
                  "result":   str,   # SUCCESS / FAILURE / ABORTED / TIMEOUT / UNKNOWN
                  "ok":       bool,
                  "build":    int|None,
                  "url":      str|None,
                  "console":  str|None,   # present only on failure
              }
          }
        }
    """
    jobs = load_list_pipelines()
    if not jobs:
        return {"error": "No pipelines registered to this list.", "jobs": {}}

    deadline  = time.time() + timeout
    timed_out = False

    while True:
        data  = load_results() or {}
        pipes = data.get("pipelines", {})
        # A job is "pending" if it has no result yet OR its pending flag is True
        still_pending = [
            j for j in jobs
            if pipes.get(j, {}).get("jenkins_pending", False)
            or pipes.get(j, {}).get("jenkins_result") is None
        ]
        if not still_pending:
            break
        if time.time() >= deadline:
            timed_out = True
            break
        if stop_check and stop_check():
            timed_out = True
            break
        # Sleep in short increments so stop_check is checked frequently
        for _ in range(5):
            time.sleep(1)
            if stop_check and stop_check():
                timed_out = True
                break

    # Collect final results
    data  = load_results() or {}
    pipes = data.get("pipelines", {})
    output = {}

    for job in jobs:
        p      = pipes.get(job, {})
        result = p.get("jenkins_result") or ("PENDING" if p.get("jenkins_pending") else "UNKNOWN")
        ok     = bool(p.get("jenkins_ok", False))
        entry  = {
            "result": result,
            "ok":     ok,
            "build":  p.get("jenkins_build"),
            "url":    p.get("jenkins_url"),
        }
        # Auto-fetch console for failed / non-passing builds
        if not ok and result not in ("UNKNOWN", "PENDING"):
            try:
                build_num = p.get("jenkins_build")
                log = get_build_console(config, job,
                                        build_number=build_num if build_num else "last")
                # Keep the tail — failures always appear at the end
                if len(log) > 12000:
                    log = f"[truncated — showing last 12000 of {len(log)} chars]\n\n" + log[-12000:]
                entry["console"] = log
            except Exception as exc:
                entry["console"] = f"[Could not fetch console: {exc}]"
        output[job] = entry

    return {"timed_out": timed_out, "jobs": output}


def enable_jenkins_job(config: dict, job_name: str) -> None:
    """Enable (un-disable) a Jenkins job."""
    from urllib.parse import quote
    status, body, _ = _jenkins_request(
        config, f"/job/{quote(job_name)}/enable", method="POST",
    )
    if status not in (200, 201, 302):
        raise RuntimeError(f"Enable job failed (HTTP {status})")


def disable_jenkins_job(config: dict, job_name: str) -> None:
    """Disable a Jenkins job (builds will be blocked)."""
    from urllib.parse import quote
    status, body, _ = _jenkins_request(
        config, f"/job/{quote(job_name)}/disable", method="POST",
    )
    if status not in (200, 201, 302):
        raise RuntimeError(f"Disable job failed (HTTP {status})")
