# Backend–Frontend Integration (Academic RAG)

Dokumen ini merangkum cara kerja backend di `config/` dan `core/`, serta endpoint yang dipakai frontend untuk berkomunikasi dengan sistem.

## 1. Arsitektur Singkat

Stack utama:
- Django sebagai backend web + auth.
- Inertia.js (`inertia`) untuk render halaman React dari Django.
- Vite (`django_vite`) untuk asset React.
- ChromaDB + LangChain untuk RAG (ingest dokumen + retrieval).

Alur besar sistem:
1. User login/register via Django auth.
2. User upload dokumen ke `/api/upload/`.
3. Backend parsing + chunking + embedding ke ChromaDB (dengan metadata `user_id`).
4. User chat ke `/api/chat/`.
5. Backend retrieve konteks berdasarkan `user_id`, lalu generate jawaban via LLM.
6. History chat dan daftar dokumen dikirim ke frontend via Inertia props dan API JSON.

Referensi kode utama:
- Routing global: `academic_rag_project/config/urls.py`
- Settings: `academic_rag_project/config/settings.py`
- Routing app: `academic_rag_project/core/urls.py`
- Views + API: `academic_rag_project/core/views.py`
- Models: `academic_rag_project/core/models.py`
- Ingest: `academic_rag_project/core/ai_engine/ingest.py`
- Retrieval: `academic_rag_project/core/ai_engine/retrieval.py`
- Vectorstore config: `academic_rag_project/core/ai_engine/config.py`

---

## 2. Routing & Entry Points

### 2.1 Root URLConf

`config/urls.py`:
- `admin/` → Django admin.
- `""` (root) → semua route dari `core.urls`.

### 2.2 App URLConf

`core/urls.py` mendefinisikan route berikut:

Halaman (Inertia):
- `GET /` → `chat_view` (butuh login).
- `GET /register/` → `register_view`.
- `GET /login/` → `login_view`.
- `GET /logout/` → `logout_view`.

API JSON (dipanggil frontend):
- `POST /api/upload/` → upload dokumen (batch).
- `POST /api/chat/` → kirim pesan chat.
- `GET /api/documents/` → refresh daftar dokumen + storage.
- `DELETE /api/documents/<id>/` → hapus dokumen + embeddings.
- `GET /api/sessions/` → list chat session.
- `POST /api/sessions/` → buat chat session baru.
- `GET /api/sessions/<id>/` → ambil history chat session.
- `PATCH /api/sessions/<id>/` → rename chat session.
- `DELETE /api/sessions/<id>/` → hapus chat session.

Semua endpoint API dibungkus `@login_required` dan `@csrf_exempt` di `core/views.py`.

---

## 3. Auth & Session Model

Backend menggunakan Django session-based auth:
- Login dilakukan di `login_view`.
- Register dilakukan di `register_view`.
- Session cookie akan dipakai otomatis oleh browser saat memanggil `/api/*`.

Implikasi untuk frontend:
- Frontend tidak perlu menyimpan token JWT.
- Pastikan request `fetch`/`axios` mengirim cookie session.
- Karena API bersifat same-origin, biasanya cookie otomatis terkirim.

Setting terkait auth di `config/settings.py`:
- `LOGIN_URL = 'login'`
- `LOGIN_REDIRECT_URL = 'home'`
- `LOGOUT_REDIRECT_URL = 'login'`

---

## 4. Kontrak Data (Models)

### 4.1 AcademicDocument

File: `core/models.py`

Field penting:
- `user` → pemilik dokumen.
- `title` → judul dokumen (auto-fill dari nama file jika kosong).
- `file` → file upload (`media/documents/%Y/%m/`).
- `uploaded_at` → timestamp upload.
- `is_embedded` → status ingest ke vectorstore.

### 4.2 ChatSession

File: `core/models.py`

Field penting:
- `user`
- `title` (default: "Chat Baru")
- `created_at`
- `updated_at`

Session dipakai untuk memisahkan history chat per topik.

### 4.3 ChatHistory

File: `core/models.py`

Field penting:
- `user`
- `session` (FK ke ChatSession)
- `question`
- `answer`
- `timestamp`

Catatan: `Meta.ordering = ['-timestamp']`, tapi di view history disortir ulang ascending untuk ditampilkan kronologis.

---

## 5. Inertia Props ke Frontend

### 5.1 Halaman utama `/`

