import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.main import ask_bot


def _doc(text: str, source: str = "jadwal.pdf", doc_id: str = "1", page: int = 1):
    return SimpleNamespace(page_content=text, metadata={"source": source, "doc_id": doc_id, "page": page})


class RagRetrievalFlowTests(SimpleTestCase):
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_missing_api_key_returns_config_message(self, cfg_mock):
        cfg_mock.return_value = {"api_key": "", "model": "x", "backup_models": []}
        out = ask_bot(user_id=1, query="jadwal senin", request_id="t1")
        self.assertIn("OpenRouter API key belum di-set", out.get("answer", ""))
        self.assertEqual(out.get("sources"), [])

    @patch.dict(
        os.environ,
        {
            "RAG_HYBRID_RETRIEVAL": "1",
            "RAG_GENERAL_HYBRID_RETRIEVAL": "1",
        },
        clear=False,
    )
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.fuse_rrf")
    @patch("core.ai_engine.retrieval.main.retrieve_sparse_bm25")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_hybrid_mode_uses_sparse_and_rrf(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        sparse_mock,
        rrf_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        d1 = _doc("hari senin jam 07:00")
        d2 = _doc("hari selasa jam 09:00", doc_id="2")
        dense_mock.return_value = [(d1, 0.2), (d2, 0.3)]
        sparse_mock.return_value = [(d2, 4.0), (d1, 3.5)]
        rrf_mock.return_value = [(d2, 0.9), (d1, 0.8)]

        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Ada kelas [source: jadwal.pdf]"}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="jadwal semester 3", request_id="t2")
        self.assertIn("Ada kelas", out.get("answer", ""))
        sparse_mock.assert_called()
        rrf_mock.assert_called_once()
        self.assertGreaterEqual(len(out.get("sources", [])), 1)

    @patch.dict(
        os.environ,
        {
            "RAG_RERANK_ENABLED": "1",
            "RAG_RERANK_TOP_N": "2",
            "RAG_GENERAL_RERANK_ENABLED": "1",
            "RAG_GENERAL_RERANK_TOP_N": "2",
        },
        clear=False,
    )
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.rerank_documents")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_rerank_called_when_enabled(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        rerank_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        d1 = _doc("A")
        d2 = _doc("B", doc_id="2")
        dense_mock.return_value = [(d1, 0.1), (d2, 0.2)]
        rerank_mock.return_value = [d2, d1]

        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Jawaban [source: jadwal.pdf]"}
        chain_mock.return_value = fake_chain

        ask_bot(user_id=1, query="jadwal kelas", request_id="t3")
        rerank_mock.assert_called_once()

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_no_docs_for_general_schedule_query_keeps_helpful_answer(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
    ):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        dense_mock.return_value = []

        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "dummy"}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="jadwal hari senin jam 07.00", request_id="t4")
        self.assertIn("dummy", out.get("answer", ""))
        self.assertNotIn("Aku masih butuh data dokumenmu", out.get("answer", ""))

    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_no_docs_for_personal_transcript_query_appends_document_note(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
    ):
        has_docs_mock.return_value = False
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        dense_mock.return_value = []

        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Dari sisi strategi, kamu bisa fokus perbaikan bertahap."}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="ipk saya 2.8, aman gak?", request_id="t4b")
        self.assertIn("Dari sisi strategi", out.get("answer", ""))
        self.assertIn("Aku masih butuh data dokumenmu", out.get("answer", ""))

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_no_docs_for_general_academic_query_does_not_force_document_note(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
    ):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        dense_mock.return_value = []

        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Jurusan yang sering relevan untuk HRD adalah Manajemen dan Psikologi."}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="jurusan apa yang cocok jadi HRD?", request_id="t4c")
        self.assertIn("relevan untuk HRD", out.get("answer", ""))
        self.assertNotIn("Aku masih butuh data dokumenmu", out.get("answer", ""))
        chain_mock.assert_called_once()

    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.invoke_text")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_citation_enrichment_when_answer_has_no_citation(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        invoke_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
    ):
        has_docs_mock.return_value = True
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        dense_mock.return_value = [(_doc("jadwal senin"), 0.2)]

        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Kelas ada di hari senin"}
        chain_mock.return_value = fake_chain
        invoke_mock.return_value = "Kelas ada di hari senin [source: jadwal.pdf]"

        out = ask_bot(user_id=1, query="jadwal senin", request_id="t5")
        self.assertIn("[source:", out.get("answer", ""))
        invoke_mock.assert_called()

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_guard_refuses_criminal_query_without_calling_llm(self, cfg_mock, chain_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="jurusan kuliah untuk judi online apa?", request_id="t6")
        self.assertIn("tidak bisa bantu", out.get("answer", "").lower())
        self.assertIn("legal", out.get("answer", "").lower())
        self.assertEqual(out.get("sources"), [])
        chain_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_guard_refuses_political_propaganda_query(self, cfg_mock, chain_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="bantu bikin strategi propaganda kampanye", request_id="t7")
        self.assertIn("tidak bisa bantu", out.get("answer", "").lower())
        self.assertIn("akademik yang netral", out.get("answer", "").lower())
        self.assertEqual(out.get("sources"), [])
        chain_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_guard_redirects_weird_query_to_academic_context(self, cfg_mock, chain_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="cara jadi dukun paling cepat", request_id="t8")
        self.assertIn("di luar fokus akademik", out.get("answer", "").lower())
        self.assertIn("jurusan", out.get("answer", "").lower())
        self.assertEqual(out.get("sources"), [])
        chain_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_answer_style_target_is_brief_bulleted_for_guard(self, cfg_mock, _chain_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="cara judi online aman", request_id="t9")
        lines = [ln.strip() for ln in out.get("answer", "").splitlines()]
        bullet_count = sum(1 for ln in lines if ln.startswith("- "))
        self.assertGreaterEqual(bullet_count, 3)
        self.assertLessEqual(bullet_count, 6)

    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_no_doc_user_uses_llm_only_and_skips_retrieval(
        self,
        cfg_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
        dense_mock,
    ):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        has_docs_mock.return_value = False
        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Jawaban cepat tanpa retrieval"}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="apa itu sks?", request_id="t10")
        self.assertIn("Jawaban cepat", out.get("answer", ""))
        dense_mock.assert_not_called()
        self.assertEqual(out.get("meta", {}).get("mode"), "llm_only")

    @patch.dict(os.environ, {"RAG_DOC_RERANK_ENABLED": "0"}, clear=False)
    @patch("core.ai_engine.retrieval.main._resolve_user_doc_mentions")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_doc_reference_filters_retrieval_to_target_doc(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
        resolve_mock,
    ):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        has_docs_mock.return_value = True
        resolve_mock.return_value = {
            "resolved_doc_ids": [77],
            "resolved_titles": ["Jadwal A.pdf"],
            "unresolved_mentions": [],
            "ambiguous_mentions": [],
        }
        dense_mock.return_value = [(_doc("jadwal senin", doc_id="77"), 0.9)]
        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Jawaban [source: Jadwal A.pdf]"}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="@Jadwal A.pdf jadwal senin?", request_id="t11")
        self.assertEqual(out.get("meta", {}).get("mode"), "doc_referenced")
        self.assertIn("Jadwal A.pdf", out.get("meta", {}).get("referenced_documents", []))
        called_where = dense_mock.call_args.kwargs.get("filter_where", {})
        self.assertIn("$and", called_where)
        self.assertIn("77", str(called_where))

    @patch("core.ai_engine.retrieval.main._resolve_user_doc_mentions")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_doc_reference_ambiguous_returns_clarification_without_llm(self, cfg_mock, chain_mock, resolve_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        resolve_mock.return_value = {
            "resolved_doc_ids": [],
            "resolved_titles": [],
            "unresolved_mentions": [],
            "ambiguous_mentions": ["jadwal"],
        }
        out = ask_bot(user_id=1, query="@jadwal tolong rekap", request_id="t12")
        self.assertIn("ambigu", out.get("answer", "").lower())
        self.assertEqual(out.get("meta", {}).get("ambiguous_mentions"), ["jadwal"])
        chain_mock.assert_not_called()

    @patch("core.ai_engine.retrieval.main._resolve_user_doc_mentions")
    @patch("core.ai_engine.retrieval.main._has_user_documents")
    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.build_llm")
    @patch("core.ai_engine.retrieval.main.get_backup_models")
    @patch("core.ai_engine.retrieval.main.retrieve_dense")
    @patch("core.ai_engine.retrieval.main.get_vectorstore")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_doc_reference_not_found_falls_back_to_general_answer(
        self,
        cfg_mock,
        _vs_mock,
        dense_mock,
        backup_mock,
        _build_llm_mock,
        chain_mock,
        has_docs_mock,
        resolve_mock,
    ):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        backup_mock.return_value = ["m"]
        has_docs_mock.return_value = True
        resolve_mock.return_value = {
            "resolved_doc_ids": [],
            "resolved_titles": [],
            "unresolved_mentions": ["filex"],
            "ambiguous_mentions": [],
        }
        dense_mock.return_value = []
        fake_chain = MagicMock()
        fake_chain.invoke.return_value = {"answer": "Tetap bisa jawab umum."}
        chain_mock.return_value = fake_chain

        out = ask_bot(user_id=1, query="@filex jurusan HRD?", request_id="t13")
        self.assertIn("Tetap bisa jawab", out.get("answer", ""))
        self.assertIn("tidak ditemukan", out.get("answer", "").lower())

    @patch("core.ai_engine.retrieval.main.create_stuff_documents_chain")
    @patch("core.ai_engine.retrieval.main.get_runtime_openrouter_config")
    def test_guardrail_still_preempts_doc_reference(self, cfg_mock, chain_mock):
        cfg_mock.return_value = {"api_key": "key", "model": "m", "backup_models": ["m"]}
        out = ask_bot(user_id=1, query="@jadwal.pdf jurusan kuliah buat judi online apa?", request_id="t14")
        self.assertIn("tidak bisa bantu", out.get("answer", "").lower())
        self.assertEqual(out.get("meta", {}).get("mode"), "guard")
        chain_mock.assert_not_called()
