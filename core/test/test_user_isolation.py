import unittest
from unittest.mock import patch

from core.ai_engine import retrieval


class TestUserIsolation(unittest.TestCase):
    """
    TestToggle: pastikan filter user_id selalu dipasang di retriever.
    UNIT TEST: tidak butuh Chroma real.
    """

    def test_retriever_filter_uses_correct_user_id(self):
        captured = {}

        class FakeVectorstore:
            def as_retriever(self, **kwargs):
                # tangkap kwargs (search_kwargs berisi k dan filter)
                captured["kwargs"] = kwargs
                return object()

        class DummyRAGChain:
            def invoke(self, payload):
                return {"answer": "dummy"}

        with patch.object(retrieval, "get_vectorstore", return_value=FakeVectorstore()), \
             patch.object(retrieval, "ChatOpenAI", return_value=object()), \
             patch.object(retrieval, "create_stuff_documents_chain", return_value=object()), \
             patch.object(retrieval, "create_retrieval_chain", return_value=DummyRAGChain()):

            user_a = 111
            retrieval.ask_bot(user_a, "query apa saja")

            self.assertIn("kwargs", captured)
            search_kwargs = captured["kwargs"]["search_kwargs"]

            # pastikan k = 20 (sesuai desain high recall kamu)
            self.assertEqual(search_kwargs["k"], 20)

            # POIN PENTING: filter harus tepat user_id
            self.assertEqual(search_kwargs["filter"], {"user_id": str(user_a)})

    def test_two_users_have_different_filters(self):
        captured_filters = []

        class FakeVectorstore:
            def as_retriever(self, **kwargs):
                captured_filters.append(kwargs["search_kwargs"]["filter"])
                return object()

        class DummyRAGChain:
            def invoke(self, payload):
                return {"answer": "dummy"}

        with patch.object(retrieval, "get_vectorstore", return_value=FakeVectorstore()), \
             patch.object(retrieval, "ChatOpenAI", return_value=object()), \
             patch.object(retrieval, "create_stuff_documents_chain", return_value=object()), \
             patch.object(retrieval, "create_retrieval_chain", return_value=DummyRAGChain()):

            retrieval.ask_bot(1, "tes")
            retrieval.ask_bot(2, "tes")

            self.assertEqual(captured_filters[0], {"user_id": "1"})
            self.assertEqual(captured_filters[1], {"user_id": "2"})
            self.assertNotEqual(captured_filters[0], captured_filters[1])