View: `chat_view` di `core/views.py`.

Inertia component yang dirender:
- `"Chat/Index"`

Props yang dikirim ke React:

```json
{
  "user": { "id": 1, "username": "...", "email": "..." },
  "activeSessionId": 10,
  "sessions": [
    {
      "id": 10,
      "title": "Chat Baru",
      "created_at": "2026-01-27 13:10",
      "updated_at": "2026-01-27 13:12"
    }
  ],
  "initialHistory": [
    {
      "question": "...",
      "answer": "...",
      "time": "14:32",
      "date": "2026-01-27"
    }
  ],
  "documents": [
    {
      "id": 1,
      "title": "KHS_Semester_1.pdf",
      "is_embedded": true,
      "uploaded_at": "2026-01-27 13:20",
      "size_bytes": 123456
    }
  ],
  "storage": {
    "used_bytes": 123456,
    "quota_bytes": 104857600,
    "used_pct": 12,
    "used_human": "120.56 KB",
    "quota_human": "100.00 MB"
  }
}
```

Asal data:
- `initialHistory` dari `ChatHistory`.
- `documents` + `storage` dari helper `_serialize_documents_for_user` dan `_build_storage_payload`.
- Quota storage saat ini hard-coded: **100 MB**.

---

## 6. API yang Dipakai Frontend

Semua endpoint ada di `core/views.py`.

### 6.1 Chat API

Endpoint:
- `POST /api/chat/`

Request body (JSON):

```json
{
  "message": "Tolong rekap nilai yang tidak lulus",
  "session_id": 10
}
```

Response sukses:

```json
{
  "answer": "...jawaban AI...",
  "session_id": 10
}
```

Response error umum:
- `400` jika JSON invalid atau `message` kosong.
- `500` jika proses AI crash.

Perilaku backend:
1. Ambil `message`.
2. Panggil `ask_bot(user.id, message)` (RAG).
3. Simpan ke `ChatHistory` sesuai `session_id`.
4. Kembalikan `answer`.

### 6.2 Upload API (Batch)

Endpoint:
- `POST /api/upload/`

Content-Type:
- `multipart/form-data`

Field yang diharapkan:
- `files` (bisa multiple).

Contoh (frontend conceptual):

```ts
const form = new FormData();
for (const f of files) form.append("files", f);
await fetch("/api/upload/", { method: "POST", body: form });
```

Response sukses:

```json
{
  "status": "success",
  "msg": "Berhasil memproses 2 file."
}
```

Response gagal total:

```json
{
  "status": "error",
  "msg": "Gagal semua. Detail: file1.pdf (Gagal Parsing), file2.csv (System Error)"
}
```

Perilaku backend per file:
1. Simpan `AcademicDocument`.
2. Panggil `process_document(doc)`.
3. Jika ingest sukses → `is_embedded = true`.
4. Jika ingest gagal → dokumen dihapus dari DB.

### 6.3 Documents API (Refresh Sidebar)

Endpoint:
- `GET /api/documents/`

Response:

```json
{
  "documents": [
    {
      "id": 1,
      "title": "KRS_Semester_2.pdf",
      "is_embedded": true,
      "uploaded_at": "2026-01-27 13:20",
      "size_bytes": 123456
    }
  ],
  "storage": {
    "used_bytes": 123456,
    "quota_bytes": 104857600,
    "used_pct": 12,
    "used_human": "120.56 KB",
    "quota_human": "100.00 MB"
  }
}
```

Tujuan endpoint ini:
- Dipanggil frontend setelah upload selesai agar sidebar sinkron.

Hapus dokumen:
- `DELETE /api/documents/<id>/` → `{ status: "success" }`
- Efek: file dihapus dari storage + embeddings di vector DB dihapus.

### 6.4 Sessions API (Chat Baru + List + Delete)

Endpoint:
- `GET /api/sessions/`
- `POST /api/sessions/`

Query params list:
- `page` (default 1)
- `page_size` (default 20)

Contoh response list:

```json
{
  "sessions": [
    {
      "id": 10,
      "title": "Chat Baru",
      "created_at": "2026-01-27 13:10",
      "updated_at": "2026-01-27 13:12"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 42,
    "has_next": true
  }
}
```

Create session (opsional title):

```json
{
  "title": "Semester Genap"
}
```

Response:

