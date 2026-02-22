from django.test import SimpleTestCase

from core.ai_engine.retrieval.infrastructure.metrics import attach_stage_timings, enrich_response_meta


class MetricsEnrichmentTests(SimpleTestCase):
    def test_enrich_response_meta_defaults(self):
        out = enrich_response_meta({})
        self.assertEqual(out.get("pipeline"), "rag_semantic")
        self.assertEqual(out.get("intent_route"), "default_rag")
        self.assertEqual(out.get("validation"), "not_applicable")
        self.assertEqual(out.get("answer_mode"), "factual")
        self.assertEqual(out.get("retrieval_docs_count"), 0)
        self.assertEqual(out.get("structured_returned"), 0)

    def test_enrich_response_meta_passthrough_existing(self):
        out = enrich_response_meta(
            {
                "pipeline": "structured_analytics",
                "intent_route": "analytical_tabular",
                "validation": "passed",
                "answer_mode": "evaluative",
                "retrieval_docs_count": 9,
                "top_score": 0.8,
                "structured_returned": 3,
            }
        )
        self.assertEqual(out.get("pipeline"), "structured_analytics")
        self.assertEqual(out.get("intent_route"), "analytical_tabular")
        self.assertEqual(out.get("validation"), "passed")
        self.assertEqual(out.get("answer_mode"), "evaluative")
        self.assertEqual(out.get("retrieval_docs_count"), 9)
        self.assertEqual(out.get("top_score"), 0.8)
        self.assertEqual(out.get("structured_returned"), 3)

    def test_attach_stage_timings(self):
        out = attach_stage_timings({}, route_ms=4, structured_ms=9, retrieval_ms=11, llm_ms=13)
        stage = out.get("stage_timings_ms") or {}
        self.assertEqual(stage.get("route_ms"), 4)
        self.assertEqual(stage.get("structured_ms"), 9)
        self.assertEqual(stage.get("retrieval_ms"), 11)
        self.assertEqual(stage.get("llm_ms"), 13)
