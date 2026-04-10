"""ai_assistant.py

Multi-provider AI integration for network device management.

Supports Anthropic (Claude), Groq (Llama), and Ollama (local models).
The active provider is stored in data/provider_config.json and can be
switched at runtime via the UI without restarting the server.

Chat history is stored in Anthropic message format internally and
converted to the appropriate format for each provider at call time.
History is persisted to data/chat_histories/<session_id>.json.
"""

import hashlib
import json
import logging
import os
import time
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Debug log — written to data/ai_debug.log for diagnosing AI behaviour issues.
# Tracks what context/constraints are sent to the model each turn.
# ---------------------------------------------------------------------------
_DEBUG_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "ai_debug.log"
)

def _dbg(*args) -> None:
    """Append a timestamped debug line to ai_debug.log."""
    try:
        os.makedirs(os.path.dirname(_DEBUG_LOG_PATH), exist_ok=True)
        line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + "  ".join(str(a) for a in args)
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as _f:
            _f.write(line + "\n")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------
_PROVIDER_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "provider_config.json"
)

# Default configs for each provider.
PROVIDER_DEFAULTS = {
    "anthropic": {
        "name":              "Claude Sonnet",
        "model":             "claude-sonnet-4-6",
        "max_tokens_per_req": 8192,
        "max_history":        20,
        "inject_topo":        "always",
        "price": {
            "input": 3.00, "output": 15.00,
            "cache_write": 3.75, "cache_read": 0.30,
        },
    },
    "anthropic_opus": {
        "name":              "Claude Opus",
        "model":             "claude-opus-4-6",
        "max_tokens_per_req": 8192,
        "max_history":        20,
        "inject_topo":        "always",
        "price": {
            "input": 15.00, "output": 75.00,
            "cache_write": 18.75, "cache_read": 1.50,
        },
    },
}



_provider_config: Optional[dict] = None


def _load_provider_config() -> dict:
    global _provider_config
    if _provider_config is not None:
        return _provider_config
    if os.path.exists(_PROVIDER_CONFIG_FILE):
        try:
            with open(_PROVIDER_CONFIG_FILE, "r", encoding="utf-8") as f:
                _provider_config = json.load(f)
            return _provider_config
        except Exception as exc:
            logger.warning("Could not load provider config: %s", exc)
    _provider_config = {"active": "anthropic", "overrides": {}}
    return _provider_config


def _save_provider_config() -> None:
    os.makedirs(os.path.dirname(_PROVIDER_CONFIG_FILE), exist_ok=True)
    try:
        with open(_PROVIDER_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_provider_config, f, indent=2)
    except Exception as exc:
        logger.warning("Could not save provider config: %s", exc)


def get_active_provider() -> str:
    return _load_provider_config().get("active", "anthropic")


def set_active_provider(provider: str, model: Optional[str] = None) -> None:
    cfg = _load_provider_config()
    if provider not in PROVIDER_DEFAULTS:
        raise ValueError(f"Unknown provider: {provider}")
    cfg["active"] = provider
    if model:
        cfg.setdefault("overrides", {})[provider] = {"model": model}
    _save_provider_config()


def get_provider_info(provider: Optional[str] = None) -> dict:
    """Return merged config for a provider (defaults + any user overrides)."""
    if provider is None:
        provider = get_active_provider()
    base = dict(PROVIDER_DEFAULTS.get(provider, {}))
    overrides = _load_provider_config().get("overrides", {}).get(provider, {})
    base.update(overrides)
    base["id"] = provider
    return base


def list_providers() -> list:
    """Return info for all providers with env-key availability status."""
    result = []
    for pid in PROVIDER_DEFAULTS:
        info = get_provider_info(pid)
        info["active"] = (pid == get_active_provider())
        info["available"] = _provider_available(pid)
        result.append(info)
    return result


def _provider_available(provider: str) -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Chat history persistence
# ---------------------------------------------------------------------------
_HISTORIES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "chat_histories"
)
os.makedirs(_HISTORIES_DIR, exist_ok=True)

# Persistent lab notes and network KB are stored per device-list.
# Use _get_lab_notes_file() / _get_network_kb_file() at call time —
# never cache these paths at import time so list-switching works correctly.

def _get_lab_notes_file() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "lab_notes.md")


def _get_network_kb_file() -> str:
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "network_kb.json")


def _load_network_kb() -> dict:
    """Return the full knowledge base dict, or {} if none exists."""
    try:
        with open(_get_network_kb_file(), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_network_kb(kb: dict) -> None:
    try:
        with open(_get_network_kb_file(), "w", encoding="utf-8") as fh:
            json.dump(kb, fh, indent=2)
    except Exception as exc:
        logger.warning("Could not save network KB: %s", exc)


def _format_network_kb(kb: dict) -> str:
    """Render the KB as a compact readable block for context injection."""
    if not kb:
        return ""
    lines = []
    for category, entries in sorted(kb.items()):
        lines.append(f"[{category}]")
        if isinstance(entries, dict):
            for k, v in sorted(entries.items()):
                if isinstance(v, dict):
                    ts  = v.get("updated", "")
                    val = v.get("value", "")
                    lines.append(f"  {k}: {val}" + (f"  (updated {ts})" if ts else ""))
                else:
                    lines.append(f"  {k}: {v}")
        elif isinstance(entries, list):
            for item in entries:
                lines.append(f"  - {item}")
        else:
            lines.append(f"  {entries}")
    return "\n".join(lines)


# Per-session progress checkpoints — the last meaningful text Claude produced
# for a session, saved after every agentic loop iteration that includes prose.
# Injected on "continue" so Claude doesn't re-verify already-gathered state.
_CHECKPOINTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "checkpoints")
os.makedirs(_CHECKPOINTS_DIR, exist_ok=True)


def _checkpoint_path(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum() or c in "_-")
    return os.path.join(_CHECKPOINTS_DIR, f"{safe}.json")


