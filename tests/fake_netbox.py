"""An in-memory stand-in for the NetBox REST API.

Not named test_* so pytest does not collect it. Implements just enough of the
API surface that modules/netbox_client.py uses: paginated list GETs with simple
equality filtering, GET-by-id, POST (assigning ids), PATCH (merging), DELETE.

Used to compare a dry-run preview against a real execution against identical
starting state.
"""

import json
import re


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def text(self):
        return json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeNetBox:
    """A minimal NetBox. ``store`` maps endpoint -> list of object dicts."""

    def __init__(self):
        self.store: dict = {}
        self._next_id = 1
        self.posts: list = []      # (endpoint, payload) in order
        self.patches: list = []    # (endpoint, obj_id, payload)
        self.deletes: list = []    # (endpoint, obj_id)
        self.verify = True
        self.headers = {}

    # ── helpers ─────────────────────────────────────────────────────────────

    def seed(self, endpoint, obj):
        """Pre-populate an object, as if a human had created it in NetBox."""
        obj = dict(obj)
        obj.setdefault("id", self._take_id())
        obj.setdefault("tags", [])
        self.store.setdefault(endpoint.strip("/"), []).append(obj)
        return obj

    def _take_id(self):
        val = self._next_id
        self._next_id += 1
        return val

    @staticmethod
    def _parse(url):
        """Split an API url into (endpoint, object_id|None)."""
        path = re.sub(r"^.*?/api/", "", url).strip("/")
        parts = path.split("/")
        if parts and parts[-1].isdigit():
            return "/".join(parts[:-1]), int(parts[-1])
        return path, None

    @staticmethod
    def _matches(obj, params):
        for key, value in (params or {}).items():
            if key in ("limit", "offset", "brief", "depth"):
                continue
            if key == "q":                       # fuzzy search: substring on name
                if str(value).lower() not in str(obj.get("name", "")).lower():
                    return False
                continue
            candidates = [key]
            if key.endswith("_id"):
                candidates.append(key[:-3])
            for cand in candidates:
                if cand in obj:
                    actual = obj[cand]
                    if isinstance(actual, dict):
                        actual = actual.get("id", actual.get("name"))
                    if str(actual) != str(value):
                        return False
                    break
            else:
                return False                      # filtered on a field we lack
        return True

    # ── requests.Session surface ────────────────────────────────────────────

    def get(self, url, params=None, timeout=None):
        endpoint, obj_id = self._parse(url)
        items = self.store.get(endpoint, [])
        if obj_id is not None:
            for obj in items:
                if obj["id"] == obj_id:
                    return FakeResponse(obj)
            return FakeResponse({"detail": "Not found."}, 404)
        hits = [o for o in items if self._matches(o, params)]
        return FakeResponse({"results": hits, "next": None, "count": len(hits)})

    def post(self, url, json=None, timeout=None):
        endpoint, _ = self._parse(url)
        payload = dict(json or {})
        self.posts.append((endpoint, dict(payload)))
        obj = dict(payload)
        obj["id"] = self._take_id()
        obj.setdefault("tags", [])
        # NetBox returns tags as objects; the client sends ids.
        obj["tags"] = [{"id": t, "slug": self._tag_slug(t), "name": self._tag_slug(t)}
                       if isinstance(t, int) else t for t in obj["tags"]]
        self.store.setdefault(endpoint, []).append(obj)
        return FakeResponse(obj, 201)

    def patch(self, url, json=None, timeout=None):
        endpoint, obj_id = self._parse(url)
        payload = dict(json or {})
        self.patches.append((endpoint, obj_id, dict(payload)))
        for obj in self.store.get(endpoint, []):
            if obj["id"] == obj_id:
                obj.update(payload)
                return FakeResponse(obj)
        return FakeResponse({"detail": "Not found."}, 404)

    def delete(self, url, timeout=None):
        endpoint, obj_id = self._parse(url)
        self.deletes.append((endpoint, obj_id))
        items = self.store.get(endpoint, [])
        for i, obj in enumerate(items):
            if obj["id"] == obj_id:
                items.pop(i)
                return FakeResponse({}, 204)
        return FakeResponse({"detail": "Not found."}, 404)

    def _tag_slug(self, tag_id):
        for obj in self.store.get("extras/tags", []):
            if obj["id"] == tag_id:
                return obj.get("slug", "")
        return ""

    # ── assertions ──────────────────────────────────────────────────────────

    def created_counts(self):
        counts: dict = {}
        for endpoint, _ in self.posts:
            counts[endpoint] = counts.get(endpoint, 0) + 1
        return counts

    def objects(self, endpoint):
        return self.store.get(endpoint.strip("/"), [])
