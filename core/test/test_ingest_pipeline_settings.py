import os
from unittest import TestCase

from core.ai_engine.ingest_pipeline import settings


class IngestPipelineSettingsTests(TestCase):
    def test_env_bool_int_float_defaults(self):
        self.assertTrue(settings.env_bool("__INGEST_TEST_BOOL__", default=True))
        self.assertEqual(settings.env_int("__INGEST_TEST_INT__", 7), 7)
        self.assertEqual(settings.env_float("__INGEST_TEST_FLOAT__", 1.5), 1.5)

    def test_env_cast_with_values(self):
        os.environ["__INGEST_TEST_BOOL__"] = "yes"
        os.environ["__INGEST_TEST_INT__"] = "13"
        os.environ["__INGEST_TEST_FLOAT__"] = "2.75"
        try:
            self.assertTrue(settings.env_bool("__INGEST_TEST_BOOL__"))
            self.assertEqual(settings.env_int("__INGEST_TEST_INT__", 0), 13)
            self.assertAlmostEqual(settings.env_float("__INGEST_TEST_FLOAT__", 0.0), 2.75)
        finally:
            os.environ.pop("__INGEST_TEST_BOOL__", None)
            os.environ.pop("__INGEST_TEST_INT__", None)
            os.environ.pop("__INGEST_TEST_FLOAT__", None)

