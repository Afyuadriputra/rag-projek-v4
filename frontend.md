# Dokumentasi Frontend — Academic RAG System

Dokumen ini menjelaskan secara **detail dan rinci** cara kerja frontend di folder `frontend/src/`.
Frontend menggunakan **React + Inertia.js + Vite** dan berkomunikasi dengan backend Django melalui API JSON.

---

## 1) Struktur Folder `frontend/src/`

```
frontend/src/
  main.tsx
  index.css
  App.css
  styles/
    glass.css
  pages/
    Auth/
      Login.tsx
      Register.tsx
    Chat/
      Index.tsx
  components/
    atoms/
      Avatar.tsx
      Badge.tsx
      IconButton.tsx
      ProgressBar.tsx
      ToggleSwitch.tsx
    molecules/
      ChatBubble.tsx
      ChatComposer.tsx
      DocumentItem.tsx
      NavTabs.tsx
      Toast.tsx
      Toggle.tsx
    organisms/
      AppHeader.tsx
      ChatThread.tsx
      KnowledgeSidebar.tsx
  lib/
    api.ts
    utils.ts
```

---

## 2) Entry Point — `main.tsx`

File ini adalah bootstrap Inertia + React.

**Fungsi utama:**
- Inisialisasi Inertia dengan `createInertiaApp`.
- `resolve` halaman dari `frontend/src/pages/**`.
- Setup global Axios CSRF header.
- Load CSS global (`index.css`, `glass.css`).
- Inisialisasi root Inertia untuk halaman `Auth/Login`, `Auth/Register`, `Chat/Index`.

**Dampak:**
Setiap route Django Inertia (`Chat/Index`, `Auth/Login`, dll) akan dipetakan ke komponen React di folder `pages/`.

---

## 3) API Client — `lib/api.ts`

Satu tempat untuk komunikasi ke backend.

**Axios instance:**
- `baseURL = /api`
- CSRF header otomatis
- Error handling di UI membaca `err.response.data.msg` (upload) dan `err.response.data.error` (chat).

**Fungsi penting:**
- `sendChat(message, sessionId)` → `POST /api/chat/`
- `uploadDocuments(files)` → `POST /api/upload/` (multipart)
- `getDocuments()` → `GET /api/documents/`
- `deleteDocument(id)` → `DELETE /api/documents/<id>/`
- `getSessions()` → `GET /api/sessions/`
- `createSession()` → `POST /api/sessions/`
- `deleteSession(id)` → `DELETE /api/sessions/<id>/`
- `renameSession(id, title)` → `PATCH /api/sessions/<id>/`
- `getSessionHistory(id)` → `GET /api/sessions/<id>/`

---

## 4) Halaman Auth — `pages/Auth`

### 4.1 `Login.tsx`
- Form username/password
- Submit via `router.post("/login/")` (Inertia)
- Menampilkan error dari backend (`errors.auth`)
- Tombol submit disabled saat `loading`

### 4.2 `Register.tsx`
- Form username/email/password/password_confirmation
- Submit via `router.post("/register/")`
- Menampilkan error per field + error umum

---

## 5) Halaman Utama Chat — `pages/Chat/Index.tsx`

Ini adalah **inti frontend** (dashboard chat + sidebar + upload + sessions).

### 5.1 Props dari Backend
Diterima lewat Inertia:
- `user`
- `initialHistory`
- `documents`
- `storage`
- `sessions`
- `activeSessionId`

### 5.2 State utama
- `items`: list chat (ChatBubble)
- `documents`: list dokumen user
- `storage`: quota/usage
- `sessions`: list session chat
- `activeSession`: session aktif
- `loading`: status request utama
- `toast`: notifikasi
- `confirmDeleteId`: modal delete session
- `confirmDeleteDocId`: modal delete dokumen
- `deletingDocId`: progress delete dokumen
- `sessionsPage` & `sessionsHasNext`: pagination sidebar
- `loadingMoreSessions`: status load more

### 5.3 Alur Chat
1. User mengetik pesan di `ChatComposer`.
2. `sendChat()` → backend.
3. Response masuk ke `items`.
4. Error handling:
   - 500: toast error, input tetap aktif
   - invalid session_id: toast error

