import axios from "axios";

// ==========================================
// 1. SETUP AXIOS INSTANCE
// ==========================================
const apiClient = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
  // Konfigurasi untuk Django CSRF Protection
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  withCredentials: true,
});

// ==========================================
// 2. TIPE DATA (INTERFACES)
// ==========================================

export interface ChatSource {
  source: string;   // judul/nama dokumen
  snippet: string;  // cuplikan konteks yang dipakai
}

// ✅ Chat API
export interface ChatResponse {
  answer?: string; // backend sukses -> {answer}
  sources?: ChatSource[];
  session_id?: number;
  error?: string;  // backend error -> {error}
}

// ✅ Upload API
export interface UploadResponse {
  status: "success" | "error";
  msg: string;
}

// ✅ Documents API (BARU)
export interface DocumentDto {
  id: number;
  title: string;
  is_embedded: boolean;
  uploaded_at: string; // "YYYY-MM-DD HH:MM"
  size_bytes: number;
}

// ✅ Documents API response (BARU)
export interface DocumentsResponse {
  documents: DocumentDto[];
  storage: {
    used_bytes: number;
    quota_bytes: number;
    used_pct: number;
    used_human?: string;  // dari backend (optional)
    quota_human?: string; // dari backend (optional)
  };
}

// ✅ Chat Sessions
export interface ChatSessionDto {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface SessionsResponse {
  sessions: ChatSessionDto[];
  pagination?: {
    page: number;
    page_size: number;
    total: number;
    has_next: boolean;
  };
}

// ==========================================
// 3. API FUNCTIONS (FUNGSI UTAMA DITANDAI)
// ==========================================

/** ⭐ FUNGSI UTAMA #1: CHAT
 * Mengirim pesan chat ke AI
 * URL Backend: POST /api/chat/
 */
export const sendChat = async (message: string, sessionId?: number) => {
  // Payload harus match dengan `json.loads(request.body)` di views.py
  const response = await apiClient.post<ChatResponse>("/chat/", {
    message,
    session_id: sessionId,
  });
  return response.data;
};

/** ⭐ FUNGSI UTAMA #2: UPLOAD DOCUMENTS
 * Upload banyak file sekaligus
 * URL Backend: POST /api/upload/
 */
export const uploadDocuments = async (files: FileList) => {
  const formData = new FormData();

  // Masukkan semua file ke FormData dengan key 'files'
  // (Sesuai `request.FILES.getlist('files')` di views.py)
  Array.from(files).forEach((file) => {
    formData.append("files", file);
  });

  const response = await apiClient.post<UploadResponse>("/upload/", formData, {
    headers: {
      // Wajib ubah Content-Type agar server tahu ini file upload
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
};

/** ⭐ FUNGSI UTAMA #3: GET DOCUMENTS (BARU)
 * Ambil daftar dokumen + storage untuk sidebar (refresh setelah upload)
 * URL Backend: GET /api/documents/
 */
export const getDocuments = async () => {
  const response = await apiClient.get<DocumentsResponse>("/documents/");
  return response.data;
};

export const deleteDocument = async (docId: number) => {
  const response = await apiClient.delete<{ status: string }>(`/documents/${docId}/`);
  return response.data;
};

export const getSessions = async (page: number = 1, pageSize: number = 20) => {
  const response = await apiClient.get<SessionsResponse>("/sessions/", {
    params: { page, page_size: pageSize },
  });
  return response.data;
};

export const createSession = async (title?: string) => {
  const response = await apiClient.post<{ session: ChatSessionDto }>("/sessions/", {
    title,
  });
  return response.data;
};

export const renameSession = async (sessionId: number, title: string) => {
  const response = await apiClient.patch<{ session: ChatSessionDto }>(`/sessions/${sessionId}/`, {
    title,
  });
  return response.data;
};

export const deleteSession = async (sessionId: number) => {
  const response = await apiClient.delete<{ status: string }>(`/sessions/${sessionId}/`);
  return response.data;
};

export const getSessionHistory = async (sessionId: number) => {
  const response = await apiClient.get<{ history: Array<{ question: string; answer: string; time: string; date: string }> }>(
    `/sessions/${sessionId}/`
  );
  return response.data;
};

export default apiClient;