```json
{
  "session": {
    "id": 11,
    "title": "Semester Genap",
    "created_at": "2026-01-27 13:15",
    "updated_at": "2026-01-27 13:15"
  }
}
```

History per session:
- `GET /api/sessions/<id>/` → `{ history: [...] }`

Rename:
- `PATCH /api/sessions/<id>/` body `{ "title": "Judul Baru" }` → `{ session: { ... } }`

Delete:
- `DELETE /api/sessions/<id>/` → `{ status: "success" }`
---

## 7. Mesin RAG (Ingest & Retrieval)

### 7.1 Vectorstore & Embedding

File: `core/ai_engine/config.py`

Poin penting:
- Persist directory: `BASE_DIR/chroma_db`
- Embedding model: `all-MiniLM-L6-v2` (HuggingFace)
- Collection name: `academic_rag`

### 7.2 Ingest Dokumen

File: `core/ai_engine/ingest.py`

`process_document(doc_instance)` melakukan:
1. Deteksi ekstensi file.
2. Parsing teks:
   - PDF: `pdfplumber` (termasuk tabel + teks).
   - Excel/CSV: `pandas` lalu `to_markdown`.
   - MD/TXT: baca langsung.
3. Chunking:
   - `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)`
4. Simpan ke ChromaDB:
   - `vectorstore.add_texts(...)`
   - Metadata wajib: `{"user_id": str(user.id), "source": doc.title}`

Metadata `user_id` ini krusial untuk isolasi data per user saat retrieval.

### 7.3 Retrieval + Generation

File: `core/ai_engine/retrieval.py`

`ask_bot(user_id, query)` melakukan:
1. Ambil vectorstore.
2. Retriever dengan filter user:
   - `filter: {"user_id": str(user_id)}`
   - `k = 20` (high recall).
3. Prompt akademik khusus rekap nilai.
4. LLM via OpenRouter memakai `ChatOpenAI`.
5. Fallback model berurutan sampai sukses.

Output akhirnya adalah string `answer`.

---

## 8. Environment Variables yang Dibutuhkan

Dari perilaku kode, minimal yang perlu disiapkan:

- `SECRET_KEY` (disarankan di `.env`).
- `DEBUG` (`True` / `False`).
- `OPENROUTER_API_KEY` (wajib untuk chat AI).
- `OPENROUTER_MODEL` (opsional, default ada di `BACKUP_MODELS[0]`).

Catatan penting:
- Karena backend mengarah ke `https://openrouter.ai/api/v1`, chat AI akan gagal tanpa `OPENROUTER_API_KEY` yang valid.

---

## 9. Checklist Integrasi Frontend

Jika kamu ingin memastikan frontend “nyambung” dengan backend ini, yang penting adalah:

1. Session auth berjalan:
   - Login via `/login/`.
   - Setelah login, akses `/` harus sukses.

2. Chat berjalan:
   - `POST /api/chat/` dengan body JSON `{ "message": "..." }`.
   - Ekspektasi response `{ "answer": "..." }`.

3. Upload berjalan:
   - `POST /api/upload/` dengan `FormData` key `files`.
   - Setelah sukses, panggil `GET /api/documents/` untuk refresh.

4. UI initial state:
   - Halaman `/` menerima props: `user`, `initialHistory`, `documents`, `storage`.

---

## 10. Ringkasan Endpoint (Cepat)

- Halaman:
  - `GET /` → Inertia `Chat/Index` (login required)
  - `GET /login/` → Inertia `Auth/Login`
  - `GET /register/` → Inertia `Auth/Register`
  - `GET /logout/` → logout + redirect

- API:
  - `POST /api/chat/` → `{ message, session_id }` → `{ answer, session_id }`
  - `POST /api/upload/` → multipart `files[]` → status + msg
  - `GET /api/documents/` → `{ documents, storage }`
  - `GET /api/sessions/` → list session (pagination)
  - `POST /api/sessions/` → create session
  - `GET /api/sessions/<id>/` → history
  - `PATCH /api/sessions/<id>/` → rename
  - `DELETE /api/sessions/<id>/` → delete

---

Kalau kamu mau, aku bisa lanjutkan dengan:
- menurunkan ini jadi kontrak TypeScript (`types.ts`) yang match persis dengan backend, dan/atau
- cek langsung kecocokan dengan komponen frontend kamu (`ChatBubble.tsx`, `ChatComposer.tsx`, dsb).
