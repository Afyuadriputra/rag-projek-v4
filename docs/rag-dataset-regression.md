# RAG Dataset Regression (Query-to-Source + 50 Prompt Akurasi)

Dokumen ini menjelaskan cara menjalankan regression test berbasis dataset akademik untuk memastikan jawaban RAG tetap grounded ke dokumen sumber.

## 1. Tujuan

Regression ini menambahkan dua kontrak test:
1. **Query-to-source mapping**: setiap query punya expected source allow-list.
2. **50 prompt akurasi**: campuran factual, evaluative, typo/ambiguous, no-evidence, out-of-domain.

Target utamanya:
- menjaga konsistensi `pipeline`, `intent_route`, `validation`,
- memastikan jawaban didukung `sources` yang relevan,
- mencegah drift kualitas saat refactor retrieval.

## 2. Lokasi Artefak

- `core/test/data/rag_query_source_mapping.yaml`
- `core/test/data/rag_accuracy_prompts_50.yaml`
- `core/test/data/rag_uploaded_docs_ground_truth.yaml`
- `core/test/data/rag_uploaded_docs_mapping.yaml`
- `core/test/data/rag_uploaded_docs_prompts_50.yaml`
- `core/test/data/rag_uploaded_docs_complex_ground_truth.yaml`
- `core/test/data/rag_uploaded_docs_complex_mapping.yaml`
- `core/test/data/rag_uploaded_docs_complex_prompts_80.yaml`
- `core/test/utils/rag_eval_loader.py`
- `core/test/test_rag_dataset_regression.py`
- `core/test/test_rag_uploaded_docs_regression.py`
- `core/test/fixtures/uploaded_docs/*.pdf`
- `core/test/test_rag_uploaded_docs_complex_regression.py`
- `core/test/fixtures/uploaded_docs_complex/*.pdf`
- `core/test/tools/generate_uploaded_docs_complex_fixtures.py`

## 3. Cara Menjalankan

### 3.1 Validasi schema/distribusi (selalu aman)

```bash
python manage.py test core.test.test_rag_dataset_regression.RagDatasetRegressionSchemaTests
```

### 3.2 Live regression terhadap runtime RAG

Set dulu env:

```bash
RAG_DATASET_REGRESSION_LIVE=1
```

Lalu jalankan:

```bash
python manage.py test core.test.test_rag_dataset_regression.RagDatasetRegressionLiveTests
```

Catatan live mode:
- butuh dokumen sudah di-ingest untuk `user_id=1`,
- butuh OpenRouter API key aktif,
- jika precondition belum siap, test akan di-`skip` (bukan fail).

### 3.3 Full file

```bash
python manage.py test core.test.test_rag_dataset_regression
```

### 3.4 Uploaded Docs Regression Pack (offline wajib)

Schema + evaluator contract:

```bash
python manage.py test core.test.test_rag_uploaded_docs_regression.RagUploadedDocsSchemaTests
python manage.py test core.test.test_rag_uploaded_docs_regression.RagUploadedDocsContractMockTests
```

### 3.5 Uploaded Docs Regression Pack (live opsional)

Set env:

```bash
RAG_UPLOADED_DOCS_REGRESSION_LIVE=1
RAG_TEST_USER_ID=1
```

Run:

```bash
python manage.py test core.test.test_rag_uploaded_docs_regression.RagUploadedDocsLiveTests
```

Precondition live mode:
- Fixture docs sudah di-ingest dan `is_embedded=True` untuk `user_id` test.
- API key OpenRouter aktif.
- Vector index user siap.

### 3.6 Uploaded Docs Complex Pack (200 rows x 8 pages, 5 jurusan)

Generate fixtures + YAML contracts (one-time):

```bash
python core/test/tools/generate_uploaded_docs_complex_fixtures.py
```

Offline tests:

```bash
python manage.py test core.test.test_rag_uploaded_docs_complex_regression.RagUploadedDocsComplexSchemaTests
python manage.py test core.test.test_rag_uploaded_docs_complex_regression.RagUploadedDocsComplexContractMockTests
```

Live tests:

```bash
RAG_UPLOADED_DOCS_COMPLEX_LIVE=1
RAG_TEST_USER_ID=1
python manage.py test core.test.test_rag_uploaded_docs_complex_regression.RagUploadedDocsComplexLiveTests
```

Precondition live complex:
- 6 file kompleks sudah di-ingest + embedded untuk user test:
  - `khs_ti_mahasiswa_c_200x8.pdf`
  - `khs_hukum_mahasiswa_d_200x8.pdf`
  - `khs_ekonomi_mahasiswa_e_200x8.pdf`
  - `khs_kedokteran_mahasiswa_f_200x8.pdf`
  - `khs_sastra_mahasiswa_g_200x8.pdf`
  - `rekap_lintas_jurusan_kompleks_2026.pdf`

## 4. Cara Membaca Failure

Format failure umumnya:
- `pipeline mismatch`: pipeline aktual tidak sesuai expected.
- `intent_route mismatch`: routing intent berubah.
- `validation mismatch`: status grounding tidak sesuai kontrak.
- `missing_source_evidence`: query grounded tapi `sources` kosong.
- `source mismatch`: source ada tapi tidak masuk allow-list.
- `answer missing required phrase(s)`: konten jawaban tidak memuat indikator minimal.
- `answer contains forbidden phrase(s)`: jawaban memuat teks terlarang.
- `tabular numeric mismatch`: angka penting tabel tidak sesuai ground truth.
- `semester coverage mismatch`: jawaban tidak mencakup semester yang diwajibkan kontrak.

## 5. Aturan Update Prompt/Mapping

## 5.1 Rule umum
- Jangan longgarkan evaluator global.
- Jika ada fail, update **expected allow-list/validation** pada item terkait setelah investigasi.
- Hindari single exact source; gunakan allow-list agar tidak flaky.

## 5.2 Menambah prompt baru
- Tambahkan item pada `rag_accuracy_prompts_50.yaml`.
- Wajib isi: `id`, `category`, `query`, `expected`.
- Pastikan `expected.allowed_sources_group` valid di `source_groups`.

## 5.3 Menjaga komposisi 50 prompt
Komposisi dikunci:
- factual_transcript: 18
- factual_krs: 10
- curriculum: 8
- evaluative: 5
- typo_ambiguous: 5
- no_evidence: 2
- out_of_domain: 2

Jika menambah satu kategori, kurangi kategori lain agar total tetap 50.

## 6. Rule Update Allow-List Source

Saat menambah/mengubah source:
1. Gunakan nama file basename (contoh: `semester 3.pdf`).
2. Simpan di `source_groups` jika dipakai berulang.
3. Hindari path absolut; evaluator menormalkan ke basename lower-case.
4. Untuk out-of-domain/guard, set `require_source_match: false`.

## 7. Integrasi Dengan Suite Existing

Regression ini tidak mengubah API publik `ask_bot`.
Gunakan ini sebagai lapisan tambahan setelah suite retrieval utama:
- `test_rag_structured_flow`
- `test_rag_retrieval_flow`
- `test_grounding_policy`
- `test_rag_regression_matrix`
- `test_rag_uploaded_docs_regression`
- `test_rag_uploaded_docs_complex_regression`
