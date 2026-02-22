from django.test import SimpleTestCase

from core.ai_engine.retrieval.domain.policies import (
    is_strict_transcript_mode,
    needs_doc_grounding,
    should_abstain_no_grounding,
    structured_polish_validation_status,
)


class GroundingPolicyTests(SimpleTestCase):
    def test_needs_doc_grounding(self):
        self.assertTrue(needs_doc_grounding("transcript"))
        self.assertTrue(needs_doc_grounding("schedule"))
        self.assertFalse(needs_doc_grounding("general"))

    def test_should_abstain_no_grounding(self):
        self.assertTrue(should_abstain_no_grounding(docs_count=0, doc_type="transcript", is_personal_query=True))
        self.assertFalse(should_abstain_no_grounding(docs_count=1, doc_type="transcript", is_personal_query=True))
        self.assertFalse(should_abstain_no_grounding(docs_count=0, doc_type="general", is_personal_query=True))

    def test_strict_transcript_mode(self):
        markers = ["khs", "transkrip"]
        self.assertTrue(is_strict_transcript_mode("rekap khs saya", markers))
        self.assertFalse(is_strict_transcript_mode("bagaimana progres saya", markers))

    def test_structured_polish_validation_status(self):
        self.assertEqual(structured_polish_validation_status({"validation": "passed"}), "passed")
        self.assertEqual(structured_polish_validation_status({}), "failed_fallback")
        self.assertEqual(structured_polish_validation_status(None), "failed_fallback")
