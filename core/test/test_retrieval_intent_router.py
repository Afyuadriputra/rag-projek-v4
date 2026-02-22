from django.test import SimpleTestCase

from core.ai_engine.retrieval.intent_router import route_intent


class IntentRouterUnitTests(SimpleTestCase):
    def test_route_analytical_tabular(self):
        out = route_intent("tolong rekap nilai rendah saya")
        self.assertEqual(out.get("route"), "analytical_tabular")

    def test_route_semantic_policy(self):
        out = route_intent("apa syarat lulus dan aturan cuti")
        self.assertEqual(out.get("route"), "semantic_policy")

    def test_route_out_of_domain(self):
        out = route_intent("resep ayam kecap yang enak")
        self.assertEqual(out.get("route"), "out_of_domain")

    def test_route_default(self):
        out = route_intent("jurusan apa yang cocok untuk HRD")
        self.assertEqual(out.get("route"), "default_rag")
