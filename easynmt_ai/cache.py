"""Cache contracts for generated AI artifacts.

Redis is intentionally not selected here. Engines depend on this small contract,
so a persistent implementation can be introduced without changing engine code.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Protocol


class AICache(Protocol):
    """Provider-neutral cache interface for serialized engine output."""

    def get(self, namespace: str, key: str) -> Optional[Mapping[str, Any]]:
        """Return a previously serialized value or ``None`` on a miss."""

    def set(
        self,
        namespace: str,
        key: str,
        value: Mapping[str, Any],
        *,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Persist a serialized value for a future request."""


class NullAICache:
    """Default no-op cache used until a real backend is configured."""

    def get(self, namespace: str, key: str) -> Optional[Mapping[str, Any]]:
        return None

    def set(
        self,
        namespace: str,
        key: str,
        value: Mapping[str, Any],
        *,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        return None


def build_cache_key(*parts: object) -> str:
    """Build a deterministic, backend-safe key from JSON-compatible values."""

    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
