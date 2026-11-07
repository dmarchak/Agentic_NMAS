"""Controller apps (the SDN design (rev. 4), section 12, I-2): generic controller code whose
network specifics come from its config. Phase P1 publishes the manifest's schema and its loader
(`manifest`); an app's lifecycle is the one jobs follow (`modules/jobs/lifecycle.py`). P6's
deploy channel is `channel` (staging from blobs, the plan), `conformance` (T17) and
`post_check` (the bounded post-check, rollback and drift).
docs/DEVELOPING_JOBS_AND_APPS.md is the guide."""

from modules.apps.manifest import Manifest, ManifestError, load_manifest, parse_manifest, \
    validate_config

__all__ = ["Manifest", "ManifestError", "load_manifest", "parse_manifest", "validate_config"]
