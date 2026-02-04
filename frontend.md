cara kerja frontend di frontend/src (struktur, alur data, dan komponen utama). Aku fokus ke arsitektur + flow yang dipakai saat login, chat, upload, dan sidebar.

Arsitektur & Bootstrap

Entry point di main.tsx.
Inisialisasi Inertia via createInertiaApp, resolve halaman dari frontend/src/pages/**.
Konfigurasi global Axios untuk CSRF Django (X-CSRFToken + csrftoken).
Import global styles index.css dan glass.css.
Frontend memakai Inertia.js sebagai bridge ke Django, jadi halaman React di-resolve berdasarkan name yang dikirim backend (mis. Chat/Index, Auth/Login, Auth/Register).
Layer API

api.ts
Axios instance baseURL /api.
Fungsi utama:
sendChat(message, sessionId) → POST /api/chat/ → {answer, sources, session_id}.
uploadDocuments(files) → POST /api/upload/ (multipart).
getDocuments() → GET /api/documents/.
deleteDocument(id) → DELETE /api/documents/<id>/.
getSessions() → GET /api/sessions/.
createSession(title?) → POST /api/sessions/.
deleteSession(id) → DELETE /api/sessions/<id>/.
getSessionHistory(id) → GET /api/sessions/<id>/.
renameSession(id, title) → PATCH /api/sessions/<id>/.
Tipe data kuat untuk response dan DocumentDto.
Halaman Utama (Chat)

Index.tsx
Props diterima dari backend (Inertia) sebagai initial state:
user, initialHistory, documents, storage, sessions, activeSessionId.
State utama:
documents, storage, sessions, activeSession, items (chat thread), loading, dark, mobileMenuOpen, toast.
Alur penting:
On load: initialHistory diubah jadi ChatItem[] (user + assistant).
Auto-load sessions saat login: getSessions() dipanggil di mount untuk sinkron list.
onSend:
Append user message → call sendChat → append assistant answer.
onUploadChange:
Upload → toast → refresh sidebar via getDocuments.
Chat sessions:
- Chat Baru → createSession() → set aktif + reset thread.
- Pilih session → getSessionHistory() → render history.
- Hapus session → confirm modal → deleteSession().
- Rename session → renameSession().
UI:
Header (AppHeader) + Sidebar (KnowledgeSidebar) + Chat area (ChatThread + ChatComposer).
Sidebar versi desktop dan drawer versi mobile.
Auth Pages

Login.tsx
router.post("/login/") (Inertia) dengan username/password.
Tampilkan error dari backend via errors.auth.
Register.tsx
router.post("/register/") dengan username/email/password/password_confirmation.
Error handling per-field + error umum.
Komponen UI

AppHeader.tsx
Header sticky: logo, nav tab, toggle light/dark, dropdown profile.
Logout via Inertia Link ke /logout/.
KnowledgeSidebar.tsx
Menampilkan list dokumen + status analyzed/processing.
Tombol upload, progress storage.
List chat session + tombol Chat Baru + delete.
Pagination: tombol "Muat lagi" jika masih ada session berikutnya.
ChatThread.tsx
Render ChatBubble per item + auto scroll ke bawah.
ChatComposer.tsx
Input chat dengan textarea auto-resize.
Enter untuk send, Shift+Enter untuk newline.
Tombol upload + tombol kirim.
ChatBubble.tsx
Render bubble user/assistant.
Untuk assistant: render Markdown (GFM) + sanitize.
Fallback kalau model mengirim tabel plaintext (tab/spasi).
Panel “Rujukan” (sources) bisa toggle.
DocumentItem.tsx
Deteksi ikon sesuai ekstensi file.
Toast.tsx
Notifikasi success/error.
Styling & Utilities

Tailwind utility class + cn() (utils.ts).
Banyak visual glass/blur dan animasi kecil langsung di komponen.
Alur Data Utama (End‑to‑End)

Backend render Inertia page Chat/Index dengan props awal.
Index.tsx set state dari props.
Chat:
onSend → sendChat() → append jawaban.
Upload:
uploadDocuments() → refresh sidebar via getDocuments().
Semua API lewat /api/* menggunakan Axios instance.
Catatan Teknis yang Perlu Diketahui

sendChat() di Index.tsx belum memasukkan sources ke state items.
ChatBubble sudah siap menampilkan rujukan, tapi items hanya menyimpan text.
Kalau mau rujukan tampil, items harus diberi sources: res.sources.