### 5.4 Alur Upload
1. Klik upload → file input hidden.
2. `uploadDocuments()`.
3. Toast tampil.
4. `refreshDocuments()`.
5. Error handling:
   - ukuran besar → toast error
   - tipe file tidak didukung → toast error

### 5.5 Alur Chat Session
- **Chat baru**: `createSession()` → set aktif → reset thread.
- **Select session**: `getSessionHistory()` → render history.
- **Rename**: `renameSession()`.
- **Delete**: modal confirm → `deleteSession()`.
- **Pagination**: tombol “Muat lagi” → append session list

### 5.6 Alur Hapus Dokumen
- Klik delete di sidebar.
- Modal confirm.
- `deleteDocument()`.
- Progress overlay + spinner.
- `refreshDocuments()`.

---

## 6) Organism Components

### 6.1 `AppHeader.tsx`
- Navbar atas
- Toggle dark mode
- Dropdown profile + logout
- Test ids: `user-menu-button`, `logout-link`

### 6.2 `KnowledgeSidebar.tsx`
- List dokumen (knowledge base)
- List chat sessions
- Upload button
- Progress storage
- Skeleton + overlay saat delete dokumen
- Test ids:
  - `doc-list`
  - `session-create`
  - `session-item-<id>`
  - `session-rename-<id>`
  - `session-delete-<id>`
  - `sessions-load-more`

### 6.3 `ChatThread.tsx`
- Render list chat bubble
- Auto scroll ke bawah
- Test id: `chat-thread`

---

## 7) Molecule Components

### 7.1 `ChatBubble.tsx`
- Render pesan user/assistant
- Mendukung Markdown (ReactMarkdown + GFM)
- Normalisasi `\n` → newline
- Panel sources (rujukan dokumen)
- Sanitasi konten (mencegah XSS) saat render markdown

### 7.2 `ChatComposer.tsx`
- Input chat
- Upload button
- Disable saat delete
- Status line berubah saat proses
- Test ids: `chat-input`, `chat-send`, `chat-upload`, `upload-input`

### 7.3 `DocumentItem.tsx`
- Menampilkan file dokumen + status embed
- Tombol delete + spinner
- Overlay “Menghapus…”
- Test id: `doc-<id>` dan tombol `doc-<id>-delete`

### 7.4 `Toast.tsx`
- Notifikasi global
- Test ids: `toast`, `toast-message`

---

## 8) Atoms & Util

- `ProgressBar.tsx`: progress storage quota
- `ToggleSwitch.tsx`: switch light/dark
- `utils.ts`: helper `cn()` untuk className

---

## 9) UI/UX Notes

- Layout menggunakan Tailwind utility classes.
- Ada glass/blur aesthetic (`glass.css`).
- Mobile support: sidebar drawer + safe area padding.
- Chat composer selalu fixed di bawah.
- Skeleton + overlay dipakai saat delete dokumen.
- Tombol upload/chat disabled saat delete berjalan (state konsisten).

---

## 10) Security & Reliability (Frontend)

- **XSS**: output chat disanitasi (Markdown render aman).
- **Error handling**: toast tampil untuk 500, 400, network error.
- **Rate-limit login**: error “coba lagi” ditampilkan dari backend.
- **Upload guard**: ukuran terlalu besar + file type reject ditangani.

---

## 11) E2E Tests (Playwright)

File: `frontend/e2e/security.spec.ts` dan `frontend/e2e/chat.spec.ts`.

Coverage utama:
- Login success/fail/rate-limit, logout redirect.
- Chat: XSS sanitize, API 500, invalid session_id.
- Upload: oversized, reject, success tampil di sidebar.
- Delete doc: modal + spinner + item hilang.
- Sessions: create/rename/delete + pagination.
- API down: toast error, UI tetap responsif.

Cara jalan:
```bash
cd frontend
npx playwright test
```

---

## 12) Ringkasan Flow Frontend

1. Backend render `Chat/Index` via Inertia.
2. Props masuk ke React → state init.
3. User upload → backend → refresh docs.
4. User chat → backend → history update.
5. User manage sessions → create/rename/delete.
6. UI selalu sinkron dengan API.

---

Jika dibutuhkan, dokumentasi ini bisa diperluas menjadi diagram arsitektur frontend atau flowchart UI/UX.
