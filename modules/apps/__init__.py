"""Controller apps (the SDN design (rev. 4), section 12, I-2): generic controller code whose
network specifics come from its config. Phase P1 publishes the manifest's schema and its loader
(`manifest`); an app's lifecycle is the one jobs follow (`modules/jobs/lifecycle.py`). P6's
deploy channel is `channel` (staging from blobs, the plan), `conformance` (T17) and
`post_check` (the bounded post-check, rollback and drift).
docs/DEVELOPING_JOBS_AND_APPS.md is the guide."""

__all__ = ["Manifest", "ManifestError", "load_manifest", "parse_manifest", "validate_config"]


def __getattr__(name):
    """The manifest's names, imported when first asked for (PEP 562), so importing the package
    needs nothing outside the standard library: `scripts/nmas-harness` imports
    `modules.apps.test_run` and `channel` on CI's bare harness Python, which has no PyYAML
    (59fa89ba's CI, "No module named 'yaml'")."""
    if name in __all__:
        from modules.apps import manifest
        return getattr(manifest, name)
    raise AttributeError(f"module 'modules.apps' has no attribute {name!r}")
