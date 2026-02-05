# Dokumentasi Backend — Academic RAG System

Dokumen ini menjelaskan cara kerja backend pada folder `core/` dan `config/` secara jelas dan detail. Backend menggunakan Django + Inertia, serta AI Engine (RAG) untuk memproses dokumen akademik dan menjawab pertanyaan user.

## 1) Arsitektur Singkat

**Lapisan utama:**
- **Web Backend (Django)**: autentikasi, routing, API, session, log, storage file.
- **AI Engine (RAG)**: ingest dokumen → chunking → embedding → vector DB (Chroma) → LLM.
- **Vector DB (Chroma)**: menyimpan embedding per user sebagai knowledge base.

**Alur besar:**
1. User login/register di Django.
2. User upload dokumen (PDF/Excel/CSV/TXT/MD).
3. Backend ingest dokumen → simpan ke Chroma dengan metadata.
4. User chat → backend ambil context dari Chroma → LLM jawab.

---

## 2) Struktur Folder Backend

```
config/
  settings.py
  urls.py
  wsgi.py
  asgi.py
  logging_filters.py

core/
  models.py
  views.py
  urls.py
  service.py
  middleware.py
  admin.py
  ai_engine/
    config.py
    ingest.py
    retrieval/
      main.py
      llm.py
      prompt.py
      rules.py
      utils.py
    vector_ops.py
```

---

## 3) Konfigurasi Utama (config/)

### 3.1 `config/settings.py`
- Mengatur **INSTALLED_APPS** (`core`, `rest_framework`, `inertia`, `django_vite`).
- Konfigurasi **database** (SQLite).
- Konfigurasi **static/media**.
- **Logging**: sudah disesuaikan agar rapi untuk terminal kecil, memakai `|` sebagai separator.
- **Audit log**: aktivitas penting dicatat ke `logs/audit.log` (rotating harian).
- **Middleware**: termasuk `core.middleware.RequestContextMiddleware` untuk request_id + access log.
- **Security**: rate‑limit login via `django-axes`, CSRF aktif untuk auth form.

### 3.2 `config/urls.py`
- Root URL mengarah ke `core.urls`.
- `admin/` untuk Django admin.
- `MEDIA_URL` diserve saat `DEBUG`.

### 3.3 `config/logging_filters.py`
- Filter `RequestIdFilter` menambahkan field:
  - `request_id`, `user`, `ip`, `method`, `path`, `status`, `duration_ms`, `agent`, `referer`.
- Dipakai agar formatter log tidak error.
- Warna status code lebih kontras:
  - 2xx: bright green, 4xx: bright yellow, 5xx: bright red.

### 3.4 Logging Audit (Rotating File)
- File audit harian disimpan di: `logs/audit.log`.
- Rotasi setiap tengah malam, retensi 14 hari.
- Format audit ringkas: `time|level|rid|user|ip|message`.

---

## 4) Models (core/models.py)

### 4.1 `AcademicDocument`
- Menyimpan file user (`media/documents/%Y/%m/`).
- Field penting: `user`, `title`, `file`, `uploaded_at`, `is_embedded`.

### 4.2 `ChatSession`
- Menyimpan sesi chat (per topik).
- Field: `user`, `title`, `created_at`, `updated_at`.

### 4.3 `ChatHistory`
- Menyimpan Q/A per sesi.
- Field: `user`, `session`, `question`, `answer`, `timestamp`.

### 4.4 `UserQuota`
- Menyimpan kuota upload per user.
- Field: `user`, `quota_bytes` (default 10MB), `updated_at`.

---

## 5) Middleware & Logging

### 5.1 `core/middleware.py`
- Membuat `request_id` unik.
- Menambahkan **audit metadata** ke request (`request.audit`):
  - `request_id`, `user`, `user_id`, `ip`, `agent`, `referer`, `method`, `path`.
- Mencatat access log dalam format ringkas:
  - method, path, status, durasi, user, ip, user-agent, referer.

### 5.2 Logging Formatter
- Format tanpa padding (tanpa spasi ekstra), tetap pakai `|`.
- Log dibaca dengan **double‑spaced** (ada baris kosong di antara log).
- Field yang selalu muncul:
  - level | time | logger | rid | method | path | status | duration | user | ip | ua | referer | file:line | message

### 5.3 Audit Logger (CCTV)
- **Logger:** `audit` (console + file).
- **Aksi penting yang dicatat:**
  - `register`, `login` (success/fail/locked/error), `logout`
  - `upload` (success/error/payload too large/empty)
  - `doc_delete`
  - `session_create`, `session_rename`, `session_delete`
  - `reingest`
  - `quota_create`, `quota_update` (admin)

---

## 6) Routing & Endpoint (core/urls.py)

**Halaman Inertia:**
- `/` → `chat_view`
- `/login/`, `/register/`, `/logout/`