def _save_checkpoint(session_id: str, task: str, progress: str, iteration: int) -> None:
    """Persist the latest progress note for a session."""
    try:
        data = {
            "task":      task,
            "progress":  progress,
            "iteration": iteration,
            "saved_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(_checkpoint_path(session_id), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def _load_checkpoint(session_id: str) -> dict:
    """Return the saved checkpoint for a session, or {}."""
    try:
        with open(_checkpoint_path(session_id), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _clear_checkpoint(session_id: str) -> None:
    """Delete the checkpoint when a session starts fresh (not a continuation)."""
    try:
        os.remove(_checkpoint_path(session_id))
    except FileNotFoundError:
        pass

# ---------------------------------------------------------------------------
# Ansible playbook store — paths are resolved at call time, not import time,
# so switching device lists automatically scopes playbooks correctly.
# ---------------------------------------------------------------------------

def _get_playbooks_dir() -> str:
    from modules.config import get_current_list_data_dir
    path = os.path.join(get_current_list_data_dir(), "playbooks")
    os.makedirs(path, exist_ok=True)
    return path


def _get_playbooks_index() -> str:
    return os.path.join(_get_playbooks_dir(), "index.json")


def _load_playbook_index() -> list:
    """Return the list of saved playbook metadata dicts."""
    try:
        with open(_get_playbooks_index(), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_playbook_index(index: list) -> None:
    # Deduplicate by name (case-insensitive) before persisting,
    # keeping the LAST occurrence so that re-saves always overwrite.
    seen: dict = {}
    deduped = []
    for pb in index:
        key = pb.get("name", "").lower().strip()
        if key in seen:
            deduped[seen[key]] = pb  # overwrite older entry with newer one
        else:
            seen[key] = len(deduped)
            deduped.append(pb)
    with open(_get_playbooks_index(), "w", encoding="utf-8") as fh:
        json.dump(deduped, fh, indent=2)


def _upsert_playbook(pb: dict) -> tuple:
    """
    Insert or update a playbook in the index by name (case-insensitive).
    If a playbook with the same name already exists, overwrite it in-place
    (preserving its original 'id' so existing references keep working).
    Returns (index, pb_id, is_update).
    """
    index = _load_playbook_index()
    name_lower = pb.get("name", "").lower().strip()
    for i, existing in enumerate(index):
        if existing.get("name", "").lower().strip() == name_lower:
            # Overwrite in-place; keep the original id so run_ansible_playbook
            # references from previous sessions continue to work.
            pb["id"] = existing["id"]
            # Update the YAML file for this playbook
            yaml_path = os.path.join(_get_playbooks_dir(), f"{existing['id']}.yml")
            try:
                with open(yaml_path, "w", encoding="utf-8") as fh:
                    fh.write(_playbook_to_yaml(pb))
            except Exception:
                pass
            index[i] = pb
            _save_playbook_index(index)
            return index, pb["id"], True
    # New playbook — assign a fresh id
    suffix = str(int(time.time() * 1000))[-5:]
    pb_id = f"{_slug(pb.get('name', 'playbook'))}_{suffix}"
    pb["id"] = pb_id
    yaml_path = os.path.join(_get_playbooks_dir(), f"{pb_id}.yml")
    try:
        with open(yaml_path, "w", encoding="utf-8") as fh:
            fh.write(_playbook_to_yaml(pb))
    except Exception:
        pass
    index.append(pb)
    _save_playbook_index(index)
    return index, pb_id, False


def _slug(name: str) -> str:
    """Convert a human name to a safe filename slug."""
    import re as _re
    s = _re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_")
    return s[:60] or "playbook"


def _playbook_to_yaml(pb: dict) -> str:
    """
    Render a playbook dict to a human-readable YAML string.
    Each play targets a single device.  The play's 'mode' field is preserved
    as a comment and drives which Ansible module is used:
      - mode 'config' (default) → cisco.ios.ios_config (enter configure terminal)
      - mode 'enable'           → cisco.ios.ios_command (exec/enable mode, no config terminal)
    """
    lines = [
        "---",
        f"# Playbook: {pb.get('name', '')}",
        f"# Description: {pb.get('description', '')}",
        f"# Created: {pb.get('created_at', '')}",
        f"# Keywords: {', '.join(pb.get('keywords', []))}",
        "",
    ]
    for play in pb.get("plays", []):
        hostname = play.get("hostname") or play.get("device_ip", "")
        device_ip = play.get("device_ip", "")
        cmds = play.get("commands", [])
        play_mode = play.get("mode", "config")
        lines += [
            f"- name: \"{'Execute on' if play_mode == 'enable' else 'Apply configuration to'} {hostname}\"",
            f"  hosts: \"{device_ip}\"",
            "  gather_facts: false",
            "  vars:",
            "    ansible_network_os: ios",
            "    ansible_connection: network_cli",
            f"  # mode: {play_mode}",
            "  tasks:",
            f"    - name: \"{pb.get('name', 'Configure device')}\"",
        ]
        if play_mode == "enable":
            lines.append("      cisco.ios.ios_command:")
            lines.append("        commands:")
        else:
            lines.append("      cisco.ios.ios_config:")
            lines.append("        lines:")
        for cmd in cmds:
            lines.append(f"          - \"{cmd}\"")
        lines.append("")
    return "\n".join(lines)


def _deduplicate_playbook_index() -> int:
    """
    Remove duplicate playbook entries (same name, case-insensitive) from the
    index, keeping only the most recently created entry for each name.
    Returns the number of duplicates removed.
    """
    index = _load_playbook_index()
    seen: dict = {}  # name_lower -> position in 'kept' list
    kept = []
    for pb in index:
        key = pb.get("name", "").lower().strip()
        if key in seen:
            # Remove the older entry; replace with this newer one
            kept[seen[key]] = pb
        else:
            seen[key] = len(kept)
            kept.append(pb)
    removed = len(index) - len(kept)
    if removed:
        _save_playbook_index(kept)
    return removed


def match_playbook(user_message: str) -> Optional[dict]:
    """
    Return the best-matching playbook for user_message, or None if no good match.
    Scoring: count how many keywords appear in the lowercased user message.
    Threshold: at least 2 keyword matches AND >= 40% keyword coverage.
    """
    index = _load_playbook_index()
    if not index:
        return None
    msg_lower = user_message.lower()
    best_score = 0.0
    best_pb = None
    for pb in index:
        keywords = [kw.lower() for kw in pb.get("keywords", [])]
        if not keywords:
            continue
        matches = sum(1 for kw in keywords if kw in msg_lower)
        score = matches / max(len(keywords), 1)
        if matches >= 2 and score >= 0.4 and score > best_score:
            best_score = score
            best_pb = pb
    return best_pb


# Project root — used for safe file access by the self-repair tools.
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# Paths (relative to project root) Claude is allowed to read.
_APP_READ_WHITELIST = {"modules", "templates", "static"}
_APP_READ_ROOT_FILES = {"app.py", "requirements.txt", "telnetlib.py", "Jenkinsfile"}

# Paths Claude is allowed to patch (write).  More restrictive than read.
_APP_WRITE_WHITELIST = {"modules", "templates"}
_APP_WRITE_ROOT_FILES = {"app.py"}

# Files that must never be written regardless of path.
_APP_WRITE_DENIED = {".env", "data/provider_config.json"}


def _load_lab_notes() -> str:
    """Return current lab notes content, or empty string if none exist."""
    try:
        with open(_get_lab_notes_file(), encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return ""


def _append_lab_note(note: str) -> str:
    """Append a timestamped note to the current list's lab_notes.md."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        line = f"- [{timestamp}] {note.strip()}\n"
        with open(_get_lab_notes_file(), "a", encoding="utf-8") as fh:
            fh.write(line)
        return f"Note saved: {note.strip()}"
    except Exception as exc:
        return f"Error saving note: {exc}"


def _history_path(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum() or c in "_-")
    return os.path.join(_HISTORIES_DIR, f"{safe}.json")


def _load_history_from_disk(session_id: str) -> list:
    path = _history_path(session_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load chat history for %s: %s", session_id, exc)
    return []


def _save_history_to_disk(session_id: str, history: list) -> None:
    path = _history_path(session_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Could not save chat history for %s: %s", session_id, exc)


# ---------------------------------------------------------------------------
# Lazy API clients
# ---------------------------------------------------------------------------
_anthropic_client = None
def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client




# ---------------------------------------------------------------------------
# Tool result cache  (TTL-based, per tool name)
# ---------------------------------------------------------------------------
_tool_cache: dict = {}

_TOOL_TTL: dict = {
    "get_all_devices":                    60,
    "execute_command":                   120,
    "execute_commands_on_device":        None,
    "execute_command_on_multiple_devices": 120,
    "get_running_config":                300,
    "get_network_topology":              600,
    "backup_device_config":              None,
    "git_commit":                        None,
    "save_ansible_playbook":             None,
    "list_ansible_playbooks":             30,
    "run_ansible_playbook":              None,
    "run_jenkins_checks":                None,
    "jenkins_wait_for_result":           None,
    "jenkins_get_current_pipelines":      30,
    "jenkins_list_jobs":                  30,
    "jenkins_get_pipeline_script":        60,
    "jenkins_get_config":                 60,
    "jenkins_create_job":                None,
    "jenkins_update_job":                None,
    "jenkins_delete_job":                None,
    "jenkins_get_builds":                 60,
    "jenkins_get_console":                30,
    "jenkins_enable_job":                None,
    "jenkins_disable_job":               None,
    "jenkins_link_pipeline":             None,
    "jenkins_unlink_pipeline":           None,
}


def _cache_key(tool_name: str, args: dict) -> str:
    raw = tool_name + json.dumps(args, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(tool_name: str, args: dict) -> Optional[str]:
    ttl = _TOOL_TTL.get(tool_name)
    if ttl is None or args.get("mode") == "config":
        return None
    key = _cache_key(tool_name, args)
    entry = _tool_cache.get(key)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    return None


def _cache_set(tool_name: str, args: dict, result: str) -> None:
    ttl = _TOOL_TTL.get(tool_name)
    if ttl is None or args.get("mode") == "config":
        return
    _tool_cache[_cache_key(tool_name, args)] = (result, time.monotonic() + ttl)


# ---------------------------------------------------------------------------
# Running-config cache (change-time aware, persisted to disk)
# ---------------------------------------------------------------------------
_CONFIG_CACHE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "config_cache"
)
os.makedirs(_CONFIG_CACHE_DIR, exist_ok=True)
_config_cache: dict = {}


def _config_cache_path(ip: str) -> str:
    return os.path.join(_CONFIG_CACHE_DIR, f"{ip.replace('.','_')}.json")


def _config_cache_load(ip: str) -> Optional[dict]:
    if ip in _config_cache:
        return _config_cache[ip]
    path = _config_cache_path(ip)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                entry = json.load(fh)
            _config_cache[ip] = entry
            return entry
        except Exception:
            pass
    return None


def _config_cache_save(ip: str, change_time: str, config: str) -> None:
    entry = {"change_time": change_time, "config": config, "fetched_at": time.time()}
    _config_cache[ip] = entry
    try:
        with open(_config_cache_path(ip), "w", encoding="utf-8") as fh:
            json.dump(entry, fh, ensure_ascii=False)
    except Exception:
        pass


def invalidate_config_cache(ip: str) -> None:
    _config_cache.pop(ip, None)
    path = _config_cache_path(ip)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Topology cache (5-min TTL, persisted to disk)
# ---------------------------------------------------------------------------
_TOPOLOGY_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "topology_cache.json"
)
_TOPOLOGY_TTL = 3600  # 1 hour — topology rarely changes; Claude triggers refresh when needed


def _topology_cache_load() -> Optional[dict]:
    if not os.path.exists(_TOPOLOGY_CACHE_FILE):
        return None
    try:
        with open(_TOPOLOGY_CACHE_FILE, "r", encoding="utf-8") as fh:
            entry = json.load(fh)
        if time.time() - entry.get("fetched_at", 0) < _TOPOLOGY_TTL:
            return entry["topology"]
    except Exception:
        pass
    return None


def _topology_cache_save(topology: dict) -> None:
    try:
        with open(_TOPOLOGY_CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"fetched_at": time.time(), "topology": topology}, fh)
    except Exception:
        pass


def invalidate_topology_cache() -> None:
    if os.path.exists(_TOPOLOGY_CACHE_FILE):
        try:
            os.remove(_TOPOLOGY_CACHE_FILE)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------
_MAX_STORED_TOOL_RESULT = 4000  # chars kept per tool result when compressing OLD history


def _sanitize_for_api(messages: list) -> list:
    """Drop orphaned tool_result messages (no matching preceding tool_use)."""
    sanitized = []
    for msg in messages:
        is_tool_result_msg = (
            msg.get("role") == "user"
            and isinstance(msg.get("content"), list)
            and any(b.get("type") == "tool_result" for b in msg["content"])
        )
        if is_tool_result_msg:
            if sanitized and sanitized[-1].get("role") == "assistant":
                prev = sanitized[-1].get("content", [])
                if isinstance(prev, list) and any(
                    b.get("type") == "tool_use" for b in prev
                ):
                    sanitized.append(msg)
        else:
            sanitized.append(msg)
    return sanitized


def _sanitize_trailing_tool_use(messages: list) -> list:
    """
    Scan the entire history for assistant messages whose tool_use calls are not
    immediately followed by a user message containing matching tool_result blocks.
    Injects synthetic tool_results wherever gaps are found so the API never sees
    an unmatched tool_use block.

    This handles both the trailing case (interrupted mid-task) and any mid-history
    corruption that can arise from session resumption or concurrent writes.
    """
    if not messages:
        return messages

    result = []
    for i, msg in enumerate(messages):
        result.append(msg)
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]
        if not tool_use_blocks:
            continue

        # Collect tool_use IDs that already have a result in the next message
        next_msg = messages[i + 1] if i + 1 < len(messages) else None
        covered_ids: set = set()
        if (
            next_msg
            and next_msg.get("role") == "user"
            and isinstance(next_msg.get("content"), list)
        ):
            for b in next_msg["content"]:
                if b.get("type") == "tool_result":
                    covered_ids.add(b.get("tool_use_id"))

        # Inject synthetic results for any uncovered tool_use IDs
        missing = [b for b in tool_use_blocks if b.get("id") not in covered_ids]
        if missing:
            synthetic_results = [
                {
                    "type":        "tool_result",
                    "tool_use_id": b["id"],
                    "content":     "[Task was interrupted before this tool completed — please re-run if needed]",
                }
                for b in missing
            ]
            result.append({"role": "user", "content": synthetic_results})
            logger.info(
                "Injected %d synthetic tool_result(s) to repair history at index %d",
                len(synthetic_results), i,
            )

    return result


_CONTEXT_SENTINEL = "\n\n"  # separator written between prefix block and user message


def _compress_history(history: list) -> list:
    """
    Compress history to minimise tokens on subsequent API calls.
    Only trims oversized tool_result blocks — does NOT touch the first user
    message so Claude retains its device/topology context across all turns.
    """
    compressed = []
    for msg in history:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            new_blocks = []
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    c = block.get("content", "")
                    if len(c) > _MAX_STORED_TOOL_RESULT:
                        block = dict(block)
                        block["content"] = (
                            c[:_MAX_STORED_TOOL_RESULT]
                            + f"\n...[{len(c) - _MAX_STORED_TOOL_RESULT}c omitted]"
                        )
                new_blocks.append(block)
            msg = dict(msg, content=new_blocks)
        compressed.append(msg)
    return compressed


def _compress_for_disk(history: list) -> list:
    """
    Like _compress_history but also strips the [Devices]/[Topology] prefix
    from the first user message before writing to disk, since those blocks
    are re-injected fresh on every session load and don't need to be stored.
    """
    compressed = _compress_history(history)
    if not compressed:
        return compressed

    first = compressed[0]
    if first.get("role") == "user" and isinstance(first.get("content"), str):
        content = first["content"]
        if _CONTEXT_SENTINEL in content:
            user_question = content.rsplit(_CONTEXT_SENTINEL, 1)[-1].strip()
            if user_question:
                compressed[0] = dict(first, content=user_question)

    return compressed


# ---------------------------------------------------------------------------
# Per-session state
# ---------------------------------------------------------------------------
_chat_histories: dict = {}
_stop_flags: dict = {}


def get_history(session_id: str) -> list:
    if session_id not in _chat_histories:
        _chat_histories[session_id] = _load_history_from_disk(session_id)
    return list(_chat_histories[session_id])


def clear_history(session_id: str) -> None:
    _chat_histories.pop(session_id, None)
    _tool_cache.clear()
    path = _history_path(session_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def stop_session(session_id: str) -> None:
    _stop_flags[session_id] = True


def _is_stopped(session_id: str) -> bool:
    return bool(_stop_flags.get(session_id, False))


def _clear_stop(session_id: str) -> None:
    _stop_flags.pop(session_id, None)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """[v3] You are an expert network automation assistant embedded in a \
Cisco IOS device management platform. You have direct SSH access to managed network \
devices through a Python intermediary layer — you never connect to devices yourself, \
but you call tools that execute commands on your behalf.

Capabilities
- Query device status, interfaces, routing tables, ACLs, and full configurations
- Execute show commands and gather diagnostic information across one or all devices
- Apply configuration changes to one or many devices (config mode)
- Analyse network topology discovered via CDP
- Back up device configurations before making changes
- Troubleshoot connectivity, routing, and interface issues

TASK COMPLETION — most important rule
When the user gives you a task (verify, configure, troubleshoot, fix), COMPLETE IT.
Do not stop after gathering information and summarising the topology.  That is not
completing the task — it is only the discovery phase.  After gathering what you need,
immediately proceed to the actual work: run the relevant verification commands,
apply the configuration, test connectivity, or produce a pass/fail verdict.

Specifically:
- "Verify X" → run the exact show commands that prove X is present and working.
  Report PASS or FAIL for each requirement, with evidence from the command output.
  Do not stop at "here is the topology" — that is not a verification.
- "Configure X" → apply the configuration change, then verify it took effect.
- "Troubleshoot X" → run diagnostics, identify the root cause, fix it or report it.
- NEVER end a response with "What would you like me to do?" or "Let me know how to
  proceed" when the user has already told you what to do.  Execute the task.

Efficiency rules  ← follow these strictly
1. Device inventory is pre-loaded in [BACKGROUND — managed device inventory…] — do NOT
   call get_all_devices and do NOT summarise the device list unless the user asks.
   That block is background context, NOT a question about device status.
2. Topology is pre-loaded in [Topology] — do NOT call get_network_topology and do NOT
   run show cdp neighbors manually.  Use the pre-loaded interface IP table and link
   table directly to plan configurations.  The IPs in [Topology] are authoritative.
   Only call get_network_topology if you observe a discrepancy between [Topology] and
   live device output — in that case refresh it, then update the network KB.
3. Knowledge base (KB) is the authoritative source of truth for this list.
   The KB covers network facts AND Jenkins/Ansible lessons — use the same tools for all of them.
   THE RULE: if a fact is in [NETWORK KB], use it as-is without re-querying or re-diagnosing.
   Treat KB entries exactly like your own memory.
   ONLY go to the source (device, Jenkins, Ansible) when:
     a) The specific fact is missing from the KB entirely, OR
     b) A command you already ran this session returns output that directly
        contradicts a KB entry — update the KB with the corrected value.

   Network KB examples:
   - category="interfaces", key="PE-1_Gi1/0",         value="10.0.0.9/30 — connects to P2"
   - category="tunnels",    key="Tunnel1_primary",     value="PE-1->P2->PE-2 via 10.0.0.11,10.0.0.28"
   - category="routing",    key="PE-1_OSPF_neighbors", value="P1(10.0.0.8) P2(10.0.0.11)"
   - category="rsvp",       key="PE-1_Gi1/0_bw",       value="1000 Kbps total, 500 Kbps reservable"

   Jenkins KB — save after EVERY Jenkins fix or discovery:
   - category="jenkins", key="csrf_crumb",       value="All POSTs need Jenkins-Crumb header from /crumbIssuer/api/json"
   - category="jenkins", key="pipeline_xml_root", value="Must use <flow-definition>, not <project>"
   - category="jenkins", key="bat_for_loop",      value="Use %%f not %f in bat FOR loops inside Groovy"
   - category="jenkins", key="<job>_last_fix",    value="<what was broken and what fixed it>"

   Ansible KB — save after EVERY playbook fix or device quirk discovery:
   - category="ansible", key="<device>_commit_required", value="Must send 'commit' before 'exit' on <device> or config is lost"
   - category="ansible", key="<device>_ospf_quirk",      value="OSPF network command requires 'area 0' suffix on this IOS version"
   - category="ansible", key="<playbook>_fix",            value="<what was wrong and what the correct command sequence is>"
4. When running the same command on multiple devices, ALWAYS use
   execute_command_on_multiple_devices in a single call instead of looping
   execute_command once per device.
5. Gather all information you need in as few tool calls as possible.
6. Do not re-run a command you already ran this session unless data may have changed.
7. Never call get_running_config unless the user explicitly asks.  Use focused section
   queries instead:  show running-config | section ospf
8. For multi-line IOS config blocks, always use execute_commands_on_device with each
   line as a separate entry — never try to send a block as a single command string.
   Example for ip explicit-path:
     commands: ["ip explicit-path name PRIMARY enable",
                "next-address 10.0.0.11", "next-address 10.0.0.28", "exit"]
   Example for interface config:
     commands: ["interface Tunnel1", "ip unnumbered Loopback0",
                "tunnel mode mpls traffic-eng", "exit"]
9. Use IOS pipe filters to keep output concise and avoid clipping:
   - show interfaces | include (line protocol|Internet address|Description)
   - show running-config | section router ospf
   - show ip route | include O|S|C
   - show mpls traffic-eng tunnels | include Tunnel|Path|State
   Do NOT fall back to querying one device at a time just because output is large —
   use a more targeted command with pipe filters instead.
10. Keep responses concise.  Show command output in code blocks; skip prose that
    restates what the output already says.

Lab notes — persistent environment memory
- A [LAB NOTES] block (if present) contains facts you discovered in previous sessions
  about this specific lab environment.  Read it at the start of every task and apply
  it immediately — do NOT attempt actions that are recorded as failing.
- When you discover something environment-specific that will affect future tasks
  (a tool that fails on this platform, a confirmed interface mapping, a quirk of a
  device's config), call save_lab_note immediately with a concise factual note.
  Examples: "backup_device_config fails with a parsing error on this GNS3 platform —
  skip it and proceed without backing up", "PE-1 Gi1/0 connects to P2 via 10.0.0.9/30".

Self-repair — fixing application code bugs
You have access to read_app_file, patch_app_file, and restart_server.  Use them
proactively whenever you identify that a limitation or failure is caused by the
application code rather than the network or device.  Do NOT just work around the
issue and move on — fix it so it works correctly for this and future sessions.

Triggers — use self-repair when you observe ANY of the following:
- A tool returns a Python exception or traceback.
- A tool behaves differently than its description says it should.
- You identify that the tool implementation prevents a valid IOS workflow
  (e.g. config wrapping interferes with sub-mode commands).
- A tool silently produces wrong output (truncation, missing devices, wrong format).
- You find yourself saying "the tool wraps X which interferes with Y" or
  "I'll try a different approach because the tool does Z".

Workflow:
1. Identify: recognise that the root cause is in the application code, not the device.
2. Read: call read_app_file on the relevant file to see the exact implementation.
3. Diagnose: explain in a brief comment what the bug is and what the fix should be.
4. Patch: call patch_app_file with the minimal old_string → new_string fix.
5. Restart: call restart_server so the change takes effect immediately.
6. Retry: after ~5 seconds, retry the original operation with the fixed tool.
7. Note: call save_lab_note describing what was wrong and what fixed it.

Rules:
- Only patch to fix a genuine bug or behavioural mismatch.  Do NOT refactor.
- Never patch .env, data/provider_config.json, or data/lab_notes.md.
- Double-check Python indentation and quotes before calling patch_app_file —
  a syntax error will prevent the server from restarting.
- read_app_file returns line numbers — do NOT include them in old_string/new_string.
- Large files (app.py is ~2300 lines): always use start_line/end_line to read only what you need.
  Read the first ~80 lines for imports/structure, then jump to the relevant section.
  The response footer tells you how many lines remain and what start_line to use next.

Resuming interrupted tasks
- A [SESSION CHECKPOINT] block (if present) contains exactly where the task left off.
  Read it and immediately continue from that point — do NOT re-run any tool calls to
  "verify" or "check" state that the checkpoint already describes.  Trust it completely.
- If there is no checkpoint but the user says "continue", scan the conversation history
  for the last successful tool results and assistant observations, then proceed from there.
- If the conversation history shows tool calls were in progress but have a note
  saying "[Task was interrupted before this tool completed]", re-run only those
  specific interrupted tool calls — do not re-gather information that succeeded.
- The [Topology] block in this message is always current — do not re-discover it.

Jenkins CI — full pipeline control with per-list isolation
Each device list has its OWN set of Jenkins pipelines. Pipelines are scoped to the
currently active list — switching lists changes which pipelines are triggered.

Server connection is stored in data/jenkins_checks.json (URL, user, api_key, token).
Per-list pipeline registries live in data/lists/{slug}/jenkins_pipelines.json.
Per-list build results live in data/lists/{slug}/jenkins_results.json.
The repo contains a Jenkinsfile at the project root used by the default pipeline.

Tool reference:
  jenkins_get_current_pipelines — show pipelines registered to THIS list with latest results [START HERE]
  jenkins_list_jobs             — list ALL jobs on the server (to discover what exists before creating)
  jenkins_get_pipeline_script   — read the Groovy pipeline stages (local cache or fetched from server)
  jenkins_get_config            — read a job's full XML config.xml (use when you need raw XML)
  jenkins_create_job            — create new pipeline on Jenkins AND register it to the current list
  jenkins_update_job            — replace a job's XML config (change stages, Groovy script, etc.)
  jenkins_delete_job            — permanently delete from server AND unlink from this list
  jenkins_get_builds            — view recent build history with results and durations
  jenkins_enable_job / jenkins_disable_job — enable or disable a job on the server
  jenkins_link_pipeline         — associate an EXISTING server job to this list (no server changes)
  jenkins_unlink_pipeline       — remove a job from this list's set (job stays on server)
  run_jenkins_checks            — trigger ALL pipelines registered to the current list

Per-list rules (critical):
- jenkins_get_current_pipelines is the FIRST tool to call when asked about CI for this list.
- jenkins_create_job auto-registers the new job to the current list.
- jenkins_delete_job removes from server AND from this list's registry.
- run_jenkins_checks triggers ONLY the pipelines registered to the current list.
- Results in the Jenkins tab are specific to the current list.

Workflow — setting up CI for a list:
1. jenkins_get_current_pipelines  → see what's already registered
2. If none: jenkins_list_jobs     → see what jobs exist on the server
3a. If a suitable job exists:     jenkins_link_pipeline to associate it
3b. If no suitable job:           jenkins_create_job with XML below
4. run_jenkins_checks             → trigger and verify

Jenkins Pipeline XML format (use this exact structure for jenkins_create_job/jenkins_update_job):
The xml_config argument must be valid Jenkins config.xml. For a Pipeline job:

<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>DESCRIPTION HERE</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">
    <script>
pipeline {
    agent any

    options {
        timeout(time: 10, unit: 'MINUTES')
        timestamps()
    }

    stages {
        stage('Syntax: app.py') {
            steps {
                bat "python -m py_compile app.py"
            }
        }
        stage('Syntax: modules/*.py') {
            steps {
                bat "FOR %%f IN (modules\\*.py) DO python -m py_compile \"%%f\""
            }
        }
        stage('HTTP: / returns 200') {
            steps {
                bat "curl -sf --max-time 10 http://localhost:5000/ > NUL"
            }
        }
    }

    post {
        always { echo "Pipeline finished: ${currentBuild.currentResult}" }
        success { echo 'All checks passed.' }
        failure { echo 'One or more checks FAILED.' }
    }
}
    </script>
    <sandbox>true</sandbox>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>

Key XML rules:
- Root element is <flow-definition>, NOT <project> or <maven2-modularset>.
- The definition class must be exactly: org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
- <sandbox>true</sandbox> is required to avoid script approval prompts.
- On Windows Jenkins agents, use bat steps (not sh). Use %%f (not %f) in FOR loops inside bat.
- Escape special chars in XML: & → &amp;  < → &lt;  > → &gt;  " → &quot;
- To read the Jenkinsfile from the repo instead of inline: use CpsScmFlowDefinition.
  For inline Groovy (most common), use CpsFlowDefinition with <script> as shown above.

Modifying an existing pipeline:
1. jenkins_get_pipeline_script to read the current Groovy stages (easier than parsing XML)
2. Edit the Groovy script as needed
3. Embed the updated script into the full XML template and call jenkins_update_job
4. run_jenkins_checks to verify

Pipeline definition locations:
- Inline jobs created via jenkins_create_job: Groovy is cached locally at
  data/lists/{slug}/{job-name}.groovy — updated automatically on every create/update.
- SCM-based jobs (like the default network-device-manager): reads the Jenkinsfile
  from the git repo root on each build. Edit the Jenkinsfile directly to change stages.

Automated CI after code changes — MANDATORY two-step pattern:
Step 1: run_jenkins_checks (startup_delay=8 after restart_server) — triggers the build.
Step 2: jenkins_wait_for_result — blocks until done, returns result + console for any failure.
NEVER skip step 2. The build result is unknown until jenkins_wait_for_result completes.

If jenkins_wait_for_result shows a failure (console is included automatically):
1. Read the console to identify the failing stage and exact error.
2. Fix the root cause:
   - Application bug  → patch_app_file + restart_server
   - Pipeline/XML bug → jenkins_update_job with corrected Groovy
3. Repeat: run_jenkins_checks → jenkins_wait_for_result until all pipelines pass.
4. update_network_kb — record what failed and what fixed it:
   category="jenkins", key="<job>_last_fix",
   value="<stage that failed> — <root cause> — fixed by <what you changed>"
   Also record any reusable lesson (CSRF headers, XML format quirks, bat syntax, etc.).

Git commits — recording successful fixes
After a patch → restart → Jenkins cycle completes successfully (build passes),
call git_commit with a concise present-tense message describing what was fixed.
Example: "Fix /devices route to handle empty device list gracefully"
- Omit 'files' to auto-stage all modified files within allowed paths (app.py, modules/, templates/).
- Set push=true only if the user explicitly asks you to push to the remote.
- Do NOT commit if Jenkins is still running or the build has not yet passed.

Ansible automation — building a reusable playbook library
After completing ANY configuration task (applying config to one or more devices),
ALWAYS call save_ansible_playbook to record what you did as a reusable playbook.
This lets future requests be handled without AI reasoning or SSH commands.

Rules for save_ansible_playbook:
- Call it at the very end of a task, after verifying the config took effect.
- name: short and descriptive, e.g. "Enable MPLS TE on PE-1 and P4"
- keywords: include device hostnames, protocol names, action verbs, interface names.
  Good keywords: ['mpls', 'traffic-eng', 'enable', 'pe-1', 'p4', 'interface', 'rsvp']
- plays: one entry per device with the EXACT commands you applied (config-mode lines).
- Do NOT save playbooks for show/read-only tasks — only for configuration changes.

Fixing / updating an existing playbook:
1. Call list_ansible_playbooks to get the exact playbook_id of the playbook to fix.
2. Call save_ansible_playbook with playbook_id set to that id AND the corrected plays/commands.
   This overwrites the existing YAML file in-place — the same file the user runs manually.
   Do NOT omit playbook_id when fixing — without it a duplicate will be created.
3. Confirm to the user that the existing playbook was updated (not a new one created).
4. Call update_network_kb to record what was wrong and what the correct command sequence is:
   category="ansible", key="<playbook_name>_fix", value="<what was wrong> — corrected to: <fixed commands>"
   Also record any device-specific quirk discovered (commit requirements, IOS version behaviour, etc.).

Rules for using saved playbooks:
- When the user asks you to configure something, call list_ansible_playbooks FIRST
  to check if a matching playbook already exists.
- If a matching playbook is found, call run_ansible_playbook with its id instead of
  manually running SSH commands. This is faster and guaranteed to be correct.
- Only fall through to manual SSH commands if no playbook matches.

Safety
- You have real SSH access to real routers and switches.
- Avoid commands that could disrupt connectivity without explicit user request.
- Do not shut interfaces or wipe configs without clear user intent.
"""

# ---------------------------------------------------------------------------
# Tool definitions  (stored in Anthropic format; converted for other providers)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "get_all_devices",
        "description": (
            "Return all managed network devices with online/offline status, hostname, "
            "IP address, and device type."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "execute_command",
        "description": (
            "Execute a single IOS command on a specific device. "
            "Use mode='enable' for show/exec commands. "
            "Use mode='config' for a single config-mode command — the connection "
            "enters 'configure terminal' before the command and exits after. "
            "For multi-line config blocks or commands that require sub-mode navigation "
            "(e.g. 'ip explicit-path', 'router ospf', 'interface'), use "
            "execute_commands_on_device instead and pass each line as a separate command."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ip":      {"type": "string", "description": "Device IP address"},
                "command": {"type": "string", "description": "IOS command to run"},
                "mode": {
                    "type": "string",
                    "enum": ["enable", "config"],
                    "description": "'enable' for show/exec, 'config' for configuration",
                },
            },
            "required": ["ip", "command", "mode"],
        },
    },
    {
        "name": "execute_commands_on_device",
        "description": (
            "Execute a list of IOS commands on a single device in sequence. "
            "Use this for multi-line config blocks, sub-mode navigation, or any "
            "config that requires entering a sub-mode (e.g. 'ip explicit-path name X', "
            "followed by 'next-address Y', 'next-address Z', 'exit'). "
            "Each string in 'commands' is sent as a separate line while inside "
            "configure terminal — enter sub-mode commands as individual list entries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string"},
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of IOS commands",
                },
                "mode": {"type": "string", "enum": ["enable", "config"]},
            },
            "required": ["ip", "commands", "mode"],
        },
    },
    {
        "name": "execute_command_on_multiple_devices",
        "description": (
            "Run the same IOS command on multiple devices in parallel. "
            "Pass device_ips=['all'] to target every online device."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_ips": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of IPs, or ['all'] for every online device",
                },
                "command": {"type": "string"},
                "mode": {"type": "string", "enum": ["enable", "config"]},
            },
            "required": ["device_ips", "command", "mode"],
        },
    },
    {
        "name": "get_running_config",
        "description": "Retrieve the full running configuration from a device.",
        "input_schema": {
            "type": "object",
            "properties": {"ip": {"type": "string"}},
            "required": ["ip"],
        },
    },
    {
        "name": "get_network_topology",
        "description": (
            "Discover the network topology via CDP. Only call this if the user "
            "explicitly asks to refresh topology or after a change that affects links."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "backup_device_config",
        "description": (
            "Create a local backup of a device's running or startup configuration. "
            "Call this before making significant configuration changes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string"},
                "config_type": {
                    "type": "string",
                    "enum": ["running", "startup"],
                },
            },
            "required": ["ip", "config_type"],
        },
    },
    {
        "name": "read_network_kb",
        "description": (
            "Read the persistent knowledge base for this device list — confirmed facts about "
            "the network topology, device configs, Jenkins pipeline behaviour, and Ansible "
            "playbook lessons. Check this BEFORE running show commands or re-diagnosing "
            "issues you may have already solved. Returns the full KB or a specific category."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category to retrieve. Network: 'interfaces', 'routing', "
                        "'tunnels', 'devices'. CI/CD: 'jenkins', 'ansible'. "
                        "Omit to get the entire KB."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "update_network_kb",
        "description": (
            "Persist a confirmed fact or lesson to the knowledge base for this device list. "
            "Use this for network facts AND for Jenkins/Ansible lessons learned. "
            "\n\nNetwork categories: 'interfaces', 'routing', 'tunnels', 'devices', 'mpls_te', 'rsvp'"
            "\nJenkins categories: 'jenkins' — pipeline quirks, CSRF fixes, agent issues, job configs"
            "\nAnsible categories: 'ansible' — playbook fixes, command ordering, device-specific quirks"
            "\n\nExamples:"
            "\n  category='jenkins', key='csrf_fix', value='Jenkins requires X-Crumb header on all POSTs — fetch from /crumbIssuer/api/json'"
            "\n  category='ansible', key='PE1_ospf_commit_order', value='Must send commit before exit or OSPF config is lost on PE-1'"
            "\n  category='interfaces', key='PE-1_Gi1/0', value='10.0.0.9/30 — connects to P2'"
            "\nExisting keys are overwritten so the KB always reflects current state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Top-level grouping. Network: 'interfaces', 'routing', 'tunnels', 'devices'. "
                        "CI/CD: 'jenkins', 'ansible'."
                    ),
                },
                "key": {
                    "type": "string",
                    "description": "Unique identifier within the category — descriptive, e.g. 'csrf_fix' or 'PE-1_Gi1/0'",
                },
                "value": {
                    "type": "string",
                    "description": "The confirmed fact, lesson, or state",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "read_app_file",
        "description": (
            "Read the source code of a file in this application. Use this when you "
            "encounter a bug or error and need to inspect the relevant code to fix it. "
            "Readable paths: app.py, modules/*.py, templates/*.html, static/**.\n\n"
            "For large files (app.py, ai_assistant.py, etc.) use start_line and end_line "
            "to read only the section you need. The response always includes line numbers "
            "so you can make accurate patches and know exactly where to read next.\n"
            "Strategy for large files: read lines 1-80 first to get the structure/imports, "
            "then jump to the specific section using start_line/end_line."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root, e.g. 'modules/device.py' or 'app.py'",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-based, inclusive). Omit to start from line 1.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to return (1-based, inclusive). Omit to read to end of file.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "patch_app_file",
        "description": (
            "Apply a surgical string-replacement patch to a source file. "
            "Replaces the first occurrence of old_string with new_string. "
            "Always read_app_file first to confirm the exact text to replace. "
            "After patching call restart_server so the change takes effect. "
            "Writable paths: app.py, modules/*.py, templates/*.html."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to find and replace (must be unique in the file)",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "restart_server",
        "description": (
            "Restart the Flask application server so that patched source files take effect. "
            "Call this after patch_app_file. The server will restart in ~2 seconds; "
            "the user's browser will reconnect automatically."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "git_commit",
        "description": (
            "Stage and commit changes to git. "
            "Call this after a successful patch → restart → Jenkins checks cycle to record the fix. "
            "If 'files' is omitted, all modified files within allowed paths are staged automatically. "
            "Set push=true to also push the commit to the remote repository."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message — concise present-tense summary (e.g. 'Fix: handle empty device list on index page')",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific files to stage (relative paths from project root). "
                        "Omit to auto-stage all modified files within writable paths."
                    ),
                },
                "push": {
                    "type": "boolean",
                    "description": "Push to remote after committing (default: false).",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "save_lab_note",
        "description": (
            "Save a persistent note about this specific lab/network environment. "
            "Use this when you discover a limitation, quirk, or confirmed behaviour "
            "that you should remember in future sessions — e.g. 'backup_device_config "
            "fails with a parsing error on this platform', or 'PE-1 Gi1/0 is the "
            "primary MPLS TE interface'. Notes are injected automatically into every "
            "future session so you never have to rediscover the same thing twice."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "A concise, factual note about this environment.",
                },
            },
            "required": ["note"],
        },
    },
    {
        "name": "jenkins_get_current_pipelines",
        "description": (
            "Show which Jenkins pipelines are registered to the CURRENT device list, "
            "along with their latest build result from the server. "
            "Call this first whenever the user asks about CI for this list, "
            "or before creating/linking a pipeline, to avoid duplicates."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "jenkins_list_jobs",
        "description": (
            "List ALL Jenkins pipeline jobs on the configured server (not filtered by list). "
            "Returns each job's name, URL, and whether it is currently buildable. "
            "Use this to discover what pipelines exist on the server before creating or linking one."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "jenkins_get_pipeline_script",
        "description": (
            "Get the Groovy pipeline script for a job — the human-readable stage definitions. "
            "Returns the locally cached .groovy file if available (created when the job was "
            "last created/updated via this tool). Falls back to fetching from the Jenkins server "
            "and caching it. Use this to read and understand a pipeline before modifying it, "
            "instead of parsing raw XML from jenkins_get_config."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_get_config",
        "description": (
            "Retrieve the raw XML configuration of a Jenkins job/pipeline. "
            "Read this before modifying a pipeline so you know the current Groovy/XML content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_create_job",
        "description": (
            "Create a new Jenkins pipeline job from an XML config string. "
            "The xml_config must be a valid Jenkins job XML (config.xml format). "
            "For a Pipeline job, use a <flow-definition> root element containing a <definition> "
            "with class='org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition' and a <script> "
            "element holding the Groovy pipeline script."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name":   {"type": "string", "description": "Name for the new Jenkins job"},
                "xml_config": {"type": "string", "description": "Full Jenkins config.xml content"},
            },
            "required": ["job_name", "xml_config"],
        },
    },
    {
        "name": "jenkins_update_job",
        "description": (
            "Replace the XML configuration of an existing Jenkins job. "
            "Call jenkins_get_config first to get the current XML, modify it, then call this. "
            "Use this to change pipeline stages, add parameters, update the Groovy script, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name":   {"type": "string", "description": "Exact Jenkins job name to update"},
                "xml_config": {"type": "string", "description": "New full Jenkins config.xml content"},
            },
            "required": ["job_name", "xml_config"],
        },
    },
    {
        "name": "jenkins_delete_job",
        "description": (
            "Permanently delete a Jenkins job and all its build history. "
            "This is irreversible — confirm the job name with jenkins_list_jobs first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name to delete"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_get_builds",
        "description": (
            "Get recent build history for a Jenkins job — build numbers, results (SUCCESS/FAILURE/ABORTED), "
            "timestamps, and durations. Useful for diagnosing repeated failures or verifying a fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name"},
                "limit":    {"type": "integer", "description": "Max builds to return (default 10)"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_get_console",
        "description": (
            "Fetch the full console log for a Jenkins build. "
            "Call this AUTOMATICALLY whenever a build result is FAILURE or ABORTED — "
            "do not ask the user to copy-paste it. "
            "Use build_number='lastFailed' to get the most recent failure without knowing the number. "
            "The log shows exactly which stage failed and why."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {
                    "type": "string",
                    "description": "Exact Jenkins job name",
                },
                "build_number": {
                    "type": "string",
                    "description": (
                        "Build number (e.g. '42'), or 'last' for the most recent build, "
                        "or 'lastFailed' for the most recent failed build (default)."
                    ),
                },
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_enable_job",
        "description": "Enable a disabled Jenkins job so it can be triggered again.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name to enable"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_disable_job",
        "description": "Disable a Jenkins job so it cannot be triggered (builds are blocked).",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name to disable"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_link_pipeline",
        "description": (
            "Associate an existing Jenkins server job with the current device list "
            "without creating or modifying the job on the server. "
            "Use this when a job already exists on Jenkins and you want it to run when "
            "this list's 'Run Checks' is triggered. "
            "After linking, run_jenkins_checks will include this job."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name to link to this list"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "jenkins_unlink_pipeline",
        "description": (
            "Remove the association between a Jenkins job and the current device list. "
            "The job remains on the Jenkins server and is NOT deleted — it just won't be "
            "triggered by this list's run_jenkins_checks any more. "
            "Use jenkins_delete_job if you want to remove the job from the server too."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "Exact Jenkins job name to unlink from this list"},
            },
            "required": ["job_name"],
        },
    },
    {
        "name": "run_jenkins_checks",
        "description": (
            "Trigger the Jenkins CI pipelines for the current list and return immediately. "
            "ALWAYS follow this with jenkins_wait_for_result to get the build outcome. "
            "Use startup_delay=8 after restart_server so the server is up before Jenkins hits HTTP endpoints."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "startup_delay": {
                    "type": "number",
                    "description": (
                        "Seconds to wait before triggering — use 8 after restart_server "
                        "so the server has time to come back up before Jenkins runs HTTP checks."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "jenkins_wait_for_result",
        "description": (
            "Wait for all running Jenkins pipelines for this list to finish, "
            "then return the result of each job. "
            "ALWAYS call this after run_jenkins_checks — never leave a build unobserved. "
            "If any pipeline failed, the console log is fetched and included automatically "
            "so you can diagnose and fix the issue immediately without a separate tool call. "
            "Blocks until all builds complete or timeout is reached."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "description": "Maximum seconds to wait (default 600 = 10 minutes).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "save_ansible_playbook",
        "description": (
            "Save or UPDATE a reusable Ansible-style playbook. "
            "Creating: call after completing any configuration task. "
            "Updating/fixing: call list_ansible_playbooks FIRST to get the exact playbook_id, "
            "then pass that playbook_id here — this overwrites the existing playbook file in-place "
            "so the user's manual runs and scheduled triggers use the corrected commands. "
            "If playbook_id is omitted, deduplication is done by name (case-insensitive match)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "playbook_id": {
                    "type": "string",
                    "description": (
                        "ID of an existing playbook to overwrite. "
                        "Get this from list_ansible_playbooks. "
                        "Pass this when fixing a broken playbook so the same file is updated, "
                        "not a new one created."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Short human-readable task name (e.g. 'Enable MPLS TE on PE-1 and P4')",
                },
                "description": {
                    "type": "string",
                    "description": "One-sentence description of what this playbook does",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Keywords for matching future requests. Include: device hostnames, "
                        "protocol names, action verbs, interface names. "
                        "Examples: ['mpls', 'te', 'traffic-eng', 'pe-1', 'p4', 'tunnel', 'enable']"
                    ),
                },
                "plays": {
                    "type": "array",
                    "description": "One entry per device — the commands applied to that device",
                    "items": {
                        "type": "object",
                        "properties": {
                            "device_ip":  {"type": "string", "description": "Device management IP"},
                            "hostname":   {"type": "string", "description": "Device hostname"},
                            "commands":   {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Ordered list of IOS commands that were applied. "
                                    "For config-mode commands omit 'configure terminal' — "
                                    "set mode='config'. For exec/enable-mode commands "
                                    "(e.g. 'mpls traffic-eng reoptimize', 'clear ip ospf process') "
                                    "set mode='enable'."
                                ),
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["config", "enable"],
                                "description": (
                                    "'config' (default) — enter configure terminal before running commands. "
                                    "'enable' — run commands in exec/privileged-exec mode WITHOUT entering "
                                    "configure terminal. Use 'enable' for operational commands such as "
                                    "'mpls traffic-eng reoptimize', 'clear ip ospf process', "
                                    "'debug mpls traffic-eng', etc."
                                ),
                            },
                        },
                        "required": ["device_ip", "commands"],
                    },
                },
            },
            "required": ["name", "description", "keywords", "plays"],
        },
    },
    {
        "name": "list_ansible_playbooks",
        "description": (
            "List all saved Ansible playbooks with their names, descriptions, and keywords. "
            "Call this when the user asks to do something that may already be automated, "
            "to check if a playbook exists before running SSH commands manually."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_ansible_playbook",
        "description": (
            "Execute a saved Ansible playbook by replaying its commands on the target devices "
            "via SSH. This is faster than re-running individual commands and doesn't require "
            "the AI to reason about what to do — the playbook already knows. "
            "Use this when a saved playbook exactly matches what the user wants."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "playbook_id": {
                    "type": "string",
                    "description": "The 'id' field from list_ansible_playbooks output",
                },
            },
            "required": ["playbook_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Human-readable tool labels for the UI
# ---------------------------------------------------------------------------
def _tool_label(name: str, args: dict) -> str:
    if name == "get_all_devices":
        return "Fetching device inventory..."
    if name == "execute_command":
        return f"Running `{args.get('command', '')}` on {args.get('ip', '')}..."
    if name == "execute_commands_on_device":
        return f"Running {len(args.get('commands', []))} command(s) on {args.get('ip', '')}..."
    if name == "execute_command_on_multiple_devices":
        ips = args.get("device_ips", [])
        target = "all devices" if ips == ["all"] else f"{len(ips)} device(s)"
        return f"Running `{args.get('command', '')}` on {target}..."
    if name == "get_running_config":
        return f"Reading running-config from {args.get('ip', '')}..."
    if name == "get_network_topology":
        return "Discovering network topology via CDP..."
    if name == "backup_device_config":
        return f"Backing up {args.get('config_type','running')}-config on {args.get('ip','')}..."
    if name == "save_lab_note":
        note = args.get("note", "")
        return f"Saving lab note: {note[:60]}{'...' if len(note) > 60 else ''}"
    if name == "read_network_kb":
        cat = args.get("category", "")
        return f"Reading network KB{': ' + cat if cat else ''}..."
    if name == "update_network_kb":
        return f"Saving to KB [{args.get('category','')}] {args.get('key','')}: {str(args.get('value',''))[:50]}"
    if name == "read_app_file":
        return f"Reading source: {args.get('path', '')}"
    if name == "patch_app_file":
        return f"Patching {args.get('path', '')}..."
    if name == "restart_server":
        return "Restarting server to apply code changes..."
    if name == "git_commit":
        return f"Committing: {args.get('message', '')}..."
    if name == "jenkins_get_current_pipelines":
        return "Checking pipelines for current list..."
    if name == "jenkins_list_jobs":
        return "Listing Jenkins jobs..."
    if name == "jenkins_get_pipeline_script":
        return f"Reading pipeline script for '{args.get('job_name', '')}'..."
    if name == "jenkins_get_config":
        return f"Getting config for Jenkins job '{args.get('job_name', '')}'..."
    if name == "jenkins_create_job":
        return f"Creating Jenkins job '{args.get('job_name', '')}'..."
    if name == "jenkins_update_job":
        return f"Updating Jenkins job '{args.get('job_name', '')}'..."
    if name == "jenkins_delete_job":
        return f"Deleting Jenkins job '{args.get('job_name', '')}'..."
    if name == "jenkins_get_builds":
        return f"Getting build history for '{args.get('job_name', '')}'..."
    if name == "jenkins_get_console":
        build = args.get('build_number', 'lastFailed')
        return f"Fetching console log for '{args.get('job_name', '')}' (build={build})..."
    if name == "jenkins_enable_job":
        return f"Enabling Jenkins job '{args.get('job_name', '')}'..."
    if name == "jenkins_disable_job":
        return f"Disabling Jenkins job '{args.get('job_name', '')}'..."
    if name == "jenkins_link_pipeline":
        return f"Linking pipeline '{args.get('job_name', '')}' to current list..."
    if name == "jenkins_unlink_pipeline":
        return f"Unlinking pipeline '{args.get('job_name', '')}' from current list..."
    if name == "run_jenkins_checks":
        delay = args.get("startup_delay", 0)
        return f"Running CI checks{f' (waiting {delay}s for server)' if delay else ''}..."
    if name == "jenkins_wait_for_result":
        return "Waiting for Jenkins build to complete..."
    if name == "save_ansible_playbook":
        return f"Saving playbook: {args.get('name', '')}..."
    if name == "list_ansible_playbooks":
        return "Listing saved Ansible playbooks..."
    if name == "run_ansible_playbook":
        return f"Running playbook: {args.get('playbook_id', '')}..."
    return f"Executing {name}..."


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------
def run_chat(
    session_id: str,
    user_message: str,
    devices_loader,
    status_cache: dict,
    connections_pool: dict,
    pool_lock,
    context_ip: Optional[str] = None,
    device_context: Optional[str] = None,
    topology_context: Optional[str] = None,
) -> Iterator[dict]:
    """
    Run one chat turn with the active AI provider.

    Yields SSE-ready event dicts:
        {"type": "text",           "content": "..."}
        {"type": "tool_start",     "id": "...", "tool": "...", "label": "...", "args": {...}}
        {"type": "tool_result",    "id": "...", "tool": "...", "content": "..."}
        {"type": "usage",          "input": N, "output": N, ..., "cost_usd": X}
        {"type": "provider",       "id": "...", "name": "...", "model": "..."}
        {"type": "interrupted",    "content": "Stopped by user."}
        {"type": "error",          "content": "..."}
        {"type": "done"}
    """
    from modules.commands import run_device_command
    from modules.connection import get_persistent_connection
    from modules.backups import (
        get_running_config as _get_running_config,
        get_startup_config as _get_startup_config,
        save_config_backup,
    )
    from modules.topology import discover_topology
    from concurrent.futures import ThreadPoolExecutor, as_completed

    provider_info    = get_provider_info()
    provider_id      = provider_info["id"]
    model            = provider_info["model"]
    max_tokens_out   = provider_info.get("max_tokens_per_req", 4096)
    max_history      = provider_info.get("max_history", 20)
    _inject_topo_cfg = provider_info.get("inject_topo", "first_turn")
    active_prompt    = SYSTEM_PROMPT

    # Inform the UI which provider is handling this turn.
    yield {"type": "provider", "id": provider_id,
           "name": provider_info["name"], "model": model}

    _clear_stop(session_id)
    if session_id not in _chat_histories:
        raw = _load_history_from_disk(session_id)
        _chat_histories[session_id] = raw
    # Repair any tool_use without tool_result anywhere in history (every turn).
    _chat_histories[session_id] = _sanitize_trailing_tool_use(_chat_histories[session_id])
    history = _chat_histories[session_id]

    # Build the user message with context prefixes.
    is_first_turn = len(history) == 0

    # Resolve topology injection setting now that we know is_first_turn.
    # "always" = every turn, "first_turn" = session start only, False = never.
    inject_topo = (
        _inject_topo_cfg == "always"
        or (_inject_topo_cfg == "first_turn" and is_first_turn)
    )

    prefix_parts = []

    # Inject persistent lab notes first so Claude sees them before anything else.
    _lab_notes = _load_lab_notes()
    if _lab_notes:
        prefix_parts.append(
            "[LAB NOTES — platform/tool quirks, apply immediately]\n"
            + _lab_notes
        )

    # Inject the network knowledge base — confirmed facts about this network.
    # This is the primary mechanism for avoiding redundant show commands.
    _kb = _load_network_kb()
    if _kb:
        # Split KB into network facts vs CI/CD lessons for clearer presentation
        _ci_cats      = {"jenkins", "ansible"}
        _net_kb       = {k: v for k, v in _kb.items() if k not in _ci_cats}
        _cicd_kb      = {k: v for k, v in _kb.items() if k in _ci_cats}
        _kb_blocks    = []
        if _net_kb:
            _kb_blocks.append(
                "[NETWORK KB — confirmed network facts, treat as ground truth]\n"
                + _format_network_kb(_net_kb)
            )
        if _cicd_kb:
            _kb_blocks.append(
                "[CI/CD KB — learned Jenkins & Ansible lessons, apply before retrying]\n"
                + _format_network_kb(_cicd_kb)
            )
        prefix_parts.append(
            "\n\n".join(_kb_blocks)
            + "\nRULE: treat every entry above as ground truth. Do NOT re-query or "
            "re-diagnose anything already recorded here. Only go to the live source "
            "when a fact is absent or a live result directly contradicts an entry "
            "(then update the KB). After fixing anything, call update_network_kb."
        )

    # Detect continuation requests and inject the saved checkpoint so Claude
    # knows exactly where it left off without re-running any tool calls.
    _CONTINUATION_KEYWORDS = (
        "continue", "keep going", "left off", "resume", "carry on",
        "pick up", "where we", "next step", "what's next", "what next",
    )
    _is_continuation = any(kw in user_message.lower() for kw in _CONTINUATION_KEYWORDS)
    _checkpoint = _load_checkpoint(session_id)

    if _is_continuation and _checkpoint:
        cp_text = (
            f"[SESSION CHECKPOINT — do NOT re-run tool calls to verify this, "
            f"trust it and continue from here]\n"
            f"Task: {_checkpoint.get('task', '(unknown)')}\n"
            f"Saved at: {_checkpoint.get('saved_at', '')}"
            f" (after step {_checkpoint.get('iteration', '?')})\n"
            f"Last progress note:\n{_checkpoint.get('progress', '')}"
        )
        prefix_parts.append(cp_text)
    elif not _is_continuation and is_first_turn:
        # Fresh task — clear any stale checkpoint from a previous session.
        _clear_checkpoint(session_id)

    if device_context:
        try:
            devs = json.loads(device_context)
            # Omit online-status — it triggers Claude to summarise device
            # reachability instead of focusing on the actual task.
            compact = [
                {"h": d.get("hostname", ""), "ip": d.get("ip", "")}
                for d in devs
            ]
            prefix_parts.append(
                "[BACKGROUND — managed device inventory, NOT a question]\n"
                + json.dumps(compact, separators=(",", ":"))
                + "\nDo NOT call get_all_devices unless the user explicitly asks "
                "to refresh. Do NOT summarise this list unless asked."
            )
        except Exception:
            pass

    if topology_context and inject_topo:
        try:
            topo = json.loads(topology_context)
            # Strip HTML title fields — they're for the visual graph, not the AI.
            for node in topo.get("nodes", []):
                node.pop("title", None)
            for edge in topo.get("edges", []):
                edge.pop("title", None)
            iface_map = topo.get("interface_map", {})
            iface_lines = []
            for hostname, ifaces in sorted(iface_map.items()):
                for entry in ifaces:
                    iface_lines.append(
                        f"  {hostname:12s}  {entry['intf']:20s}  {entry['ip']}"
                    )
            link_lines = []
            for edge in topo.get("edges", []):
                link_lines.append(
                    f"  {edge['from']:12s} {edge.get('from_intf',''):12s} "
                    f"{edge.get('local_ip',''):15s}  <->  "
                    f"{edge['to']:12s} {edge.get('to_intf',''):12s} "
                    f"{edge.get('remote_ip','')}"
                )
            topo_text = "[Topology — authoritative, do NOT call get_network_topology]\n"
            if iface_lines:
                topo_text += "\nInterface IP table:\n"
                topo_text += "  Device        Interface             IP\n"
                topo_text += "\n".join(iface_lines)
            if link_lines:
                topo_text += "\n\nLinks (use these IPs for next-hops):\n"
                topo_text += "  From          From-intf    From-IP          <->  To            To-intf      To-IP\n"
                topo_text += "\n".join(link_lines)
            prefix_parts.append(topo_text)
        except Exception:
            pass

    if context_ip:
        devices = devices_loader()
        dev = next((d for d in devices if d["ip"] == context_ip), None)
        label = dev.get("hostname", context_ip) if dev else context_ip
        prefix_parts.append(f"[Viewing: {label} ({context_ip})]")

    _ACTION_KEYWORDS = (
        "verify", "verif", "check", "configure", "config", "enable", "disable",
        "fix", "troubleshoot", "apply", "set up", "setup", "implement",
        "add", "remove", "delete", "change", "update", "test", "validate",
        "make sure", "ensure", "confirm", "shut", "bring up", "bring down",
        "continue", "keep going", "left off", "resume", "carry on", "proceed",
        "where we", "pick up",
    )
    # Also inject the constraint whenever the session has prior history with
    # tool results — if work was already in progress, Claude must continue it.
    _has_prior_tool_work = any(
        isinstance(m.get("content"), list)
        and any(b.get("type") == "tool_result" for b in m["content"])
        for m in history[:-1]  # exclude the message just appended
    )
    _kw_matched = any(kw in user_message.lower() for kw in _ACTION_KEYWORDS)
    _inject_constraint = _kw_matched or _has_prior_tool_work
    if _inject_constraint:
        prefix_parts.append(
            "[TASK CONSTRAINT] Complete the assigned task fully. Do NOT stop to "
            "summarise devices or topology — the [BACKGROUND] block above is context "
            "only, not a question. After gathering information, immediately proceed to "
            "execute every required step. Report PASS/FAIL with evidence. "
            "Do NOT ask 'what would you like me to do?' when the user has already "
            "given you a task."
        )

    # Separate context prefix (re-injected every API call) from the user message
    # stored in history.  History only stores the clean user question so it
    # never accumulates large context blocks across turns.
    context_prefix = "\n".join(prefix_parts) if prefix_parts else ""
    history.append({"role": "user", "content": user_message})

    # --- Diagnostic log: summarise what was built for this turn --------------
    _dbg("=" * 70)
    _dbg(f"SESSION={session_id}  PROVIDER={provider_id}")
    _dbg(f"USER_MSG={user_message!r}")
    _dbg(f"is_first_turn={is_first_turn}  has_prior_tool_work={_has_prior_tool_work}")
    _dbg(f"kw_matched={_kw_matched}  inject_constraint={_inject_constraint}")
    _dbg(f"inject_topo={inject_topo}  history_len_before_append={len(history)-1}")
    _dbg(f"PREFIX_PARTS ({len(prefix_parts)}):")
    for _i, _p in enumerate(prefix_parts):
        _dbg(f"  [{_i}] {_p[:200]!r}{'...' if len(_p) > 200 else ''}")
    _dbg(f"context_prefix length={len(context_prefix)} chars")

    # -----------------------------------------------------------------
    # Tool executor
    # -----------------------------------------------------------------
    def _conn(device):
        return get_persistent_connection(device, connections_pool, pool_lock)

    def _find_device(ip, devices):
        return next((d for d in devices if d.get("ip") == ip), None)

    def execute_tool(name: str, args: dict) -> str:
        cached = _cache_get(name, args)
        if cached is not None:
            return cached

        try:
            if name == "get_all_devices":
                devices = devices_loader()
                result = [
                    {
                        "hostname":    d.get("hostname", "unknown"),
                        "ip":          d.get("ip", ""),
                        "device_type": d.get("device_type", "cisco_ios"),
                        "online":      bool(status_cache.get(d.get("ip", ""), False)),
                    }
                    for d in devices
                ]
                return json.dumps(result, indent=2)

            elif name == "execute_command":
                ip      = args["ip"]
                command = args["command"]
                mode    = args.get("mode", "enable")
                device  = _find_device(ip, devices_loader())
                if not device:
                    return f"Error: device {ip} not found"
                conn = _conn(device)
                if mode == "config":
                    try:
                        conn.config_mode()
                        out = run_device_command(conn, command)
                    finally:
                        conn.exit_config_mode()
                else:
                    out = run_device_command(conn, command)
                return out or "(no output)"

            elif name == "execute_commands_on_device":
                ip       = args["ip"]
                commands = args["commands"]
                mode     = args.get("mode", "enable")
                device   = _find_device(ip, devices_loader())
                if not device:
                    return f"Error: device {ip} not found"
                conn    = _conn(device)
                outputs = []
                if mode == "config":
                    try:
                        conn.config_mode()
                        for cmd in commands:
                            outputs.append(f"[{cmd}]\n{run_device_command(conn, cmd)}")
                    finally:
                        conn.exit_config_mode()
                else:
                    for cmd in commands:
                        outputs.append(f"[{cmd}]\n{run_device_command(conn, cmd)}")
                return "\n\n".join(outputs)

            elif name == "execute_command_on_multiple_devices":
                device_ips = args["device_ips"]
                command    = args["command"]
                mode       = args.get("mode", "enable")
                devices    = devices_loader()
                targets = (
                    [d for d in devices if status_cache.get(d.get("ip",""), False)]
                    if device_ips == ["all"]
                    else [d for d in devices if d.get("ip") in device_ips]
                )
                if not targets:
                    return "No matching online devices found"

                def run_one(dev):
                    hostname = dev.get("hostname", dev["ip"])
                    try:
                        conn = get_persistent_connection(dev, connections_pool, pool_lock)
                        if mode == "config":
                            try:
                                conn.config_mode()
                                out = run_device_command(conn, command)
                            finally:
                                conn.exit_config_mode()
                        else:
                            out = run_device_command(conn, command)
                        return hostname, dev["ip"], out, None
                    except Exception as exc:
                        return hostname, dev["ip"], None, str(exc)

                results = {}
                with ThreadPoolExecutor(max_workers=5) as ex:
                    for h, ip, out, err in ex.map(run_one, targets):
                        results[f"{h} ({ip})"] = f"ERROR: {err}" if err else (out or "")

                # Fair-share per-device truncation: every device gets an equal
                # slice of the limit so later devices aren't dropped entirely
                # when a single device produces unusually verbose output.
                _limit     = _TOOL_CHAR_LIMITS.get("execute_command_on_multiple_devices", 500000)
                _per_dev   = max(20000, _limit // max(len(results), 1))
                _parts     = []
                _clipped   = 0
                for k, v in results.items():
                    if len(v) > _per_dev:
                        _clipped += 1
                        v = v[:_per_dev] + f"\n...[output clipped at {_per_dev} chars]"
                    _parts.append(f"=== {k} ===\n{v}")
                out_str = "\n\n".join(_parts)
                if _clipped:
                    out_str += (
                        f"\n\n[Note: {_clipped}/{len(results)} device(s) had output clipped. "
                        f"Use a pipe filter on the same command to get targeted output "
                        f"rather than re-querying all devices.]"
                    )
                return out_str

            elif name == "get_running_config":
                ip     = args["ip"]
                device = _find_device(ip, devices_loader())
                if not device:
                    return f"Error: device {ip} not found"
                conn = _conn(device)
                try:
                    change_line = conn.send_command_timing(
                        "show running-config | include Last configuration change",
                        read_timeout=10,
                    ).strip()
                except Exception:
                    change_line = ""
                cached_cfg = _config_cache_load(ip)
                if cached_cfg and cached_cfg.get("change_time") == change_line and change_line:
                    return f"[Cached — unchanged since: {change_line}]\n\n" + cached_cfg["config"]
                config = _get_running_config(conn) or "Failed to retrieve config"
                if change_line:
                    _config_cache_save(ip, change_line, config)
                return config

            elif name == "get_network_topology":
                if topology_context:
                    try:
                        topo = json.loads(topology_context)
                        return "[Topology already provided]\n\n" + json.dumps(topo, indent=2)
                    except Exception:
                        pass
                cached_topo = _topology_cache_load()
                if cached_topo is not None:
                    return "[Cached topology]\n\n" + json.dumps(cached_topo, indent=2)
                devices = devices_loader()
                topo = discover_topology(
                    devices=devices,
                    connection_factory=get_persistent_connection,
                    connections_pool=connections_pool,
                    pool_lock=pool_lock,
                    status_cache=status_cache,
                    max_workers=5,
                )
                _topology_cache_save(topo)
                return json.dumps(topo, indent=2)

            elif name == "backup_device_config":
                ip          = args["ip"]
                config_type = args.get("config_type", "running")
                device      = _find_device(ip, devices_loader())
                if not device:
                    return f"Error: device {ip} not found"
                conn = _conn(device)
                cfg  = (_get_running_config(conn) if config_type == "running"
                        else _get_startup_config(conn))
                if cfg:
                    info = save_config_backup(ip, device.get("hostname", ip), cfg, config_type)
                    return f"Backup saved: {info.get('filename', 'unknown')}"
                return "Failed to retrieve config for backup"

            elif name == "read_app_file":
                rel = args.get("path", "").replace("\\", "/").lstrip("/")
                abs_path = os.path.normpath(os.path.join(_PROJECT_ROOT, rel))
                # Safety: must stay inside project root
                if not abs_path.startswith(_PROJECT_ROOT):
                    return "Error: path is outside project root"
                top_dir = rel.split("/")[0]
                base_file = rel if "/" not in rel else None
                allowed = (
                    top_dir in _APP_READ_WHITELIST
                    or (base_file and base_file in _APP_READ_ROOT_FILES)
                )
                if not allowed:
                    return f"Error: '{rel}' is not in the readable whitelist"
                try:
                    with open(abs_path, encoding="utf-8") as fh:
                        all_lines = fh.readlines()
                    total = len(all_lines)

                    # Apply optional line range (1-based, inclusive)
                    start = max(1, int(args.get("start_line") or 1))
                    end   = min(total, int(args.get("end_line") or total))
                    slice_lines = all_lines[start - 1 : end]

                    numbered = "".join(
                        f"{start + i:5d}  {line}"
                        for i, line in enumerate(slice_lines)
                    )
                    header = f"[{rel}  lines {start}-{end} of {total}]\n"
                    trailer = (
                        f"\n… {total - end} more lines. "
                        f"Call read_app_file with start_line={end + 1} to continue."
                        if end < total else ""
                    )
                    return header + numbered + trailer
                except FileNotFoundError:
                    return f"Error: file not found: {rel}"

            elif name == "patch_app_file":
                rel        = args.get("path", "").replace("\\", "/").lstrip("/")
                old_string = args.get("old_string", "")
                new_string = args.get("new_string", "")
                abs_path   = os.path.normpath(os.path.join(_PROJECT_ROOT, rel))
                if not abs_path.startswith(_PROJECT_ROOT):
                    return "Error: path is outside project root"
                # Check denied list first
                if rel in _APP_WRITE_DENIED:
                    return f"Error: '{rel}' is protected and cannot be patched"
                top_dir   = rel.split("/")[0]
                base_file = rel if "/" not in rel else None
                allowed   = (
                    top_dir in _APP_WRITE_WHITELIST
                    or (base_file and base_file in _APP_WRITE_ROOT_FILES)
                )
                if not allowed:
                    return f"Error: '{rel}' is not in the writable whitelist"
                try:
                    with open(abs_path, encoding="utf-8") as fh:
                        original = fh.read()
                    if old_string not in original:
                        return "Error: old_string not found in file — read the file again to get the exact text"
                    count = original.count(old_string)
                    if count > 1:
                        return (f"Error: old_string appears {count} times — make it more specific "
                                "so the patch is unambiguous")
                    patched = original.replace(old_string, new_string, 1)
                    with open(abs_path, "w", encoding="utf-8") as fh:
                        fh.write(patched)
                    _dbg(f"patch_app_file: {rel} patched successfully")
                    return f"Patched {rel} successfully. Call restart_server to apply."
                except FileNotFoundError:
                    return f"Error: file not found: {rel}"

            elif name == "restart_server":
                import threading as _threading
                # Save a pending-restart marker so the frontend can auto-resume
                # this session once the server comes back up.
                _pending_path = os.path.join(_PROJECT_ROOT, "data", "pending_restart.json")
                try:
                    _cp = _load_checkpoint(session_id)
                    os.makedirs(os.path.dirname(_pending_path), exist_ok=True)
                    with open(_pending_path, "w", encoding="utf-8") as _fh:
                        json.dump({
                            "session_id": session_id,
                            "task":       _cp.get("task", user_message[:200]),
                            "timestamp":  time.time(),
                        }, _fh)
                except Exception:
                    pass
                def _do_restart():
                    time.sleep(2)   # let the SSE response flush first
                    _dbg("restart_server: exiting with code 3 (watchdog restart)")
                    os._exit(3)     # exit code 3 tells launcher.py to restart the server
                _threading.Thread(target=_do_restart, daemon=True).start()
                return (
                    "Server restart scheduled in 2 seconds. "
                    "The watchdog launcher will automatically start a fresh server process. "
                    "Call run_jenkins_checks with startup_delay=8 to verify "
                    "the patch didn't break anything once the server is back up."
                )

            elif name == "git_commit":
                import subprocess as _sp
                import shlex as _shlex
                commit_msg = args.get("message", "").strip()
                if not commit_msg:
                    return "Error: commit message is required"
                files_arg  = args.get("files") or []
                do_push    = bool(args.get("push", False))

                try:
                    app_root = _PROJECT_ROOT

                    if files_arg:
                        # Validate each supplied file against write whitelist
                        to_stage = []
                        for rel in files_arg:
                            rel = rel.replace("\\", "/").lstrip("/")
                            top_dir   = rel.split("/")[0]
                            base_file = rel if "/" not in rel else None
                            allowed   = (
                                top_dir in _APP_WRITE_WHITELIST
                                or (base_file and base_file in _APP_WRITE_ROOT_FILES)
                            )
                            if not allowed:
                                return (
                                    f"Error: '{rel}' is outside the allowed write paths. "
                                    f"Allowed dirs: {sorted(_APP_WRITE_WHITELIST)}, "
                                    f"root files: {sorted(_APP_WRITE_ROOT_FILES)}"
                                )
                            to_stage.append(rel)
                    else:
                        # Auto-detect: stage all modified/new files within write whitelist
                        status_out = _sp.check_output(
                            ["git", "status", "--porcelain"],
                            cwd=app_root, text=True, stderr=_sp.PIPE,
                        )
                        to_stage = []
                        for line in status_out.splitlines():
                            if len(line) < 4:
                                continue
                            rel = line[3:].strip().replace("\\", "/")
                            top_dir   = rel.split("/")[0]
                            base_file = rel if "/" not in rel else None
                            allowed   = (
                                top_dir in _APP_WRITE_WHITELIST
                                or (base_file and base_file in _APP_WRITE_ROOT_FILES)
                            )
                            if allowed:
                                to_stage.append(rel)
                        if not to_stage:
                            return "Nothing to commit — no modified files found within allowed paths."

                    # Stage
                    _sp.check_call(
                        ["git", "add", "--"] + to_stage,
                        cwd=app_root, stderr=_sp.PIPE,
                    )

                    # Commit
                    commit_result = _sp.run(
                        ["git", "commit", "-m", commit_msg],
                        cwd=app_root, text=True,
                        stdout=_sp.PIPE, stderr=_sp.STDOUT,
                    )
                    commit_out = commit_result.stdout.strip()
                    if commit_result.returncode != 0:
                        # Nothing to commit is not a hard error
                        if "nothing to commit" in commit_out.lower():
                            return "Nothing to commit — working tree is clean."
                        return f"git commit failed:\n{commit_out}"

                    result_lines = [f"Committed: {commit_msg}", commit_out]

                    if do_push:
                        push_result = _sp.run(
                            ["git", "push"],
                            cwd=app_root, text=True,
                            stdout=_sp.PIPE, stderr=_sp.STDOUT,
                        )
                        push_out = push_result.stdout.strip()
                        if push_result.returncode != 0:
                            result_lines.append(f"Push FAILED:\n{push_out}")
                        else:
                            result_lines.append(f"Pushed to remote.\n{push_out}")

                    return "\n".join(result_lines)

                except _sp.CalledProcessError as exc:
                    return f"git error: {exc.stderr or exc}"
                except Exception as exc:
                    return f"git_commit error: {exc}"

            elif name == "read_network_kb":
                kb  = _load_network_kb()
                cat = args.get("category", "").strip()
                if cat:
                    subset = kb.get(cat, {})
                    if not subset:
                        return f"No entries found in category '{cat}'. KB categories: {list(kb.keys())}"
                    return f"[{cat}]\n" + _format_network_kb({cat: subset})
                if not kb:
                    return "KB is empty — no facts or lessons recorded yet."
                return _format_network_kb(kb)

            elif name == "update_network_kb":
                category = args.get("category", "general").strip()
                key      = args.get("key", "").strip()
                value    = args.get("value", "").strip()
                if not key:
                    return "Error: key is required"
                kb = _load_network_kb()
                kb.setdefault(category, {})[key] = {
                    "value":   value,
                    "updated": time.strftime("%Y-%m-%d %H:%M"),
                }
                _save_network_kb(kb)
                return f"KB updated: [{category}] {key} = {value}"

            elif name == "save_lab_note":
                return _append_lab_note(args.get("note", ""))

            elif name == "jenkins_get_current_pipelines":
                from modules.jenkins_runner import (
                    load_config as _jload, get_current_list_pipeline_status,
                )
                try:
                    cfg  = _jload()
                    info = get_current_list_pipeline_status(cfg)
                    rows = info.get("registered", [])
                    list_name = info.get("list_name", "?")
                    if not rows:
                        return (
                            f"No pipelines registered to list '{list_name}'. "
                            "Use jenkins_create_job to create one, or jenkins_link_pipeline "
                            "to associate an existing server job."
                        )
                    lines = [f"Pipelines for list '{list_name}':"]
                    for r in rows:
                        result = r.get("last_result") or "no builds yet"
                        build  = f" (#{r['last_build']})" if r.get("last_build") else ""
                        server = "" if r["exists_on_server"] else "  ⚠ NOT FOUND ON SERVER"
                        lines.append(
                            f"  • {r['job_name']}{server}  last={result}{build}"
                        )
                    return "\n".join(lines)
                except Exception as exc:
                    return f"Error: {exc}"

            elif name == "jenkins_list_jobs":
                from modules.jenkins_runner import (
                    load_config as _jload, list_jenkins_jobs, load_list_pipelines,
                )
                try:
                    cfg         = _jload()
                    all_jobs    = list_jenkins_jobs(cfg)
                    list_pipes  = set(load_list_pipelines())
                    if not all_jobs:
                        return "No Jenkins jobs found on server."
                    lines = [
                        f"Jenkins jobs on server ({len(all_jobs)} total). "
                        f"Current list has: {sorted(list_pipes) or 'none'}",
                        "",
                    ]
                    for j in all_jobs:
                        marker = " [THIS LIST]" if j["name"] in list_pipes else ""
                        status = "enabled" if j.get("buildable") else "disabled"
                        color  = j.get("color", "")
                        state  = color.replace("_anime", " (running)") if color else ""
                        lines.append(f"  • {j['name']}  [{status}]{marker}  {state}".rstrip())
                    return "\n".join(lines)
                except Exception as exc:
                    return f"Error listing jobs: {exc}"

            elif name == "jenkins_get_pipeline_script":
                from modules.jenkins_runner import (
                    load_config as _jload, load_pipeline_script,
                    save_pipeline_script, get_job_config, _extract_groovy_from_xml,
                )
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                # Try local cache first
                script = load_pipeline_script(job)
                if script:
                    return f"Pipeline script for '{job}' (local cache):\n\n{script}"
                # Not cached — fetch from server and cache it
                try:
                    cfg = _jload()
                    xml = get_job_config(cfg, job)
                    script = _extract_groovy_from_xml(xml)
                    if script:
                        save_pipeline_script(job, script)
                        return f"Pipeline script for '{job}' (fetched from server):\n\n{script}"
                    return (
                        f"No inline Groovy script found in '{job}' config. "
                        "This job may use an SCM-based Jenkinsfile (read from the git repo). "
                        "Use jenkins_get_config to see the full XML."
                    )
                except Exception as exc:
                    return f"Error fetching pipeline script for '{job}': {exc}"

            elif name == "jenkins_get_config":
                from modules.jenkins_runner import load_config as _jload, get_job_config
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                try:
                    cfg = _jload()
                    return get_job_config(cfg, job)
                except Exception as exc:
                    return f"Error getting config for '{job}': {exc}"

            elif name == "jenkins_create_job":
                from modules.jenkins_runner import (
                    load_config as _jload, create_jenkins_job, register_pipeline,
                )
                job = args.get("job_name", "").strip()
                xml = args.get("xml_config", "").strip()
                if not job or not xml:
                    return "Error: job_name and xml_config are required"
                try:
                    cfg = _jload()
                    create_jenkins_job(cfg, job, xml)
                    register_pipeline(job)
                    return (
                        f"Jenkins job '{job}' created and registered to the current device list. "
                        f"Call run_jenkins_checks to trigger it."
                    )
                except Exception as exc:
                    return f"Error creating job '{job}': {exc}"

            elif name == "jenkins_update_job":
                from modules.jenkins_runner import load_config as _jload, update_jenkins_job
                job = args.get("job_name", "").strip()
                xml = args.get("xml_config", "").strip()
                if not job or not xml:
                    return "Error: job_name and xml_config are required"
                try:
                    cfg = _jload()
                    update_jenkins_job(cfg, job, xml)
                    return f"Jenkins job '{job}' updated successfully."
                except Exception as exc:
                    return f"Error updating job '{job}': {exc}"

            elif name == "jenkins_delete_job":
                from modules.jenkins_runner import (
                    load_config as _jload, delete_jenkins_job, unregister_pipeline,
                )
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                try:
                    cfg = _jload()
                    delete_jenkins_job(cfg, job)
                    unregister_pipeline(job)
                    return f"Jenkins job '{job}' deleted from server and unregistered from the current list."
                except Exception as exc:
                    return f"Error deleting job '{job}': {exc}"

            elif name == "jenkins_link_pipeline":
                from modules.jenkins_runner import register_pipeline, load_list_pipelines
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                register_pipeline(job)
                pipes = load_list_pipelines()
                return f"Pipeline '{job}' linked to the current list. Current list pipelines: {pipes}"

            elif name == "jenkins_unlink_pipeline":
                from modules.jenkins_runner import unregister_pipeline, load_list_pipelines
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                unregister_pipeline(job)
                pipes = load_list_pipelines()
                return (
                    f"Pipeline '{job}' unlinked from the current list "
                    f"(job still exists on Jenkins server). Remaining: {pipes}"
                )

            elif name == "jenkins_get_builds":
                from modules.jenkins_runner import load_config as _jload, get_job_builds
                job   = args.get("job_name", "").strip()
                limit = int(args.get("limit", 10))
                if not job:
                    return "Error: job_name is required"
                try:
                    cfg    = _jload()
                    builds = get_job_builds(cfg, job, limit=limit)
                    if not builds:
                        return f"No builds found for '{job}'."
                    lines = [f"Recent builds for '{job}':"]
                    for b in builds:
                        ts  = b.get("timestamp", 0) // 1000
                        dt  = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "?"
                        dur = f"{b.get('duration', 0) // 1000}s"
                        res = b.get("result") or "IN_PROGRESS"
                        lines.append(f"  #{b.get('number')}  {res:<12}  {dt}  ({dur})")
                    return "\n".join(lines)
                except Exception as exc:
                    return f"Error getting builds for '{job}': {exc}"

            elif name == "jenkins_get_console":
                from modules.jenkins_runner import load_config as _jload, get_build_console
                job   = args.get("job_name", "").strip()
                build = args.get("build_number", "lastFailed")
                if not job:
                    return "Error: job_name is required"
                try:
                    cfg = _jload()
                    log = get_build_console(cfg, job, build_number=build)
                    # Trim very long logs — keep the tail where failures appear
                    if len(log) > 15000:
                        log = "… (log truncated — showing last 15000 chars)\n\n" + log[-15000:]
                    return f"Console log for '{job}' build={build}:\n\n{log}"
                except Exception as exc:
                    return f"Error fetching console log for '{job}': {exc}"

            elif name == "jenkins_enable_job":
                from modules.jenkins_runner import load_config as _jload, enable_jenkins_job
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                try:
                    cfg = _jload()
                    enable_jenkins_job(cfg, job)
                    return f"Jenkins job '{job}' enabled."
                except Exception as exc:
                    return f"Error enabling job '{job}': {exc}"

            elif name == "jenkins_disable_job":
                from modules.jenkins_runner import load_config as _jload, disable_jenkins_job
                job = args.get("job_name", "").strip()
                if not job:
                    return "Error: job_name is required"
                try:
                    cfg = _jload()
                    disable_jenkins_job(cfg, job)
                    return f"Jenkins job '{job}' disabled."
                except Exception as exc:
                    return f"Error disabling job '{job}': {exc}"

            elif name == "run_jenkins_checks":
                from modules.jenkins_runner import run_checks, format_summary
                delay = float(args.get("startup_delay", 0))
                summary = run_checks(startup_delay=delay)
                return format_summary(summary)

            elif name == "jenkins_wait_for_result":
                from modules.jenkins_runner import load_config as _jload, wait_for_build_results
                timeout = int(args.get("timeout", 600))
                try:
                    cfg    = _jload()
                    result = wait_for_build_results(cfg, timeout=timeout)
                except Exception as exc:
                    return f"Error waiting for build results: {exc}"

                if "error" in result:
                    return result["error"]

                jobs       = result.get("jobs", {})
                timed_out  = result.get("timed_out", False)
                lines      = []

                if timed_out:
                    lines.append(f"WARNING: Timed out after {timeout}s — some builds may still be running.\n")

                all_ok = all(j["ok"] for j in jobs.values())
                lines.append(f"Build results ({len(jobs)} pipeline(s)):")

                for job_name, info in jobs.items():
                    res  = info.get("result", "UNKNOWN")
                    num  = f"#{info['build']}" if info.get("build") else ""
                    url  = f"  {info['url']}" if info.get("url") else ""
                    mark = "✓" if info["ok"] else "✗"
                    lines.append(f"\n  {mark} {job_name} {num}  [{res}]{url}")
                    if not info["ok"] and info.get("console"):
                        lines.append(f"\n--- Console output ---\n{info['console']}\n--- End console ---")
                    elif not info["ok"] and info.get("console_error"):
                        lines.append(f"  (console fetch failed: {info['console_error']})")

                if all_ok:
                    lines.append("\nAll pipelines passed.")
                else:
                    failed = [n for n, i in jobs.items() if not i["ok"]]
                    lines.append(f"\nFailed pipelines: {', '.join(failed)}")
                    lines.append("Diagnose using the console output above, fix the root cause, then call run_jenkins_checks + jenkins_wait_for_result again.")

                return "\n".join(lines)

            elif name == "save_ansible_playbook":
                pb_name  = args.get("name", "Unnamed playbook").strip()
                pb_desc  = args.get("description", "").strip()
                keywords = [str(k).strip().lower() for k in args.get("keywords", [])]
                plays    = args.get("plays", [])
                explicit_id = args.get("playbook_id", "").strip()
                if not plays:
                    return "Error: plays list is required and must not be empty"

                pb_record = {
                    "name":        pb_name,
                    "description": pb_desc,
                    "keywords":    keywords,
                    "plays":       plays,
                    "updated_at":  time.strftime("%Y-%m-%d %H:%M"),
                }

                # If caller supplied an explicit ID, look it up and overwrite
                if explicit_id:
                    idx = _load_playbook_index()
                    match = next((p for p in idx if p["id"] == explicit_id), None)
                    if match is None:
                        return (
                            f"Error: playbook id '{explicit_id}' not found. "
                            f"Call list_ansible_playbooks to see valid IDs."
                        )
                    pb_record["id"]         = explicit_id
                    pb_record["created_at"] = match.get("created_at", pb_record["updated_at"])
                    yml_file = f"{explicit_id}.yml"
                    yml_path = os.path.join(_get_playbooks_dir(), yml_file)
                    with open(yml_path, "w", encoding="utf-8") as fh:
                        fh.write(_playbook_to_yaml(pb_record))
                    for i, p in enumerate(idx):
                        if p["id"] == explicit_id:
                            idx[i] = pb_record
                            break
                    _save_playbook_index(idx)
                    _dbg(f"save_ansible_playbook: updated '{pb_name}' (id={explicit_id})")
                    return (
                        f"Playbook UPDATED in-place: '{pb_name}' (id={explicit_id})\n"
                        f"Keywords: {', '.join(keywords)}\n"
                        f"Plays: {len(plays)} device(s)\n"
                        f"YAML overwritten: {yml_file}"
                    )

                # No explicit ID — upsert by name (deduplicates automatically)
                pb_record["created_at"] = time.strftime("%Y-%m-%d %H:%M")
                _, pb_id, is_update = _upsert_playbook(pb_record)
                action = "UPDATED" if is_update else "saved"
                _dbg(f"save_ansible_playbook: {action} '{pb_name}' (id={pb_id})")
                return (
                    f"Playbook {action}: '{pb_name}' (id={pb_id})\n"
                    f"Keywords: {', '.join(keywords)}\n"
                    f"Plays: {len(plays)} device(s)\n"
                    f"YAML written to: {pb_id}.yml"
                )

            elif name == "list_ansible_playbooks":
                idx = _load_playbook_index()
                if not idx:
                    return "No playbooks saved yet. Complete a configuration task and call save_ansible_playbook."
                lines = [f"Saved playbooks ({len(idx)} total):\n"]
                for pb in idx:
                    lines.append(
                        f"  id: {pb['id']}\n"
                        f"  name: {pb['name']}\n"
                        f"  description: {pb.get('description','')}\n"
                        f"  keywords: {', '.join(pb.get('keywords', []))}\n"
                        f"  devices: {', '.join(p.get('hostname') or p.get('device_ip','') for p in pb.get('plays',[]))}\n"
                        f"  created: {pb.get('created_at','')}\n"
                    )
                return "\n".join(lines)

            elif name == "run_ansible_playbook":
                playbook_id = args.get("playbook_id", "").strip()
                idx = _load_playbook_index()
                pb  = next((p for p in idx if p["id"] == playbook_id), None)
                if not pb:
                    ids = [p["id"] for p in idx]
                    return f"Error: playbook '{playbook_id}' not found. Available: {ids}"

                _IOS_ERR_PATS = (
                    "% Invalid input", "% Incomplete command", "% Ambiguous command",
                    "% Unknown command", "% Error", "% Bad", "% Command rejected",
                )
                def _ios_err(out: str) -> str:
                    for ln in out.splitlines():
                        if any(p in ln for p in _IOS_ERR_PATS):
                            return ln.strip()
                    return ""

                output_parts = [
                    f"Running playbook: {pb['name']}",
                    f"Description: {pb.get('description','')}",
                    f"Plays: {len(pb.get('plays',[]))} device(s)\n",
                ]
                all_ok = True
                for play in pb.get("plays", []):
                    device_ip = play.get("device_ip", "")
                    hostname  = play.get("hostname") or device_ip
                    commands  = play.get("commands", [])
                    output_parts.append(f"--- {hostname} ({device_ip}) ---")
                    device = _find_device(device_ip, devices_loader())
                    if not device:
                        output_parts.append(f"  ERROR: device {device_ip} not found in inventory")
                        all_ok = False
                        continue
                    play_mode = play.get("mode", "config")
                    try:
                        conn = _conn(device)
                        if play_mode == "config":
                            conn.config_mode()
                        try:
                            for cmd in commands:
                                out = run_device_command(conn, cmd)
                                err = _ios_err(out)
                                if err:
                                    output_parts.append(f"  [FAIL] {cmd}")
                                    output_parts.append(f"         {err}")
                                    all_ok = False
                                else:
                                    output_parts.append(f"  [OK]   {cmd}")
                        finally:
                            if play_mode == "config":
                                conn.exit_config_mode()
                    except Exception as exc:
                        output_parts.append(f"  ERROR: {exc}")
                        all_ok = False
                status = "COMPLETED SUCCESSFULLY" if all_ok else "COMPLETED WITH ERRORS"
                output_parts.append(f"\nPlaybook {status}")
                return "\n".join(output_parts)

            else:
                return f"Unknown tool: {name}"

        except Exception as exc:
            logger.error("Tool error [%s]: %s", name, exc, exc_info=True)
            return f"Error executing {name}: {exc}"

    def execute_tool_cached(name: str, args: dict) -> str:
        result = execute_tool(name, args)
        if not result.startswith("Error"):
            if args.get("mode") == "config":
                _tool_cache.clear()
                invalidate_topology_cache()
                for key in ("ip", "device_ips"):
                    val = args.get(key)
                    if isinstance(val, str):
                        invalidate_config_cache(val)
                    elif isinstance(val, list):
                        for ip in val:
                            invalidate_config_cache(ip)
            else:
                _cache_set(name, args, result)
        return result

    # -----------------------------------------------------------------
    # Per-tool output limits
    # -----------------------------------------------------------------
    _TOOL_CHAR_LIMITS = {
        # execute_command_on_multiple_devices handles per-device truncation
        # internally, so the global limit is set very high to avoid a second cut.
        "execute_command_on_multiple_devices": 500000,
        "get_running_config":                  100000,
        "get_network_topology":                 25000,
        "execute_commands_on_device":           80000,
        "execute_command":                      80000,
        "get_all_devices":                       4000,
        "backup_device_config":                  2000,
        "save_lab_note":                          500,
        "read_network_kb":                       10000,
        "update_network_kb":                       300,
        "read_app_file":                        100000,
        "patch_app_file":                          500,
        "restart_server":                          200,
        "git_commit":                             1000,
        "save_ansible_playbook":                  1000,
        "list_ansible_playbooks":                 8000,
        "run_ansible_playbook":                  50000,
        "run_jenkins_checks":                    10000,
        "jenkins_get_current_pipelines":           1000,
        "jenkins_list_jobs":                      2000,
        "jenkins_get_pipeline_script":           10000,
        "jenkins_get_config":                    20000,
        "jenkins_create_job":                     1000,
        "jenkins_update_job":                     1000,
        "jenkins_delete_job":                      500,
        "jenkins_get_builds":                     3000,
        "jenkins_get_console":                   20000,
        "jenkins_wait_for_result":               40000,
        "jenkins_enable_job":                      500,
        "jenkins_disable_job":                     500,
        "jenkins_link_pipeline":                   500,
        "jenkins_unlink_pipeline":                 500,
    }
    _DEFAULT_TOOL_CHARS = 80000

    # -----------------------------------------------------------------
    # Agentic loop
    # -----------------------------------------------------------------
    price      = provider_info.get("price", {})
    usage_total = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}

    api_messages  = list(history)
    max_iterations = 50
    iteration      = 0

    # Index of the current user turn in api_messages.  This message must
    # always appear in the trimmed window — otherwise Claude loses the task
    # description when the window fills with tool-result messages.
    _session_start_idx = len(api_messages) - 1

    try:
        while iteration < max_iterations:
            iteration += 1

            if _is_stopped(session_id):
                yield {"type": "interrupted", "content": "Stopped by user."}
                break

            if len(api_messages) > max_history + 1:
                # Always keep the current user turn (task description) visible.
                # Fill any remaining budget with the most-recent prior history
                # so Claude has context from the previous session as well.
                session_msgs = api_messages[_session_start_idx:]   # current turn + tool rounds
                prior_msgs   = api_messages[:_session_start_idx]   # older history

                if len(session_msgs) >= max_history:
                    # Session fills the window — pin user turn + most recent rounds
                    trimmed = [session_msgs[0]] + session_msgs[-(max_history - 1):]
                else:
                    # Fill remaining slots with recent prior context.
                    # Compress only the prior (older) messages — current session
                    # tool results must stay full-fidelity so Claude can read them.
                    budget      = max_history - len(session_msgs)
                    prior_trim  = _compress_history(prior_msgs[-budget:])
                    trimmed     = prior_trim + session_msgs
            else:
                trimmed = api_messages
            # No global _compress_history on trimmed — current-session results
            # are kept intact. Only prior context is compressed (done above).
            trimmed = _sanitize_for_api(trimmed)

            # Re-inject device/topology context prefix into the current user
            # turn (always session_msgs[0] = api_messages[_session_start_idx]).
            # Find it in trimmed by matching the clean user_message content.
            _prefix_injected = False
            if context_prefix and trimmed:
                for _ti, _tm in enumerate(trimmed):
                    if (_tm.get("role") == "user"
                            and isinstance(_tm.get("content"), str)
                            and _tm["content"] == user_message):
                        trimmed = (
                            trimmed[:_ti]
                            + [dict(_tm, content=context_prefix + "\n\n" + _tm["content"])]
                            + trimmed[_ti + 1:]
                        )
                        _prefix_injected = True
                        break
                # Fallback: inject into first user text message if not found above
                if not _prefix_injected:
                    for _ti, _tm in enumerate(trimmed):
                        if _tm.get("role") == "user" and isinstance(_tm.get("content"), str):
                            trimmed = (
                                trimmed[:_ti]
                                + [dict(_tm, content=context_prefix + "\n\n" + _tm["content"])]
                                + trimmed[_ti + 1:]
                            )
                            _prefix_injected = True
                            break

            # --- Diagnostic log: what is being sent to the API this iteration
            # Find where the current user task message sits in trimmed
            _task_msg_pos = next(
                (i for i, m in enumerate(trimmed)
                 if m.get("role") == "user"
                 and isinstance(m.get("content"), str)
                 and user_message in m.get("content", "")),
                None
            )
            _dbg(f"  ITER={iteration}  trimmed_msgs={len(trimmed)}"
                 f"  api_msgs_total={len(api_messages)}"
                 f"  prefix_injected={_prefix_injected}"
                 f"  task_msg_pos={_task_msg_pos}")
            if trimmed:
                _first_content = trimmed[0].get("content", "")
                if isinstance(_first_content, str):
                    _dbg(f"  FIRST_MSG_ROLE={trimmed[0]['role']}"
                         f"  FIRST_MSG_PREVIEW={_first_content[:300]!r}"
                         f"{'...' if len(_first_content) > 300 else ''}")
                else:
                    _dbg(f"  FIRST_MSG_ROLE={trimmed[0]['role']}"
                         f"  FIRST_MSG_CONTENT=<list of {len(_first_content)} blocks>")

            # ---- Call the Anthropic API ---------------------------------
            import anthropic as _anthropic
            _resp = None
            for _attempt in range(3):
                try:
                    cached_tools = [t.copy() for t in TOOLS]
                    cached_tools[-1] = dict(
                        cached_tools[-1], cache_control={"type": "ephemeral"}
                    )
                    _resp = _get_anthropic_client().messages.create(
                        model=model,
                        max_tokens=max_tokens_out,
                        system=[{
                            "type": "text",
                            "text": active_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }],
                        messages=trimmed,
                        tools=cached_tools,
                        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                    )
                    break
                except _anthropic.RateLimitError:
                    if _attempt == 2:
                        raise
                    _wait = 15 * (2 ** _attempt)
                    yield {"type": "rate_limit_wait", "seconds": _wait,
                           "content": f"Rate limit — retrying in {_wait}s…"}
                    time.sleep(_wait)

            u = _resp.usage
            usage_total["input"]       += getattr(u, "input_tokens", 0)
            usage_total["output"]      += getattr(u, "output_tokens", 0)
            usage_total["cache_write"] += getattr(u, "cache_creation_input_tokens", 0)
            usage_total["cache_read"]  += getattr(u, "cache_read_input_tokens", 0)

            asst_content = []
            for block in _resp.content:
                if block.type == "text":
                    yield {"type": "text", "content": block.text}
                    asst_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    asst_content.append({
                        "type": "tool_use",
                        "id":    block.id,
                        "name":  block.name,
                        "input": block.input,
                    })
            api_messages.append({"role": "assistant", "content": asst_content})
            stop_reason = _resp.stop_reason
            tool_calls  = [
                {"id": b.id, "name": b.name, "input": b.input}
                for b in _resp.content if b.type == "tool_use"
            ]

            # ---- Shared: stop if no tool calls --------------------------
            # Log the assistant's decision so we can see why it stopped or
            # what text it produced (critical for diagnosing off-task behaviour).
            _text_blocks = [
                b.get("text", b) if isinstance(b, dict) else getattr(b, "text", "")
                for b in (asst_content if isinstance(asst_content, list) else [])
                if (isinstance(b, dict) and b.get("type") == "text")
                   or (not isinstance(b, dict) and getattr(b, "type", None) == "text")
            ]
            _tool_names = [
                b.get("name", b) if isinstance(b, dict) else getattr(b, "name", "")
                for b in (asst_content if isinstance(asst_content, list) else [])
                if (isinstance(b, dict) and b.get("type") == "tool_use")
                   or (not isinstance(b, dict) and getattr(b, "type", None) == "tool_use")
            ]
            _text_preview = " | ".join(_text_blocks)[:400] if _text_blocks else ""
            _dbg(f"  RESPONSE stop_reason={stop_reason!r}"
                 f"  tools={_tool_names}"
                 f"  text_preview={_text_preview!r}")

            # Save a checkpoint after any iteration where Claude produces
            # meaningful prose (observations, plans, confirmations).
            # This lets "continue" resume without re-verifying gathered state.
            _full_text = " ".join(_text_blocks).strip()
            if _full_text and len(_full_text) > 40:
                _save_checkpoint(
                    session_id  = session_id,
                    task        = user_message[:200],
                    progress    = _full_text[:1500],  # cap to avoid huge checkpoints
                    iteration   = iteration,
                )

            if stop_reason == "max_tokens":
                # Claude hit the output token limit mid-response.  The tool
                # calls it intended to make were truncated.  Inject a short
                # user nudge so the next iteration continues the task rather
                # than starting fresh or treating this as done.
                _dbg("  !! max_tokens hit — injecting continuation nudge")
                api_messages.append({
                    "role":    "user",
                    "content": "Your previous response was cut off by the token limit. "
                               "Please continue exactly where you left off — "
                               "make the tool calls you were about to make.",
                })
                continue   # next iteration, Claude will proceed from here

            if stop_reason not in ("tool_use", "tool_calls"):
                break

            # ---- Shared: announce + run tools ---------------------------
            for tc in tool_calls:
                yield {
                    "type":  "tool_start",
                    "id":    tc["id"],
                    "tool":  tc["name"],
                    "label": _tool_label(tc["name"], tc["input"]),
                    "args":  tc["input"],
                }

            def _run_tc(tc):
                return tc, execute_tool_cached(tc["name"], tc["input"])

            raw_results = {}
            if len(tool_calls) == 1:
                tc, res = _run_tc(tool_calls[0])
                raw_results[tc["id"]] = (tc, res)
            else:
                with ThreadPoolExecutor(max_workers=len(tool_calls)) as ex:
                    for tc, res in ex.map(_run_tc, tool_calls):
                        raw_results[tc["id"]] = (tc, res)

            tool_results_anthropic = []   # appended to api_messages (Anthropic format)
            for tc in tool_calls:
                _, result = raw_results[tc["id"]]
                limit     = _TOOL_CHAR_LIMITS.get(tc["name"], _DEFAULT_TOOL_CHARS)
                if len(result) > limit:
                    truncated = (
                        result[:limit]
                        + f"\n... [output clipped at {limit} chars — use IOS pipe filters"
                          f" (| include, | section, | begin) to get targeted output]"
                    )
                else:
                    truncated = result
                yield {
                    "type":    "tool_result",
                    "id":      tc["id"],
                    "tool":    tc["name"],
                    "content": truncated,
                }
                tool_results_anthropic.append({
                    "type":        "tool_result",
                    "tool_use_id": tc["id"],
                    "content":     truncated,
                })

            api_messages.append({"role": "user", "content": tool_results_anthropic})

            # Save progress after every completed iteration so that if this
            # task times out or the connection drops, the user can say
            # "continue" and Claude resumes from here instead of starting over.
            # Keep full context in memory; strip prefix only for disk storage.
            _progress = _compress_history(api_messages)
            _chat_histories[session_id] = _progress
            _save_history_to_disk(session_id, _compress_for_disk(api_messages))

            if _is_stopped(session_id):
                yield {"type": "interrupted", "content": "Stopped by user."}
                break

        if iteration >= max_iterations:
            _dbg(f"  !! max_iterations ({max_iterations}) reached — loop stopped")
            yield {"type": "text", "content": f"\n\n⚠️ Reached the maximum of {max_iterations} steps. Say **continue** to resume."}

        # Keep full context in memory for this session; strip prefix for disk.
        compressed = _compress_history(api_messages)
        _chat_histories[session_id] = compressed
        _save_history_to_disk(session_id, _compress_for_disk(api_messages))

        # Emit usage/cost event
        cost = sum(
            (usage_total.get(k, 0) / 1_000_000) * price.get(k, 0)
            for k in ("input", "output", "cache_write", "cache_read")
        )
        yield {
            "type":        "usage",
            "input":       usage_total["input"],
            "output":      usage_total["output"],
            "cache_write": usage_total["cache_write"],
            "cache_read":  usage_total["cache_read"],
            "cost_usd":    round(cost, 6),
        }
        yield {"type": "done"}

    except Exception as exc:
        logger.error("AI agent error: %s", exc, exc_info=True)
        yield {"type": "error", "content": str(exc)}
        yield {"type": "done"}


# ---------------------------------------------------------------------------
# Direct playbook execution (bypasses Claude API entirely)
# ---------------------------------------------------------------------------
def run_ansible_direct(
    session_id: str,
    user_message: str,
    playbook: dict,
    devices_loader,
    status_cache: dict,
    connections_pool: dict,
    pool_lock,
) -> "Iterator[dict]":
    """
    Run a matched Ansible playbook without calling the Claude API.

    Yields granular per-play SSE events so the frontend can render a live
    progress modal.  Event types beyond the standard set:
      ansible_start  — playbook kicked off  {name, description, total_plays}
      ansible_play_start — a play began     {index, hostname, device_ip, cmd_count}
      ansible_play_result — a play finished {index, hostname, device_ip, ok,
                                             output, error, cmd_count}
      ansible_done   — all plays complete   {ok, name}
    """
    from modules.commands import run_device_command
    from modules.connection import get_persistent_connection

    pb_name  = playbook.get("name", playbook.get("id", "playbook"))
    pb_desc  = playbook.get("description", "")
    plays    = playbook.get("plays", [])

    yield {"type": "provider", "id": "ansible", "name": "Ansible Playbook", "model": "local"}
    yield {
        "type":        "ansible_start",
        "name":        pb_name,
        "description": pb_desc,
        "total_plays": len(plays),
        "playbook_id": playbook.get("id", ""),
    }

    # IOS error patterns — any of these in command output means the command failed.
    _IOS_ERRORS = (
        "% Invalid input",
        "% Incomplete command",
        "% Ambiguous command",
        "% Unknown command",
        "% Error",
        "% Bad",
        "% Command rejected",
        "% Not supported",
    )

    def _ios_error(output: str) -> str:
        """Return the first IOS error line found in output, or empty string."""
        for line in output.splitlines():
            if any(pat in line for pat in _IOS_ERRORS):
                return line.strip()
        return ""

    def _find_device(ip, devices):
        return next((d for d in devices if d.get("ip") == ip), None)

    def _conn(device):
        return get_persistent_connection(device, connections_pool, pool_lock)

    all_ok = True
    failed_plays = []   # collected for ansible_done so the UI can auto-troubleshoot

    for idx, play in enumerate(plays):
        device_ip = play.get("device_ip", "")
        hostname  = play.get("hostname") or device_ip
        commands  = play.get("commands", [])

        yield {
            "type":      "ansible_play_start",
            "index":     idx,
            "hostname":  hostname,
            "device_ip": device_ip,
            "cmd_count": len(commands),
        }

        device = _find_device(device_ip, devices_loader())
        if not device:
            all_ok = False
            yield {
                "type":      "ansible_play_result",
                "index":     idx,
                "hostname":  hostname,
                "device_ip": device_ip,
                "ok":        False,
                "commands":  [],
                "error":     f"Device {device_ip} not found in inventory",
                "cmd_count": len(commands),
            }
            continue

        cmd_results = []   # list of {cmd, output, ok, ios_error}
        play_exception = None
        play_has_ios_error = False
        play_mode = play.get("mode", "config")

        try:
            conn = _conn(device)
            if play_mode == "config":
                conn.config_mode()
            try:
                for cmd in commands:
                    out = run_device_command(conn, cmd)
                    err = _ios_error(out)
                    cmd_ok = not bool(err)
                    if not cmd_ok:
                        play_has_ios_error = True
                    cmd_results.append({
                        "cmd":       cmd,
                        "output":    out.strip(),
                        "ok":        cmd_ok,
                        "ios_error": err,
                    })
            finally:
                if play_mode == "config":
                    conn.exit_config_mode()
        except Exception as exc:
            play_exception = str(exc)

        play_ok = (play_exception is None) and (not play_has_ios_error)
        if not play_ok:
            all_ok = False

        # Build a top-level error summary for failed plays
        if play_exception:
            top_error = play_exception
        elif play_has_ios_error:
            bad = [r for r in cmd_results if not r["ok"]]
            top_error = f"{len(bad)} command(s) rejected by IOS"
        else:
            top_error = None

        yield {
            "type":      "ansible_play_result",
            "index":     idx,
            "hostname":  hostname,
            "device_ip": device_ip,
            "ok":        play_ok,
            "commands":  cmd_results,
            "error":     top_error,
            "cmd_count": len(commands),
        }

        if not play_ok:
            failed_plays.append({
                "hostname":  hostname,
                "device_ip": device_ip,
                "error":     top_error,
                # Only include failed commands to keep the payload concise
                "commands":  [c for c in cmd_results if not c["ok"]],
            })

    yield {
        "type":        "ansible_done",
        "ok":          all_ok,
        "name":        pb_name,
        "failed_plays": failed_plays,
    }
    yield {"type": "usage", "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "cost_usd": 0.0}
    yield {"type": "done"}
