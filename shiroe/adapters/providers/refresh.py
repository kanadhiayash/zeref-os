"""``shiroe providers refresh`` — partial, honest self-update (SHR-60 PART C).

Only two facts have a machine-readable authoritative source: whether a
model id still exists, and (derived from that) whether it should now be
considered ``retired``. Both come from a provider's ``list-models``
endpoint, which the account already has credentials for and which sends no
user payload — it is a GET with no body, so it's privacy-safe by
construction.

Everything else in the v2 capability record — context window, output
limit, pricing, tool/modality support, retention class — has **no**
machine-readable source. This module never touches those fields. It is not
allowed to scrape HTML docs and guess; a refresh that always reports green
is not a gate, so it says plainly which fields it did not check.

Connector-gated (opt-in) via the same ``require_connector`` pattern used by
LLM grading. OFF by default, so it is OFF in CI and never runs during the test
suite unless a test explicitly monkeypatches around the gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shiroe.adapters.providers.base import PROVIDER_SCHEMA_V2

_PKG_DIR = Path(__file__).parent

# Fields with no machine-readable authoritative source. Refresh never
# writes to these — they stay whatever a human last verified, and this
# list is reported back so the caller knows what refresh did *not* check.
STALE_ON_REFRESH: tuple[str, ...] = (
    "context_window", "max_output_tokens", "endpoint", "modalities",
    "supports_tools", "supports_structured_output", "region", "retention_class",
)

_LIST_MODELS_ENDPOINTS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1/models",
    "openai": "https://api.openai.com/v1/models",
}


def _lifecycle_from_presence(current: str, present: bool) -> str:
    """The only lifecycle transition refresh is allowed to make on its own.

    Presence graduates an ``unknown`` id to ``active`` (existence is exactly
    what list-models can confirm). Presence does *not* undo a human-recorded
    ``deprecated`` — a model commonly stays listed and callable throughout
    its deprecation window, so continuing to appear is not evidence it is
    no longer deprecated. Absence is treated as ``retired``: the id no
    longer resolves on this account, which is itself machine-confirmed.
    """
    if present:
        return "active" if current == "unknown" else current
    return "retired"


def _list_model_ids(provider: str) -> tuple[set[str], str, str]:
    """GET the provider's list-models endpoint. No request body — no user
    payload ever leaves the machine on this path."""
    url = _LIST_MODELS_ENDPOINTS.get(provider)
    if url is None:
        raise ValueError(
            f"no list-models endpoint known for provider {provider!r} "
            f"(have: {', '.join(sorted(_LIST_MODELS_ENDPOINTS))})"
        )
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set; cannot call list-models")
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:  # openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set; cannot call list-models")
        headers = {"Authorization": f"Bearer {api_key}"}

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"list-models failed for {provider!r}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"list-models unreachable for {provider!r}: {exc.reason}") from exc

    digest = hashlib.sha256(body).hexdigest()[:16]
    data = json.loads(body.decode("utf-8"))
    ids = {item["id"] for item in data.get("data", []) if "id" in item}
    return ids, digest, url


def _apply_refresh(data: dict, ids: set[str], url: str, digest: str, checked_at: str) -> list[dict]:
    """Pure mutation of a loaded v2 registry dict. No network, no I/O — the
    part that gets unit-tested directly (network is gated + untestable in
    CI by design)."""
    if data.get("schema") != PROVIDER_SCHEMA_V2:
        raise ValueError(
            f"refresh requires schema {PROVIDER_SCHEMA_V2!r}, got {data.get('schema')!r}"
        )
    changed: list[dict] = []
    for cls, entry in data.get("classes", {}).items():
        present = entry.get("model_id") in ids
        current_lifecycle = entry.get("lifecycle", "unknown")
        new_lifecycle = _lifecycle_from_presence(current_lifecycle, present)
        if new_lifecycle == current_lifecycle:
            continue
        entry["lifecycle"] = new_lifecycle
        entry["verified_at"] = checked_at
        entry["verified_by"] = "api"
        entry["source_url"] = url
        changed.append({
            "class": cls,
            "model_id": entry.get("model_id"),
            "lifecycle": {"from": current_lifecycle, "to": new_lifecycle},
            "response_digest": digest,
        })
    return changed


def refresh_provider(provider: str, *, project_root: Path | None = None) -> dict:
    """Refresh model existence/lifecycle for one provider from its
    list-models endpoint. Requires the ``provider_refresh`` connector to be
    enabled (SHARING_POLICY.md or ``SHIROE_ALLOW_CONNECTOR=provider_refresh``)
    — disabled by default, so this is a no-op-by-refusal in CI and tests.
    """
    from shiroe.memory import discover_project_root
    from shiroe.security import load_policy, require_connector

    root = project_root or discover_project_root()
    policy = load_policy(root)
    require_connector(policy, "provider_refresh", purpose=f"providers-refresh:{provider}")

    path = _PKG_DIR / f"{provider}.json"
    if not path.exists():
        raise KeyError(f"no provider registry {provider!r} at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))

    ids, digest, url = _list_model_ids(provider)
    checked_at = datetime.now(timezone.utc).date().isoformat()
    changed = _apply_refresh(data, ids, url, digest, checked_at)

    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {
        "provider": provider,
        "endpoint": url,
        "response_digest": digest,
        "checked_at": checked_at,
        "ids_seen": len(ids),
        "changed": changed,
        "stale_fields_not_checked": list(STALE_ON_REFRESH),
    }
