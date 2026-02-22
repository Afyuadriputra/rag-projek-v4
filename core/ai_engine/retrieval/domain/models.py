from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QueryContext:
    user_id: int
    query: str
    request_id: str = "-"
    doc_ids: Optional[List[int]] = None
    mentions: List[str] = field(default_factory=list)


@dataclass
class RetrievalPlan:
    route: str = "default_rag"
    mode: str = "doc_background"
    dense_k: int = 30
    bm25_k: int = 40
    rerank_top_n: int = 8
    use_hybrid: bool = False
    use_rerank: bool = False
    use_query_rewrite: bool = False


@dataclass
class AnswerEnvelope:
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredResult:
    ok: bool
    answer: str
    sources: List[Dict[str, Any]]
    doc_type: str
    facts: List[Dict[str, Any]]
    stats: Dict[str, Any]
    reason: str
