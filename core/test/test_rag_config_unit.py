from unittest.mock import patch

from django.test import SimpleTestCase

from core.ai_engine import config as cfg


class RagConfigUnitTests(SimpleTestCase):
    def setUp(self):
        cfg._EMBEDDING_SINGLETON = None

    def tearDown(self):
        cfg._EMBEDDING_SINGLETON = None

    def test_preprocess_query_and_passage_for_e5(self):
        with patch.dict("os.environ", {"RAG_EMBEDDING_MODEL": "intfloat/multilingual-e5-large"}, clear=False):
            self.assertEqual(cfg.preprocess_embedding_query("jadwal senin"), "query: jadwal senin")
            self.assertEqual(cfg.preprocess_embedding_passage("isi dokumen"), "passage: isi dokumen")

    @patch("core.ai_engine.config._build_embedding")
    def test_embedding_fallback_to_legacy_when_primary_fails(self, build_mock):
        build_mock.side_effect = [RuntimeError("load fail"), "legacy-embedder"]
        with patch.dict("os.environ", {"RAG_EMBEDDING_MODEL": "intfloat/multilingual-e5-large"}, clear=False):
            emb = cfg.get_embedding_function()
        self.assertEqual(emb, "legacy-embedder")
        self.assertEqual(build_mock.call_count, 2)
