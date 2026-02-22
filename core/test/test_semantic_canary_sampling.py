from django.test import SimpleTestCase

from core.ai_engine.retrieval.application.semantic_service import _use_optimized_for_request


class SemanticCanarySamplingTests(SimpleTestCase):
    def test_sampling_zero_and_full(self):
        self.assertFalse(
            _use_optimized_for_request(user_id=1, request_id="r1", query="apa itu sks", traffic_pct=0)
        )
        self.assertTrue(
            _use_optimized_for_request(user_id=1, request_id="r1", query="apa itu sks", traffic_pct=100)
        )

    def test_sampling_deterministic_for_same_seed(self):
        out1 = _use_optimized_for_request(user_id=7, request_id="rid-123", query="jadwal", traffic_pct=50)
        out2 = _use_optimized_for_request(user_id=7, request_id="rid-123", query="jadwal", traffic_pct=50)
        self.assertEqual(out1, out2)

