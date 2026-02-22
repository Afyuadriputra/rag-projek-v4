from __future__ import annotations

from dataclasses import dataclass
from typing import List
from unittest.mock import patch

from django.test import SimpleTestCase
from langchain_core.documents import Document

from core.ai_engine.retrieval.application.semantic_service import run_semantic
from core.ai_engine.retrieval.config.settings import RetrievalSettings


@dataclass(frozen=True)
class _Case:
    query: str
    intent_route: str
    has_docs_hint: bool
    docs_count: int
    expected_validation: str


_CASES: List[_Case] = [
    _Case("apa itu sks", "default_rag", True, 1, "not_applicable"),
    _Case("apa syarat lulus skripsi", "semantic_policy", True, 1, "not_applicable"),
    _Case("jurusan apa yang cocok jadi HRD", "default_rag", True, 1, "not_applicable"),
    _Case("nilai saya berapa", "default_rag", True, 0, "no_grounding_evidence"),
    _Case("jadwal saya hari senin jam 07.00", "default_rag", True, 0, "no_grounding_evidence"),
    _Case("ringkas dokumen akademik saya", "default_rag", True, 1, "not_applicable"),
]


def _docs_for(count: int) -> List[Document]:
    return [
        Document(
            page_content=f"Konten akademik {idx}",
            metadata={"source": "doc.pdf", "doc_id": "1", "user_id": "1"},
        )
        for idx in range(max(int(count), 0))
    ]


class SemanticParityLegacyVsOptimizedTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.main._ask_bot_legacy")
    def test_parity_semantic_matrix(self, legacy_ask_mock):
        def _legacy_side_effect(*, user_id, query, request_id):
            case = next(c for c in _CASES if c.query == query)
            sources = [{"source": "doc.pdf"}] if case.docs_count > 0 else []
            return {
                "answer": f"legacy::{query}",
                "sources": sources,
                "meta": {
                    "pipeline": "rag_semantic",
                    "intent_route": case.intent_route,
                    "validation": case.expected_validation,
                    "retrieval_docs_count": len(sources),
                    "top_score": 0.8 if sources else 0.0,
                    "stage_timings_ms": {"retrieval_ms": 1, "llm_ms": 1},
                },
            }

        legacy_ask_mock.side_effect = _legacy_side_effect

        for case in _CASES:
            with patch(
                "core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings",
                return_value=RetrievalSettings(semantic_optimized_retrieval_enabled=False),
            ):
                legacy_out = run_semantic(
                    user_id=1,
                    query=case.query,
                    request_id="rid-legacy",
                    intent_route=case.intent_route,
                    has_docs_hint=case.has_docs_hint,
                    resolved_doc_ids=[],
                    resolved_titles=[],
                    unresolved_mentions=[],
                    ambiguous_mentions=[],
                )

            with patch(
                "core.ai_engine.retrieval.application.semantic_service.get_retrieval_settings",
                return_value=RetrievalSettings(semantic_optimized_retrieval_enabled=True),
            ), patch(
                "core.ai_engine.retrieval.application.semantic_service.get_vectorstore",
                return_value=object(),
            ), patch(
                "core.ai_engine.retrieval.application.semantic_service.run_retrieval",
                return_value={
                    "mode": "doc_background",
                    "docs": _docs_for(case.docs_count),
                    "dense_hits": case.docs_count,
                    "top_score": 0.9 if case.docs_count else 0.0,
                    "retrieval_ms": 5,
                },
            ), patch(
                "core.ai_engine.retrieval.application.semantic_service.run_answer",
                return_value={
                    "ok": True,
                    "text": f"optimized::{case.query}",
                    "model": "m",
                    "llm_ms": 7,
                    "fallback_used": False,
                },
            ), patch("core.ai_engine.retrieval.main._ask_bot_legacy") as legacy_guard_mock:
                optimized_out = run_semantic(
                    user_id=1,
                    query=case.query,
                    request_id="rid-opt",
                    intent_route=case.intent_route,
                    has_docs_hint=case.has_docs_hint,
                    resolved_doc_ids=[],
                    resolved_titles=[],
                    unresolved_mentions=[],
                    ambiguous_mentions=[],
                )
                legacy_guard_mock.assert_not_called()

            self.assertEqual(legacy_out.get("meta", {}).get("pipeline"), "rag_semantic")
            self.assertEqual(optimized_out.get("meta", {}).get("pipeline"), "rag_semantic")
            self.assertEqual(
                optimized_out.get("meta", {}).get("validation"),
                legacy_out.get("meta", {}).get("validation"),
            )
            self.assertEqual(
                optimized_out.get("meta", {}).get("validation"),
                case.expected_validation,
            )
            self.assertTrue(str(legacy_out.get("answer") or "").strip())
            self.assertTrue(str(optimized_out.get("answer") or "").strip())
