import unittest
from unittest.mock import patch

# Import module retrieval (bukan hanya function) supaya gampang patch variabelnya
from core.ai_engine import retrieval


class TestLLMFallbackModel(unittest.TestCase):
    """
    Test: paksa model pertama gagal, pastikan model kedua dipakai dan berhasil.
    Ini UNIT TEST: tidak butuh internet, tidak butuh OpenRouter, tidak butuh Chroma.
    """

    def test_fallback_to_backup_model_when_primary_fails(self):
        # Pakai list model kecil agar deterministik
        test_models = ["model_utama_gagal", "model_backup_sukses"]

        # Dummy Chain yang punya invoke() dan mengembalikan jawaban
        class DummyRAGChain:
            def invoke(self, payload):
                return {"answer": "OK_DARI_BACKUP"}

        # Fake vectorstore dan retriever (tidak dipakai banyak karena chain kita dummy)
        class FakeVectorstore:
            def as_retriever(self, **kwargs):
                return object()

        # ChatOpenAI palsu: error kalau model pertama, sukses kalau model kedua
        def fake_chatopenai_constructor(*args, **kwargs):
            model_name = kwargs.get("model_name")
            if model_name == "model_utama_gagal":
                raise Exception("Simulasi error: model utama down")
            return object()  # LLM dummy

        with patch.object(retrieval, "BACKUP_MODELS", test_models), \
             patch.object(retrieval, "get_vectorstore", return_value=FakeVectorstore()), \
             patch.object(retrieval, "ChatOpenAI", side_effect=fake_chatopenai_constructor) as mocked_llm, \
             patch.object(retrieval, "create_stuff_documents_chain", return_value=object()), \
             patch.object(retrieval, "create_retrieval_chain", return_value=DummyRAGChain()), \
             patch.object(retrieval.time, "sleep", return_value=None):

            answer = retrieval.ask_bot(user_id=1, query="Tes fallback")

            # Pastikan jawabannya dari backup (artinya fallback terjadi)
            self.assertEqual(answer, "OK_DARI_BACKUP")

            # Pastikan ChatOpenAI dipanggil >= 2 kali (utama gagal, backup sukses)
            self.assertGreaterEqual(mocked_llm.call_count, 2)

            # Pastikan urutan model yang dicoba benar
            first_call_model = mocked_llm.call_args_list[0].kwargs.get("model_name")
            second_call_model = mocked_llm.call_args_list[1].kwargs.get("model_name")

            self.assertEqual(first_call_model, "model_utama_gagal")
            self.assertEqual(second_call_model, "model_backup_sukses")
