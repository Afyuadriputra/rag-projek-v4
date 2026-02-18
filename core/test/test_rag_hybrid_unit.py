from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from core.ai_engine.retrieval.hybrid import fuse_rrf, retrieve_sparse_bm25
from core.ai_engine.retrieval.rerank import rerank_documents


def _doc(text: str, source: str = "doc.pdf", doc_id: str = "1", page: int = 1):
    return SimpleNamespace(page_content=text, metadata={"source": source, "doc_id": doc_id, "page": page})


class RagHybridUnitTests(SimpleTestCase):
    def test_rrf_fusion_dedup_and_order(self):
        a = _doc("jadwal senin 07:00", source="a.pdf", doc_id="10", page=1)
        b = _doc("jadwal selasa 08:00", source="b.pdf", doc_id="11", page=1)
        c = _doc("mata kuliah basis data", source="c.pdf", doc_id="12", page=2)

        dense = [(a, 0.10), (b, 0.20), (c, 0.30)]
        sparse = [(b, 5.0), (a, 4.0)]
        fused = fuse_rrf(dense_docs=dense, sparse_docs=sparse, k=3)
        self.assertEqual(len(fused), 3)
        top_doc = fused[0][0]
        self.assertIn(top_doc.metadata.get("doc_id"), {"10", "11"})

    def test_bm25_keyword_match(self):
        docs = [
            _doc("hari senin jam 07:00 ruang A101"),
            _doc("hari selasa jam 13:00 ruang B202"),
            _doc("transkrip nilai ipk"),
        ]
        ranked = retrieve_sparse_bm25("senin ruang", docs_pool=docs, k=2)
        self.assertEqual(len(ranked), 2)
        self.assertIn("senin", ranked[0][0].page_content.lower())

    @patch("core.ai_engine.retrieval.rerank._get_reranker", side_effect=RuntimeError("load failed"))
    def test_rerank_fallback_when_model_unavailable(self, _mock_get):
        docs = [_doc("A"), _doc("B"), _doc("C")]
        out = rerank_documents(query="jadwal", docs=docs, model_name="x", top_n=2)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].page_content, "A")
