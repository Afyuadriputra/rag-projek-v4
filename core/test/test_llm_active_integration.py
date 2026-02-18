import os
import unittest
from unittest.mock import patch

from langchain_core.documents import Document
from core.ai_engine import retrieval


@unittest.skipUnless(
    os.environ.get("RUN_LLM_TESTS") == "1",
    "Set RUN_LLM_TESTS=1 untuk menjalankan tes LLM (real network)"
)
class TestLLMActiveIntegration(unittest.TestCase):
    """
    Integration test: memanggil OpenRouter beneran via ask_bot(),
    tapi retrieval di-mock dengan retriever yang KOMPATIBEL runnable chain.
    """

    def test_ask_bot_real_llm_returns_text(self):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        self.assertTrue(api_key, "OPENROUTER_API_KEY belum diset di environment")

        class FakeRetriever:
            # LangChain runnable compatibility
            def with_config(self, **kwargs):
                return self

            def invoke(self, query, **kwargs):
                return [
                    Document(page_content="Semester 1: Matematika Diskrit - Nilai D"),
                    Document(page_content="Semester 2: Algoritma - Nilai B"),
                ]

        class FakeVectorstore:
            def as_retriever(self, **kwargs):
                return FakeRetriever()

        with patch.object(retrieval, "get_vectorstore", return_value=FakeVectorstore()):
            answer = retrieval.ask_bot(user_id=123, query="Sebutkan mata kuliah yang tidak lulus")

            self.assertIsInstance(answer, str)
            self.assertTrue(len(answer.strip()) > 0)

            # Pastikan BUKAN fallback error (kalau ini muncul berarti LLM chain gagal)
            self.assertNotIn("Maaf, semua server AI sedang sibuk", answer)
            self.assertNotIn("Error:", answer)
