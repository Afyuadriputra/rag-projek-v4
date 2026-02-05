# Use Case — Academic RAG System

Dokumen ini merinci use case utama sistem Academic RAG, mencakup aktor, alur normal, alternatif, error, dan log audit yang dihasilkan.

---

## 1) Aktor & Peran

- **Mahasiswa (User)**: mengelola knowledge base pribadi (upload dokumen), melakukan chat akademik, membuat & mengelola sesi chat.
- **Admin**: mengelola kuota upload user, melihat log audit untuk aktivitas.
- **Sistem (RAG Engine)**: memproses dokumen (ingest, embedding) dan menjawab pertanyaan.

---

## 2) Use Case Utama

### UC‑01 — Registrasi User
**Aktor:** Mahasiswa  
**Tujuan:** Membuat akun baru.  
**Prekondisi:** User belum login.

**Alur Normal:**
1. User membuka `/register/`.
2. User mengisi username, email, password, konfirmasi password.
3. Sistem memvalidasi input.
4. Sistem membuat akun dan otomatis membuat `UserQuota` default (10MB).
5. Sistem login otomatis dan redirect ke `/`.

**Alternatif / Error:**
- Username sudah digunakan → tampil error.
- Password tidak cocok → error validasi.
- Error sistem → tampil error umum.

**Audit Log:**
- `action=register status=success user_id=...`
- `action=register status=fail reason=duplicate_username`

---

### UC‑02 — Login User
**Aktor:** Mahasiswa  
**Tujuan:** Masuk ke sistem.  
**Prekondisi:** User terdaftar.

**Alur Normal:**
1. User membuka `/login/`.
2. User isi username + password.
3. Sistem autentikasi sukses.
4. User redirect ke `/`.

**Alternatif / Error:**
- Kredensial salah → tampil error.
- Rate limit (axes) → tampil pesan terkunci.

**Audit Log:**
- `action=login status=success user_id=...`
- `action=login status=fail reason=invalid_credentials`
- `action=login status=locked`

---

### UC‑03 — Logout User
**Aktor:** Mahasiswa  
**Tujuan:** Keluar dari sistem.  
**Prekondisi:** User login.

**Alur Normal:**
1. User klik menu profil → logout.
2. Sistem mengakhiri session.
3. Redirect ke `/login/`.

**Audit Log:**
- `action=logout status=success`

---

### UC‑04 — Upload Dokumen Knowledge Base
**Aktor:** Mahasiswa  
**Tujuan:** Menambahkan file akademik ke knowledge base.  
**Prekondisi:** User login, kuota tersedia.

**Alur Normal:**
1. User klik tombol upload.
2. Pilih file (`pdf/xlsx/xls/csv/md/txt`).
3. Sistem menyimpan file ke media storage.
4. Sistem ingest dokumen → parsing → metadata → embedding ke Chroma.
5. UI refresh daftar dokumen + storage.

**Alternatif / Error:**
- Kuota tidak cukup → upload ditolak.
- File tidak didukung → error parsing.
- File corrupt → parsing gagal.
- Payload terlalu besar → 413.

**Audit Log:**
- `action=upload status=success ...`
- `action=upload status=payload_too_large`
- `action=upload status=error`

---

### UC‑05 — Lihat Daftar Dokumen
**Aktor:** Mahasiswa  
**Tujuan:** Melihat dokumen di sidebar knowledge base.  
**Prekondisi:** User login.

**Alur Normal:**
1. Sistem memanggil `GET /api/documents/`.
2. Sistem menampilkan list dokumen + storage usage.

---

### UC‑06 — Hapus Dokumen Knowledge Base
**Aktor:** Mahasiswa  
**Tujuan:** Menghapus dokumen & embedding.  
**Prekondisi:** User login, dokumen milik user.

**Alur Normal:**
1. User klik delete dokumen.
2. Modal konfirmasi muncul.
3. User konfirmasi.
4. Sistem hapus embedding di Chroma + file storage + DB record.
5. UI update list dokumen.

**Alternatif / Error:**
- Dokumen tidak ditemukan → 404.
- Error vector DB → log error.

**Audit Log:**
- `action=doc_delete status=success doc_id=...`
- `action=doc_delete status=not_found doc_id=...`

---

### UC‑07 — Chat Akademik (RAG)
**Aktor:** Mahasiswa  
**Tujuan:** Bertanya berdasarkan dokumen/knowledge base.  
**Prekondisi:** User login.

**Alur Normal:**
1. User mengetik pertanyaan di chat.
2. Sistem mencari context di vector DB (filter by user_id).
3. LLM menjawab (LLM‑first, context optional).
4. History tersimpan dalam session.

**Alternatif / Error:**
- session_id invalid → 400.
- LLM error → 500, toast error.

**Audit Log:**
- (Chat log tercatat via request log + error log)

---

### UC‑08 — Create Session Chat
**Aktor:** Mahasiswa  
**Tujuan:** Membuat sesi chat baru.  
**Prekondisi:** User login.

**Alur Normal:**
1. User klik “Chat Baru”.
2. Sistem membuat session.
3. Session muncul di sidebar.

**Audit Log:**
- `action=session_create status=success session_id=...`

---

### UC‑09 — Rename Session Chat
**Aktor:** Mahasiswa  
**Tujuan:** Mengubah judul sesi chat.  
**Prekondisi:** User login.

**Alur Normal:**
1. User klik rename.
2. User input judul baru.
3. Sistem update title di DB.

**Audit Log:**
- `action=session_rename status=success session_id=...`

---

### UC‑10 — Delete Session Chat
**Aktor:** Mahasiswa  
**Tujuan:** Menghapus sesi chat.  
**Prekondisi:** User login.

**Alur Normal:**
1. User klik delete session.
2. Modal konfirmasi muncul.
3. Sistem hapus session + history.

**Audit Log:**
- `action=session_delete status=success session_id=...`

---

### UC‑11 — Reingest Dokumen
**Aktor:** Mahasiswa  
**Tujuan:** Memproses ulang dokumen (refresh embedding).  
**Prekondisi:** User login.

**Alur Normal:**
1. User (atau sistem) memanggil `/api/reingest/`.
2. Sistem hapus embedding lama.
3. Sistem ingest ulang dokumen.

**Audit Log:**
- `action=reingest status=success doc_ids=[...]`

---

## 3) Use Case Admin

### UC‑12 — Update Kuota User
**Aktor:** Admin  
**Tujuan:** Mengatur quota upload user.  
**Prekondisi:** Admin login di Django Admin.

**Alur Normal:**
1. Admin buka Django Admin → UserQuota.
2. Admin mengubah `quota_bytes` (atau input MB).
3. Sistem menyimpan kuota baru.

**Audit Log:**
- `action=quota_update target_user=... old_quota=... new_quota=...`

---

## 4) Non‑Functional Use Case

### UC‑13 — Audit & Monitoring
**Tujuan:** Memonitor aktivitas sistem.

**Fitur:**
- Request log (method, path, status, user, ip, ua).
- Audit log di file `logs/audit.log`.
- Rotating file harian, retensi 14 hari.

---

## 5) Ringkasan

Use case mencakup seluruh alur utama: **auth, upload, chat, session management, dokumen, reingest, dan admin quota**.  
Audit log tersedia untuk menelusuri aktivitas penting (CCTV‑style monitoring).  
