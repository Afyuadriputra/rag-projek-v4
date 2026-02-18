import os
import unittest
from unittest.mock import patch

from core.ai_engine import retrieval


class TestLLMActiveUnit(unittest.TestCase):
    """
    Unit test: memastikan ask_bot membangun LLM + chain dan memanggil invoke(),
    tanpa memanggil OpenRouter beneran.
    """

    def test_ask_bot_calls_llm_chain(self):
        # Fake vectorstore dan retriever
        class FakeVectorstore:
            def as_retriever(self, **kwargs):
                return object()

        # Dummy rag chain yang mengembalikan jawaban
        class DummyRAGChain:
            def invoke(self, payload):
                return {"answer": "OK_FROM_UNIT_TEST"}

        # Patch environment key (biar constructor dapat value)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "DUMMY_KEY"}), \
             patch.object(retrieval, "get_vectorstore", return_value=FakeVectorstore()), \
             patch.object(retrieval, "ChatOpenAI", return_value=object()) as mock_chatopenai, \
             patch.object(retrieval, "create_stuff_documents_chain", return_value=object()) as mock_stuff, \
             patch.object(retrieval, "create_retrieval_chain", return_value=DummyRAGChain()) as mock_retrieval_chain:

            ans = retrieval.ask_bot(user_id=1, query="Tes")

            self.assertEqual(ans, "OK_FROM_UNIT_TEST")

            # Pastikan LLM dicoba dibuat
            self.assertGreaterEqual(mock_chatopenai.call_count, 1)

            # Pastikan chain dirakit
            self.assertGreaterEqual(mock_stuff.call_count, 1)
            self.assertGreaterEqual(mock_retrieval_chain.call_count, 1)

            # Pastikan ChatOpenAI dikonfig dengan base OpenRouter
            kwargs = mock_chatopenai.call_args.kwargs
            self.assertEqual(kwargs["openai_api_base"], "https://openrouter.ai/api/v1")
            self.assertIn("openai_api_key", kwargs)
