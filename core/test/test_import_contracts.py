import inspect

from django.test import SimpleTestCase

import core.ai_engine.retrieval.infrastructure.metrics as metrics


class ImportContractsTests(SimpleTestCase):
    def test_metrics_uses_absolute_core_monitoring_import(self):
        src = inspect.getsource(metrics)
        self.assertIn("from core.monitoring import record_rag_metric", src)

    def test_emit_rag_metric_exists(self):
        self.assertTrue(callable(metrics.emit_rag_metric))
