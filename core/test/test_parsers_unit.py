import unittest

from core.ai_engine.parsers import classifier
from core.ai_engine.parsers import normalize
from core.ai_engine.parsers import schedule_jadwal_fakultas


class TestParsersClassifier(unittest.TestCase):
    def test_classifier_jadwal_fakultas(self):
        pages = ["HARI SESI JAM RUANG SMT KLS DOSEN"]
        doc_type, conf, signals = classifier.classify(pages)
        self.assertEqual(doc_type, "jadwal_fakultas")
        self.assertGreaterEqual(conf, 0.6)
        self.assertTrue("hari" in signals)

    def test_classifier_krs(self):
        pages = ["Lembar Rencana Studi\nNIM: 123456\nProgram Studi: Informatika\nSemester: 7"]
        doc_type, conf, signals = classifier.classify(pages)
        self.assertEqual(doc_type, "krs")
        self.assertGreaterEqual(conf, 0.5)
        self.assertTrue("krs" in signals or "lembar rencana studi" in signals)


class TestParsersNormalize(unittest.TestCase):
    def test_time_normalization(self):
        self.assertEqual(normalize.normalize_time_range("07.00-07.50"), "07:00-07:50")
        self.assertEqual(normalize.normalize_time_range("7:00–9:30"), "07:00-09:30")

    def test_merge_header_smt(self):
        merged = normalize.merge_split_headers(["SM", "T", "KLS"])
        self.assertEqual(merged[0], "SMT")


class TestMergedCellPropagation(unittest.TestCase):
    def test_propagate_hari_sesi_jam(self):
        rows = [
            {"hari": "SENIN", "sesi": "I", "jam": "07:00-07:50"},
            {"hari": None, "sesi": None, "jam": None},
        ]
        schedule_jadwal_fakultas._propagate_merged_fields(rows)
        self.assertEqual(rows[1]["hari"], "SENIN")
        self.assertEqual(rows[1]["sesi"], "I")
        self.assertEqual(rows[1]["jam"], "07:00-07:50")
