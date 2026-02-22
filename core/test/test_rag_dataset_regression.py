from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from core.ai_engine.retrieval.main import ask_bot
from core.models import AcademicDocument
from core.test.utils.rag_eval_loader import (
    RagEvalAssertionError,
    evaluate_rag_output,
    load_accuracy_prompts,
    load_query_source_mapping,
)


class RagDatasetRegressionSchemaTests(SimpleTestCase):
    def test_accuracy_prompts_50_distribution_guard(self):
        data = load_accuracy_prompts()
        prompts = list(data.get("prompts") or [])
        self.assertEqual(len(prompts), 50, "Prompt count must be exactly 50")

        got = Counter(str(x.get("category") or "") for x in prompts)
        expected = {
            "factual_transcript": 18,
            "factual_krs": 10,
            "curriculum": 8,
            "evaluative": 5,
            "typo_ambiguous": 5,
            "no_evidence": 2,
            "out_of_domain": 2,
        }
        self.assertEqual(dict(got), expected)

    def test_yaml_contracts_loadable(self):
        mapping = load_query_source_mapping()
        prompts = load_accuracy_prompts()

        self.assertEqual(int(mapping.get("version") or 0), 1)
        self.assertEqual(int(prompts.get("version") or 0), 1)

        self.assertTrue(mapping.get("source_groups"))
        self.assertTrue(mapping.get("queries"))
        self.assertTrue(prompts.get("source_groups"))
        self.assertTrue(prompts.get("prompts"))


class RagDatasetRegressionLiveTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.live_enabled = str(os.environ.get("RAG_DATASET_REGRESSION_LIVE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _skip_if_not_ready(self):
        if not self.live_enabled:
            self.skipTest("Set RAG_DATASET_REGRESSION_LIVE=1 to run live dataset regression")

        dataset_root = Path("dataset")
        if not dataset_root.exists():
            self.skipTest("dataset/ not found")

        if not AcademicDocument.objects.filter(user_id=1, is_embedded=True).exists():
            self.skipTest("No embedded AcademicDocument for user_id=1; ingest docs first")

        smoke = ask_bot(user_id=1, query="halo", request_id="dataset-reg-smoke")
        msg = str(smoke.get("answer") or "").lower()
        if "api key belum" in msg:
            self.skipTest("OpenRouter API key not configured")

    def test_query_source_mapping_contract(self):
        self._skip_if_not_ready()
        data = load_query_source_mapping()
        source_groups = dict(data.get("source_groups") or {})
        queries = list(data.get("queries") or [])

        self.assertGreaterEqual(len(queries), 20)
        self.assertLessEqual(len(queries), 25)

        failures = []
        for item in queries:
            qid = str(item.get("id") or "-")
            query = str(item.get("query") or "").strip()
            with self.subTest(qid=qid, query=query):
                out = ask_bot(user_id=1, query=query, request_id=f"dataset-map-{qid}")
                expected = {
                    "expected_pipeline": item.get("expected_pipeline"),
                    "expected_intent_route": item.get("expected_intent_route"),
                    "expected_validation_in": item.get("expected_validation_in") or [],
                    "allowed_sources": item.get("allowed_sources") or [],
                    "source_match_mode": item.get("source_match_mode") or "any_of",
                    "require_source_match": bool((item.get("allowed_sources") or []) != []),
                    "must_contain_any": item.get("must_contain_any") or [],
                    "must_not_contain": item.get("must_not_contain") or [],
                }
                try:
                    evaluate_rag_output(out, expected, source_groups=source_groups)
                except RagEvalAssertionError as exc:
                    failures.append(f"{qid}: {exc}")

        if failures:
            self.fail("\n".join(failures))

    def test_accuracy_prompts_50_regression(self):
        self._skip_if_not_ready()
        data = load_accuracy_prompts()
        source_groups = dict(data.get("source_groups") or {})
        prompts = list(data.get("prompts") or [])

        failures = []
        for item in prompts:
            pid = str(item.get("id") or "-")
            category = str(item.get("category") or "-")
            query = str(item.get("query") or "").strip()
            expected = dict(item.get("expected") or {})

            with self.subTest(pid=pid, category=category):
                out = ask_bot(user_id=1, query=query, request_id=f"dataset-acc-{pid}")
                try:
                    evaluate_rag_output(out, expected, source_groups=source_groups)
                except RagEvalAssertionError as exc:
                    failures.append(f"{pid} [{category}]: {exc}")

        if failures:
            self.fail("\n".join(failures))
