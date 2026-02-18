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

    @patch.dict(os.environ, {"RAG_HYBRID_RETRIEVAL": "1"}, clear=False)
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
    ):
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

    @patch.dict(os.environ, {"RAG_RERANK_ENABLED": "1", "RAG_RERANK_TOP_N": "2"}, clear=False)
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
    ):
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
    def test_no_docs_for_schedule_returns_low_evidence_message(
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
        self.assertIn("belum cukup", out.get("answer", "").lower())

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
    ):
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
