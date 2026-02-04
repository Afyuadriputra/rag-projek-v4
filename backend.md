Gambaran Umum
Project ini adalah Django app dengan Inertia.js + Vite untuk frontend, dan RAG pipeline (Chroma + LangChain) untuk QA dokumen akademik. Entry point routing ada di urls.py lalu semuanya diarahkan ke urls.py.

Konfigurasi Proyek (config/)

settings.py
App aktif: core, rest_framework, inertia, django_vite.
DB: SQLite (db.sqlite3).
Static + Vite: core/static, dist di core/static/dist.
Media upload: media/.
Auth redirect: LOGIN_URL = login, LOGIN_REDIRECT_URL = home.
Logging: format berwarna + request_id + akses log per request.
urls.py
'' include core.urls, admin/ standar.
MEDIA_URL di-serve jika DEBUG.
logging_filters.py
Menjamin setiap log punya request_id.
Middleware Request ID + Access Log

middleware.py
Set request.request_id dan log 1 baris akses per request.
Ini menghidupkan format log di settings.py.
Model Utama (core/models.py)

AcademicDocument
Simpan file upload user, auto title dari nama file.
is_embedded menandai status ingest ke Chroma.
ChatHistory
Simpan Q/A per user, default sorting terbaru dulu.
Routing (core/urls.py)

Page utama: / → chat_view.
Auth: /register/, /login/, /logout/.
API:
POST /api/upload/
POST /api/chat/
GET /api/documents/
POST /api/reingest/
Service Layer (core/service.py)
File ini jadi pusat business logic (views hanya orchestration).

get_dashboard_props(...)
Ambil profile, history, dokumen, storage → dipakai page chat.
get_documents_payload(...)
Return list dokumen + storage info.
upload_files_batch(...)
Save AcademicDocument → process_document(...) → set is_embedded.
Jika gagal parsing: record dihapus (DB tetap bersih).
chat_and_save(...)
ask_bot(...) → simpan history → return answer + sources.
reingest_documents_for_user(...)
Delete embedding lama → ingest ulang.
Views (core/views.py)

Auth (register_view, login_view, logout_view)
Register + login langsung (Inertia response).
Validasi error basic, log audit.
chat_view
Login required.
Ambil props dari service, render Inertia Chat/Index.
documents_api
GET only, return list dokumen + storage.
upload_api
POST only, ambil files → service.
chat_api
POST only, JSON {message} → service.
reingest_api
POST only, optional doc_ids.
AI Engine (core/ai_engine/)

config.py
Embedding model: all-MiniLM-L6-v2.
Vectorstore: Chroma di chroma_db/, collection academic_rag.
ingest.py
Parse PDF/Excel/CSV/MD/TXT.
PDF: ekstrak tabel + schedule rows + text halaman.
Buat chunk 1000 char, overlap 120.
Simpan ke Chroma + metadata: user_id, doc_id, source, file_type, columns, schedule_rows.
retrieval.py
Guardrail: smalltalk, non‑academic query ditolak halus.
Ambil doc dari Chroma per user_id.
Detect kolom yang boleh ditampilkan (anti-halu).
Jika pertanyaan jadwal → data‑first (tanpa LLM).
Jika pertanyaan nilai tapi kolom grade tidak ada → jawab “data nilai tidak ditemukan”.
LLM via OpenRouter (model fallback).
Kontrak output wajib: 5 heading + tabel Markdown valid.
vector_ops.py
Delete embeddings per dokumen / per user (best effort).
Alur Request Penting

Upload dokumen
POST /api/upload/ → upload_files_batch
Save file → parse + chunk → embed → Chroma
is_embedded true jika sukses.
Chat RAG
POST /api/chat/ → chat_and_save
ask_bot → retrieval docs → jawab → simpan history.
Dashboard
GET / → chat_view
Gabungkan user profile + history + dokumen + quota.
Catatan Teknis

rest_framework terpasang tapi API masih pakai JsonResponse.
OPENROUTER_API_KEY wajib untuk LLM.
Quota statis 100MB (QUOTA_BYTES di views.py).
ChatHistory ordering default terbaru dulu di model, tapi service.get_dashboard_props sengaja urut ascending untuk timeline.
