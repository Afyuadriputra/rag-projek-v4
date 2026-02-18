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

export interface PlannerOption {
  id: number;
  label: string;
  value: string;
}

export interface PlannerSessionState {
  current_step?: string;
  data_level?: Record<string, unknown>;
  collected_data?: Record<string, unknown>;
}

// ✅ Chat API (mode=chat)
export interface ChatModeResponse {
  type?: "chat";
  answer?: string; // backend sukses -> {answer}
  sources?: ChatSource[];
  session_id?: number;
  error?: string;  // backend error -> {error}
}

// ✅ Planner API (mode=planner)
export interface PlannerModeResponse {
  type: "planner_step" | "planner_output" | "planner_generate";
  answer: string;
  options: PlannerOption[];
  allow_custom: boolean;
  planner_step: string;
  session_state: PlannerSessionState;
  planner_meta?: Record<string, unknown>;
  error?: string;
}

export type ChatResponse = ChatModeResponse | PlannerModeResponse;

export type SendChatPayload = {
  message: string;
  session_id?: number;
  mode?: "chat" | "planner";
  option_id?: number;
};

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
export const sendChat = async (
  messageOrPayload: string | SendChatPayload,
  sessionId?: number
) => {
  // Backward-compatible:
  // - sendChat("halo", sessionId)
  // - sendChat({ message, mode, option_id, session_id })
  const payload: SendChatPayload =
    typeof messageOrPayload === "string"
      ? { message: messageOrPayload, session_id: sessionId, mode: "chat" }
      : {
          message: messageOrPayload.message,
          session_id: messageOrPayload.session_id,
          mode: messageOrPayload.mode ?? "chat",
          option_id: messageOrPayload.option_id,
        };

  const response = await apiClient.post<ChatResponse>("/chat/", payload);
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
