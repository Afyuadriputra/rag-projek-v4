from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.test import SimpleTestCase, TestCase
from pypdf import PdfReader

from core.ai_engine.retrieval.main import ask_bot
from core.models import AcademicDocument
from core.test.utils.rag_eval_loader import (
    RagEvalAssertionError,
    assert_semester_coverage,
    assert_tabular_consistency,
    evaluate_uploaded_docs_complex_output,
    load_uploaded_docs_complex_ground_truth,
    load_uploaded_docs_complex_mapping,
    load_uploaded_docs_complex_prompts,
)


class RagUploadedDocsComplexSchemaTests(SimpleTestCase):
    def test_complex_prompts_distribution_guard_80(self):
        data = load_uploaded_docs_complex_prompts()
        prompts = list(data.get("prompts") or [])
        self.assertEqual(len(prompts), 80, "Prompt count must be exactly 80")

        got = Counter(str(x.get("category") or "") for x in prompts)
        expected = {
            "factual_transcript": 25,
            "factual_schedule_or_semester": 15,
            "cross_major_comparison": 12,
            "evaluative_grounded": 10,
            "typo_ambiguous_multilingual": 8,
            "partial_evidence": 4,
            "no_evidence": 3,
            "out_of_domain": 3,
        }
        self.assertEqual(dict(got), expected)

    def test_complex_yaml_contracts_loadable(self):
        mapping = load_uploaded_docs_complex_mapping()
        prompts = load_uploaded_docs_complex_prompts()
        gt = load_uploaded_docs_complex_ground_truth()

        self.assertEqual(int(mapping.get("version") or 0), 1)
        self.assertEqual(int(prompts.get("version") or 0), 1)
        self.assertEqual(int(gt.get("version") or 0), 1)

        self.assertTrue(mapping.get("source_groups"))
        self.assertTrue(mapping.get("queries"))
        self.assertTrue(prompts.get("source_groups"))
        self.assertTrue(prompts.get("prompts"))
        self.assertTrue(gt.get("facts"))

    def test_complex_ground_truth_references_covered(self):
        mapping = load_uploaded_docs_complex_mapping()
        prompts = load_uploaded_docs_complex_prompts()
        gt = load_uploaded_docs_complex_ground_truth()
        facts = dict(gt.get("facts") or {})

        def _resolve_path(ref: str) -> bool:
            group, key = ref.split(".", 1)
            node: Any = facts.get(group)
            if node is None:
                return False
            for part in key.split("."):
                if not isinstance(node, dict) or part not in node:
                    return False
                node = node[part]
            return True

        refs: List[str] = []
        for item in list(mapping.get("queries") or []):
            refs.extend([r for r in list(item.get("expected_numbers") or []) if isinstance(r, str) and "." in r])
        for item in list(prompts.get("prompts") or []):
            expected = dict(item.get("expected") or {})
            refs.extend([r for r in list(expected.get("expected_numbers") or []) if isinstance(r, str) and "." in r])

        self.assertTrue(refs, "No expected_numbers references found")
        missing = [r for r in refs if not _resolve_path(r)]
        self.assertEqual(missing, [], f"Missing ground truth references: {missing}")

    def test_fixture_inventory_complete(self):
        root = Path("core/test/fixtures/uploaded_docs_complex")
        expected_files = [
            "khs_ti_mahasiswa_c_200x8.pdf",
            "khs_hukum_mahasiswa_d_200x8.pdf",
            "khs_ekonomi_mahasiswa_e_200x8.pdf",
            "khs_kedokteran_mahasiswa_f_200x8.pdf",
            "khs_sastra_mahasiswa_g_200x8.pdf",
            "rekap_lintas_jurusan_kompleks_2026.pdf",
        ]
        for name in expected_files:
            path = root / name
            self.assertTrue(path.exists(), f"Missing fixture: {name}")

        for name in expected_files[:5]:
            reader = PdfReader(str(root / name))
            self.assertEqual(len(reader.pages), 8, f"Expected 8 pages in {name}")
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            row_hits = sum(1 for line in text.splitlines() if line.strip().startswith("ROW "))
            self.assertGreaterEqual(row_hits, 200, f"Expected >=200 rows in {name}, got {row_hits}")


class RagUploadedDocsComplexContractMockTests(SimpleTestCase):
    def test_complex_evaluator_source_route_validation_contract(self):
        gt = load_uploaded_docs_complex_ground_truth()
        out = {
            "answer": "Berdasarkan dokumen, jurusan TI total SKS 601 dan IPK 2.45.",
            "sources": [{"source": "khs_ti_mahasiswa_c_200x8.pdf"}],
            "meta": {
                "pipeline": "structured_analytics",
                "intent_route": "analytical_tabular",
                "validation": "passed",
            },
        }
        expected = {
            "pipeline_in": ["structured_analytics", "rag_semantic"],
            "intent_route_in": ["analytical_tabular", "default_rag"],
            "validation_in": ["passed", "skipped_strict"],
            "allowed_sources": ["khs_ti_mahasiswa_c_200x8.pdf"],
            "require_source_match": True,
            "source_match_mode": "any_of",
            "must_contain_any": ["dokumen", "sks", "ipk"],
            "must_not_contain": ["resep"],
            "expected_numbers": ["ti_rekap.total_sks", "ti_rekap.ipk"],
        }
        evaluate_uploaded_docs_complex_output(out, expected, source_groups={}, ground_truth=gt)

    def test_complex_evaluator_numeric_semester_contract(self):
        gt = load_uploaded_docs_complex_ground_truth()
        answer = "Semester 3 memiliki SKS 86 dan jumlah matkul 29 untuk jurusan TI."
        assert_tabular_consistency(
            answer=answer,
            expected_numbers=["ti_rekap.semester_stats.semester_3.sks", "ti_rekap.semester_stats.semester_3.matkul"],
            ground_truth=gt,
            tolerance_policy={"rel_tol": 0.02, "abs_tol": 0.05},
        )
        assert_semester_coverage(answer, [3])

    def test_complex_evaluator_no_evidence_contract(self):
        out = {
            "answer": "Berdasarkan dokumen, data nomor ijazah tidak tersedia.",
            "sources": [],
            "meta": {
                "pipeline": "rag_semantic",
                "intent_route": "default_rag",
                "validation": "no_grounding_evidence",
            },
        }
        expected = {
            "pipeline_in": ["structured_analytics", "rag_semantic"],
            "intent_route_in": ["analytical_tabular", "default_rag"],
            "validation_in": ["no_grounding_evidence"],
            "require_source_match": False,
            "must_contain_any": ["dokumen", "tidak", "tersedia"],
            "must_not_contain": [],
        }
        evaluate_uploaded_docs_complex_output(out, expected, source_groups={}, ground_truth={})


class RagUploadedDocsComplexLiveTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.live_enabled = str(os.environ.get("RAG_UPLOADED_DOCS_COMPLEX_LIVE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        cls.user_id = int(str(os.environ.get("RAG_TEST_USER_ID", "1")).strip() or 1)

    def _skip_if_not_ready(self):
        if not self.live_enabled:
            self.skipTest("Set RAG_UPLOADED_DOCS_COMPLEX_LIVE=1 to run uploaded-docs complex live regression")

        fixture_root = Path("core/test/fixtures/uploaded_docs_complex")
        if not fixture_root.exists():
            self.skipTest("Fixture folder core/test/fixtures/uploaded_docs_complex not found")

        required_titles = {
            "khs_ti_mahasiswa_c_200x8.pdf",
            "khs_hukum_mahasiswa_d_200x8.pdf",
            "khs_ekonomi_mahasiswa_e_200x8.pdf",
            "khs_kedokteran_mahasiswa_f_200x8.pdf",
            "khs_sastra_mahasiswa_g_200x8.pdf",
            "rekap_lintas_jurusan_kompleks_2026.pdf",
        }
        have_titles = set(
            AcademicDocument.objects.filter(user_id=self.user_id, is_embedded=True).values_list("title", flat=True)
        )
        if not required_titles.issubset(have_titles):
            self.skipTest(
                "Complex fixture docs not embedded for user_id="
                f"{self.user_id}. Required: {sorted(required_titles)}"
            )

        smoke = ask_bot(user_id=self.user_id, query="halo", request_id="uploaded-cx-smoke")
        msg = str(smoke.get("answer") or "").lower()
        if "api key belum" in msg:
            self.skipTest("OpenRouter API key not configured")

    def test_complex_query_source_mapping_contract(self):
        self._skip_if_not_ready()
        data = load_uploaded_docs_complex_mapping()
        source_groups = dict(data.get("source_groups") or {})
        ground_truth = load_uploaded_docs_complex_ground_truth()
        queries = list(data.get("queries") or [])

        self.assertGreaterEqual(len(queries), 40)

        failures: List[str] = []
        for item in queries:
            qid = str(item.get("id") or "-")
            query = str(item.get("query") or "").strip()
            with self.subTest(qid=qid, query=query):
                out = ask_bot(user_id=self.user_id, query=query, request_id=f"uploaded-cx-map-{qid}")
                expected = {
                    "pipeline_in": item.get("pipeline_in") or [],
                    "intent_route_in": item.get("intent_route_in") or [],
                    "validation_in": item.get("expected_validation_in") or item.get("validation_in") or [],
                    "allowed_sources": item.get("allowed_sources") or [],
                    "allowed_sources_group": item.get("allowed_sources_group"),
                    "source_match_mode": item.get("source_match_mode") or "any_of",
                    "require_source_match": bool(item.get("require_source_match", True)),
                    "must_contain_any": item.get("must_contain_any") or [],
                    "must_not_contain": item.get("must_not_contain") or [],
                    "expected_numbers": item.get("expected_numbers") or [],
                    "expected_semesters": item.get("expected_semesters") or [],
                }
                try:
                    evaluate_uploaded_docs_complex_output(
                        out,
                        expected,
                        source_groups=source_groups,
                        ground_truth=ground_truth,
                    )
                except RagEvalAssertionError as exc:
                    failures.append(f"{qid}: {exc}")

        if failures:
            self.fail("\n".join(failures))

    def test_complex_prompts_80_regression(self):
        self._skip_if_not_ready()
        data = load_uploaded_docs_complex_prompts()
        source_groups = dict(data.get("source_groups") or {})
        ground_truth = load_uploaded_docs_complex_ground_truth()
        prompts = list(data.get("prompts") or [])

        failures: List[str] = []
        for item in prompts:
            pid = str(item.get("id") or "-")
            category = str(item.get("category") or "-")
            query = str(item.get("query") or "").strip()
            expected = dict(item.get("expected") or {})

            with self.subTest(pid=pid, category=category):
                out = ask_bot(user_id=self.user_id, query=query, request_id=f"uploaded-cx-acc-{pid}")
                try:
                    evaluate_uploaded_docs_complex_output(
                        out,
                        expected,
                        source_groups=source_groups,
                        ground_truth=ground_truth,
                    )
                except RagEvalAssertionError as exc:
                    failures.append(f"{pid} [{category}]: {exc}")

        if failures:
            self.fail("\n".join(failures))
