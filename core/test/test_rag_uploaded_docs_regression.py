from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.test import SimpleTestCase, TestCase

from core.ai_engine.retrieval.main import ask_bot
from core.models import AcademicDocument
from core.test.utils.rag_eval_loader import (
    RagEvalAssertionError,
    assert_numeric_consistency,
    evaluate_uploaded_docs_output,
    load_uploaded_docs_ground_truth,
    load_uploaded_docs_mapping,
    load_uploaded_docs_prompts,
)


class RagUploadedDocsSchemaTests(SimpleTestCase):
    def test_uploaded_prompts_distribution_guard(self):
        data = load_uploaded_docs_prompts()
        prompts = list(data.get("prompts") or [])
        self.assertEqual(len(prompts), 50, "Prompt count must be exactly 50")

        got = Counter(str(x.get("category") or "") for x in prompts)
        expected = {
            "factual_transcript": 18,
            "factual_schedule_or_krs": 10,
            "cross_major_curriculum": 8,
            "evaluative_grounded": 5,
            "typo_ambiguous": 5,
            "no_evidence": 2,
            "out_of_domain": 2,
        }
        self.assertEqual(dict(got), expected)

    def test_uploaded_yaml_contracts_loadable(self):
        mapping = load_uploaded_docs_mapping()
        prompts = load_uploaded_docs_prompts()
        gt = load_uploaded_docs_ground_truth()

        self.assertEqual(int(mapping.get("version") or 0), 1)
        self.assertEqual(int(prompts.get("version") or 0), 1)
        self.assertEqual(int(gt.get("version") or 0), 1)

        self.assertTrue(mapping.get("source_groups"))
        self.assertTrue(mapping.get("queries"))
        self.assertTrue(prompts.get("source_groups"))
        self.assertTrue(prompts.get("prompts"))
        self.assertTrue(gt.get("facts"))

    def test_ground_truth_keys_covered(self):
        mapping = load_uploaded_docs_mapping()
        prompts = load_uploaded_docs_prompts()
        gt = load_uploaded_docs_ground_truth()
        facts = dict(gt.get("facts") or {})

        def _iter_expected_numbers(items: Iterable[Dict[str, Any]]) -> Iterable[str]:
            for item in items:
                expected = item if "expected_numbers" in item else dict(item.get("expected") or {})
                for ref in list(expected.get("expected_numbers") or []):
                    if isinstance(ref, str) and "." in ref:
                        yield ref

        refs = list(_iter_expected_numbers(mapping.get("queries") or []))
        refs.extend(list(_iter_expected_numbers(prompts.get("prompts") or [])))
        self.assertTrue(refs, "No expected_numbers references found")

        missing = []
        for ref in refs:
            group, key = ref.split(".", 1)
            node = facts.get(group)
            if not isinstance(node, dict) or key not in node:
                missing.append(ref)

        self.assertEqual(missing, [], f"Missing ground truth references: {missing}")


class RagUploadedDocsContractMockTests(SimpleTestCase):
    def test_evaluator_source_and_text_contract(self):
        gt = load_uploaded_docs_ground_truth()
        out = {
            "answer": "Total SKS 144 dan IPK 3.42. Hasil studi menunjukkan nilai baik.",
            "sources": [{"source": "khs_ti_mahasiswa_a.pdf"}],
            "meta": {
                "pipeline": "structured_analytics",
                "intent_route": "analytical_tabular",
                "validation": "passed",
            },
        }
        expected = {
            "pipeline_in": ["structured_analytics", "rag_semantic"],
            "intent_route_in": ["analytical_tabular", "default_rag"],
            "validation_in": ["passed"],
            "allowed_sources": ["khs_ti_mahasiswa_a.pdf"],
            "require_source_match": True,
            "source_match_mode": "any_of",
            "must_contain_any": ["sks", "ipk"],
            "must_not_contain": ["resep"],
            "expected_numbers": ["ti_rekap.total_sks", "ti_rekap.ipk"],
        }
        evaluate_uploaded_docs_output(out, expected, source_groups={}, ground_truth=gt)

    def test_evaluator_numeric_consistency_contract(self):
        gt = load_uploaded_docs_ground_truth()
        answer = "Perbandingan: TI 144 SKS, Hukum 146 SKS, IPK 3.42 vs 3.18."
        assert_numeric_consistency(
            answer=answer,
            expected_numbers=[
                "lintas_jurusan_2025.ti_total_sks",
                "lintas_jurusan_2025.hukum_total_sks",
                "lintas_jurusan_2025.ti_ipk",
                "lintas_jurusan_2025.hukum_ipk",
            ],
            ground_truth=gt,
        )


class RagUploadedDocsLiveTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.live_enabled = str(os.environ.get("RAG_UPLOADED_DOCS_REGRESSION_LIVE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        cls.user_id = int(str(os.environ.get("RAG_TEST_USER_ID", "1")).strip() or 1)

    def _skip_if_not_ready(self):
        if not self.live_enabled:
            self.skipTest("Set RAG_UPLOADED_DOCS_REGRESSION_LIVE=1 to run uploaded-docs live regression")

        fixture_root = Path("core/test/fixtures/uploaded_docs")
        if not fixture_root.exists():
            self.skipTest("Fixture folder core/test/fixtures/uploaded_docs not found")

        required_titles = {
            "khs_ti_mahasiswa_a.pdf",
            "khs_hukum_mahasiswa_b.pdf",
            "rekap_lintas_jurusan_2025.pdf",
        }
        have_titles = set(
            AcademicDocument.objects.filter(user_id=self.user_id, is_embedded=True).values_list("title", flat=True)
        )
        if not required_titles.issubset(have_titles):
            self.skipTest(
                "Fixture docs not embedded for user_id="
                f"{self.user_id}. Required: {sorted(required_titles)}"
            )

        smoke = ask_bot(user_id=self.user_id, query="halo", request_id="uploaded-reg-smoke")
        msg = str(smoke.get("answer") or "").lower()
        if "api key belum" in msg:
            self.skipTest("OpenRouter API key not configured")

    def test_uploaded_query_source_mapping_contract(self):
        self._skip_if_not_ready()
        data = load_uploaded_docs_mapping()
        source_groups = dict(data.get("source_groups") or {})
        ground_truth = load_uploaded_docs_ground_truth()
        queries = list(data.get("queries") or [])

        self.assertGreaterEqual(len(queries), 20)

        failures: List[str] = []
        for item in queries:
            qid = str(item.get("id") or "-")
            query = str(item.get("query") or "").strip()
            with self.subTest(qid=qid, query=query):
                out = ask_bot(user_id=self.user_id, query=query, request_id=f"uploaded-map-{qid}")
                expected = {
                    "pipeline_in": item.get("pipeline_in") or ([item.get("expected_pipeline")] if item.get("expected_pipeline") else []),
                    "intent_route_in": item.get("intent_route_in") or ([item.get("expected_intent_route")] if item.get("expected_intent_route") else []),
                    "validation_in": item.get("expected_validation_in") or item.get("validation_in") or [],
                    "allowed_sources": item.get("allowed_sources") or [],
                    "allowed_sources_group": item.get("allowed_sources_group"),
                    "source_match_mode": item.get("source_match_mode") or "any_of",
                    "require_source_match": bool(item.get("require_source_match", True)),
                    "must_contain_any": item.get("must_contain_any") or [],
                    "must_not_contain": item.get("must_not_contain") or [],
                    "expected_numbers": item.get("expected_numbers") or [],
                }
                try:
                    evaluate_uploaded_docs_output(
                        out,
                        expected,
                        source_groups=source_groups,
                        ground_truth=ground_truth,
                    )
                except RagEvalAssertionError as exc:
                    failures.append(f"{qid}: {exc}")

        if failures:
            self.fail("\n".join(failures))

    def test_uploaded_prompts_50_regression(self):
        self._skip_if_not_ready()
        data = load_uploaded_docs_prompts()
        source_groups = dict(data.get("source_groups") or {})
        ground_truth = load_uploaded_docs_ground_truth()
        prompts = list(data.get("prompts") or [])

        failures: List[str] = []
        for item in prompts:
            pid = str(item.get("id") or "-")
            category = str(item.get("category") or "-")
            query = str(item.get("query") or "").strip()
            expected = dict(item.get("expected") or {})
            with self.subTest(pid=pid, category=category):
                out = ask_bot(user_id=self.user_id, query=query, request_id=f"uploaded-acc-{pid}")
                try:
                    evaluate_uploaded_docs_output(
                        out,
                        expected,
                        source_groups=source_groups,
                        ground_truth=ground_truth,
                    )
                except RagEvalAssertionError as exc:
                    failures.append(f"{pid} [{category}]: {exc}")

        if failures:
            self.fail("\n".join(failures))
