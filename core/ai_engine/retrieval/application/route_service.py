from __future__ import annotations

import hashlib
from typing import Any, Dict

from django.core.cache import cache

from ..config.settings import get_retrieval_settings
from ..intent_router import route_intent


def resolve_route(query: str, router_enabled: bool = True) -> Dict[str, Any]:
    if not router_enabled:
        return {"route": "default_rag", "reason": "router_disabled", "matched": []}
    q = str(query or "").strip().lower()
    settings = get_retrieval_settings()
    ttl_s = max(int(settings.rag_route_cache_ttl_s), 0)
    if not q or ttl_s <= 0:
        return route_intent(query)
    q_hash = hashlib.md5(q.encode("utf-8")).hexdigest()
    ck = f"rag:route:v1:{q_hash}"
    cached = cache.get(ck)
    if isinstance(cached, dict):
        return cached
    out = route_intent(query)
    cache.set(ck, out, ttl_s)
    return out