**API utama:**
- `POST /api/chat/` → tanya LLM
- `POST /api/upload/` → upload dokumen
- `GET /api/documents/` → list dokumen + storage
- `DELETE /api/documents/<id>/` → hapus dokumen + embeddings
- `POST /api/reingest/` → ingest ulang dokumen (opsional `doc_ids`)

**Chat sessions:**
- `GET /api/sessions/` → list sessions
- `POST /api/sessions/` → buat session
- `GET /api/sessions/<id>/` → history session
- `PATCH /api/sessions/<id>/` → rename session
- `DELETE /api/sessions/<id>/` → hapus session

---

## 7) Service Layer (core/service.py)

Service berfungsi sebagai **logic layer** supaya `views.py` tetap bersih.

Fungsi penting:
- `get_dashboard_props()` → data awal Inertia (user, history, docs, storage, sessions)
- `upload_files_batch()` → simpan file + ingest + validasi kuota
- `chat_and_save()` → panggil LLM + simpan history
- `reingest_documents_for_user()` → delete embedding lama + ingest ulang
- `delete_document_for_user()` → hapus file + embeddings
- `get_user_quota_bytes()` → kuota upload dari DB (`UserQuota`)

---

## 8) AI Engine (core/ai_engine)

### 8.1 `config.py`
- Embedding: `all-MiniLM-L6-v2` (HuggingFace)
- Vectorstore: Chroma (persist di `chroma_db/`)

### 8.2 `ingest.py`
- Membaca file PDF/Excel/CSV/TXT/MD.
- Multi-strategy parsing + fallback OCR.
- Normalisasi kolom header agar konsisten.
- Simpan metadata:
  - `user_id`, `doc_id`, `source`, `file_type`
  - `columns` (JSON string)
  - `schedule_rows` (JSON string)
  - `semester` (jika terdeteksi)
  - `doc_type` (`schedule` / `transcript` / `general`)

### 8.3 `vector_ops.py`
- `delete_vectors_for_doc()` → hapus embeddings dokumen.
- `purge_vectors_for_user()` → hapus semua embeddings user.

### 8.4 `retrieval/` (LLM‑first)
- `main.py`: orchestration `ask_bot()`
- `llm.py`: setup OpenRouter LLM
- `prompt.py`: template prompt
- `rules.py`: infer doc type
- `utils.py`: build sources + helper UI

**LLM‑first logic:**
- Selalu panggil LLM.
- Jika context ada → gunakan.
- Jika context kosong → LLM jawab secara umum.

**Prompt guardrail:**
- Instruksi di dalam dokumen **tidak boleh** mengubah aturan sistem.

---

## 9) Kuota Upload

- Default kuota: **10MB** per user.
- Admin dapat mengubah di **Django Admin → UserQuota**.
- Upload ditolak jika melewati kuota.
- UI menampilkan storage dari API.
- Perubahan kuota dicatat di audit log:
  - `action=quota_create` / `action=quota_update`.

---

## 10) Flow Utama (End‑to‑End)

### 10.1 Upload Dokumen
1. Frontend kirim file ke `POST /api/upload/`.
2. Backend simpan file → ingest → embeddings ke Chroma.
3. `is_embedded` diperbarui.
4. Audit log: `action=upload`.

### 10.2 Chat
1. Frontend kirim pertanyaan ke `POST /api/chat/`.
2. Backend retrieval context dari Chroma.
3. LLM jawab (LLM‑first, context tambahan bila ada).
4. History disimpan ke DB.

### 10.3 Hapus Dokumen
1. Frontend panggil `DELETE /api/documents/<id>/`.
2. Backend hapus file + embeddings + record DB.
3. Audit log: `action=doc_delete`.

---

## 11) Debug & Troubleshooting

- **OCR tidak bekerja:** pastikan `pytesseract`, `pdf2image`, dan `tesseract.exe` terpasang & masuk PATH.
- **Chroma filter error:** pastikan filter memakai `$and` jika ada lebih dari satu key.
- **Vector kosong:** lakukan `POST /api/reingest/`.
- **Audit log kosong:** pastikan folder `logs/` ada dan permission write.

---

## 12) Catatan Penting

- Sistem menggunakan OpenRouter API Key (wajib).
- Semua log dicatat rapi di terminal kecil untuk monitoring.
- `retrieval.py` sudah dipisah menjadi modul agar lebih mudah maintenance.
- Audit log di file `logs/audit.log` untuk review aktivitas.

---

## 13) Ringkasan Singkat

Backend ini adalah sistem RAG berbasis Django, dengan alur:
- Upload dokumen → ingest → embeddings → Chroma.
- Chat → LLM‑first, menggunakan context jika ada.
- Semua aktivitas tercatat di terminal dengan format rapi + audit file harian.

Jika ingin, dokumentasi ini bisa diperluas menjadi diagram arsitektur atau flowchart.
