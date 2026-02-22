from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class RagSemanticBenchmarkCommandTests(SimpleTestCase):
    @patch("core.management.commands.rag_semantic_benchmark._ask")
    def test_benchmark_prints_on_off_comparison(self, ask_mock):
        def _fake_ask(*, user_id, query, request_id):
            import os

            _ = (user_id, query, request_id)
            flag = str(os.environ.get("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", "0"))
            if flag == "1":
                return {"meta": {"stage_timings_ms": {"retrieval_ms": 20, "llm_ms": 40}}}
            return {"meta": {"stage_timings_ms": {"retrieval_ms": 30, "llm_ms": 60}}}

        ask_mock.side_effect = _fake_ask

        out = StringIO()
        call_command(
            "rag_semantic_benchmark",
            user_id=1,
            iterations=2,
            queries=["apa itu sks?", "apa syarat lulus skripsi?"],
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("RAG Semantic Benchmark", text)
        self.assertIn("OFF  (RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=0)", text)
        self.assertIn("ON   (RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED=1)", text)
        self.assertIn("Delta ON-OFF", text)
        self.assertIn("Threshold Gate: PASSED", text)

    @patch("core.management.commands.rag_semantic_benchmark._ask")
    def test_benchmark_threshold_gate_fails(self, ask_mock):
        def _fake_ask(*, user_id, query, request_id):
            import os

            _ = (user_id, query, request_id)
            flag = str(os.environ.get("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", "0"))
            if flag == "1":
                return {"meta": {"stage_timings_ms": {"retrieval_ms": 9999, "llm_ms": 9999}}}
            return {"meta": {"stage_timings_ms": {"retrieval_ms": 10, "llm_ms": 10}}}

        ask_mock.side_effect = _fake_ask
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "rag_semantic_benchmark",
                user_id=1,
                iterations=1,
                queries=["apa itu sks?"],
                max_on_p95_total_ms=1,
                max_on_p95_retrieval_ms=1,
                max_on_p95_llm_ms=1,
                max_on_error_rate_pct=0.0,
                stdout=out,
            )

    @patch("core.management.commands.rag_semantic_benchmark._ask")
    def test_benchmark_delta_gate_fails(self, ask_mock):
        def _fake_ask(*, user_id, query, request_id):
            import os

            _ = (user_id, query, request_id)
            flag = str(os.environ.get("RAG_SEMANTIC_OPTIMIZED_RETRIEVAL_ENABLED", "0"))
            if flag == "1":
                return {"meta": {"stage_timings_ms": {"retrieval_ms": 300, "llm_ms": 400}}}
            return {"meta": {"stage_timings_ms": {"retrieval_ms": 10, "llm_ms": 20}}}

        ask_mock.side_effect = _fake_ask
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "rag_semantic_benchmark",
                user_id=1,
                iterations=1,
                queries=["apa itu sks?"],
                max_on_p95_total_ms=99999,
                max_on_p95_retrieval_ms=99999,
                max_on_p95_llm_ms=99999,
                max_on_error_rate_pct=100.0,
                max_delta_p95_total_ms=1,
                max_delta_p95_retrieval_ms=1,
                max_delta_p95_llm_ms=1,
                stdout=out,
            )
