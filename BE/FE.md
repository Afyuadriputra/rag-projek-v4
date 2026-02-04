deskripsi arsitektur lengkap sistem chatbot RAG rekomendasi KRS untuk laporan. Saya susun ringkas namun tetap teknis.

Gambaran Umum Sistem
Sistem terdiri dari tiga lapisan utama:

Frontend (React + Inertia + Vite) untuk interaksi pengguna, upload dokumen, dan chat.
Backend (Django) sebagai pengelola autentikasi, API, dan orkestrasi RAG.
AI Engine (RAG Pipeline) untuk ingest dokumen, embedding, penyimpanan vector, retrieval, dan generasi jawaban.
Arsitektur Lapisan

Presentation Layer (Frontend)

Lokasi: frontend/
Framework: React + Inertia.js
Fungsi utama:
Form login/register.
Upload dokumen akademik.
Chat antarmuka tanya jawab.
Sidebar daftar dokumen + status ingest.
Komponen utama:
Index.tsx sebagai halaman chat.
api.ts untuk komunikasi API backend.
Application Layer (Backend Django)

Lokasi: core/, config/
Fungsi utama:
Autentikasi user (login/register/logout).
API dokumen (/api/upload/, /api/documents/).
API chat (/api/chat/).
Re-ingest dokumen (/api/reingest/).
Struktur kunci:
views.py: endpoint utama.
service.py: business logic (orchestration).
models.py: penyimpanan dokumen & chat history.
settings.py: konfigurasi Django, logging, static, media.
middleware.py: request_id + access log.
Knowledge Layer (RAG Pipeline)

Lokasi: core/ai_engine/
Fungsi utama:
Ingest: parsing PDF/Excel/CSV/TXT → chunking → embedding.
Storage: ChromaDB lokal (chroma_db/).
Retrieval: cari konteks berdasarkan query.
LLM Response: jawaban berbasis konteks.
Modul penting:
ingest.py: ekstraksi tabel jadwal/KRS + metadata.
retrieval.py: query → retrieve → LLM → output markdown terstruktur.
config.py: embedding & vector store config.
vector_ops.py: hapus embedding per dokumen.
Alur Kerja Utama (End-to-End)

Registrasi/Login

User login melalui frontend.
Backend views.py memproses dan membuat session.
Upload Dokumen

Frontend memanggil POST /api/upload/.
Backend menyimpan file ke media/ + create AcademicDocument.
process_document() melakukan parsing, chunking, embedding, simpan ke Chroma.
Chat RAG

Frontend kirim pertanyaan ke POST /api/chat/.
Backend ask_bot():
Ambil embedding dokumen terkait user.
Retrieval context dari Chroma.
LLM menghasilkan jawaban + sumber.
Jawaban dan history disimpan ke DB.
Rekap Dokumen

Frontend memanggil GET /api/documents/.
Backend mengembalikan list dokumen + info kuota.
Desain Data Utama

AcademicDocument: file upload, judul, status embed, user pemilik.
ChatHistory: tanya jawab user, timestamp.
Metadata di vector store:
user_id, doc_id, source, file_type.
columns (schema dokumen).
schedule_rows (jadwal hasil ekstraksi).
Teknologi & Integrasi

Frontend: React, TailwindCSS, Inertia.js, Axios.
Backend: Django 6, SQLite, REST API.
RAG: LangChain + ChromaDB.
Embedding: all-MiniLM-L6-v2.
LLM: OpenRouter (model fallback + timeout).
Keunggulan Arsitektur

Isolasi data per user melalui metadata user_id di vector store.
Data-first answering untuk jadwal (lebih akurat, tidak halu).
Guardrail output: format jawaban harus konsisten.
Logging terstruktur (request_id + access log).