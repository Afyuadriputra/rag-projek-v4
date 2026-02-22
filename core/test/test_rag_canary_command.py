from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from core.models import RagRequestMetric


class RagCanaryCommandTests(TestCase):
    def test_rag_canary_report_prints_summary(self):
        user = User.objects.create_user(username="u1", password="x")
        RagRequestMetric.objects.create(
            request_id="r1",
            user=user,
            mode="structured_transcript",
            retrieval_ms=100,
            rerank_ms=10,
            llm_time_ms=200,
            fallback_used=False,
            status_code=200,
            source_count=2,
            query_len=20,
            dense_hits=3,
            bm25_hits=0,
            final_docs=2,
            llm_model="m",
        )
        RagRequestMetric.objects.create(
            request_id="r2",
            user=user,
            mode="rag_semantic",
            retrieval_ms=300,
            rerank_ms=20,
            llm_time_ms=500,
            fallback_used=True,
            status_code=500,
            source_count=1,
            query_len=12,
            dense_hits=2,
            bm25_hits=1,
            final_docs=1,
            llm_model="m",
        )
        RagRequestMetric.objects.create(
            request_id="bench-on-0-0",
            user=user,
            mode="rag_semantic",
            retrieval_ms=9999,
            rerank_ms=9999,
            llm_time_ms=9999,
            fallback_used=False,
            status_code=200,
            source_count=1,
            query_len=1,
            dense_hits=1,
            bm25_hits=1,
            final_docs=1,
            llm_model="m",
        )

        out = StringIO()
        call_command("rag_canary_report", minutes=120, limit=100, top_slow=2, stdout=out)
        text = out.getvalue()
        self.assertIn("RAG Canary Report", text)
        self.assertIn("Bench rows  : excluded", text)
        self.assertIn("By mode:", text)
        self.assertIn("By validation:", text)
        self.assertIn("Top 2 slow requests", text)
        self.assertIn("structured_transcript", text)
        self.assertIn("rag_semantic", text)
        self.assertNotIn("bench-on-0-0", text)
