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

const PLANNER_START_TIMEOUT_MS = 90000;

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
  detected?: boolean;
  confidence?: number;
}

export interface PlannerSessionState {
  current_step?: string;
  data_level?: Record<string, unknown>;
  collected_data?: Record<string, unknown>;
}

export interface ProfileHintCandidate {
  value: string | number;
  label: string;
  confidence: number;
  evidence: string[];
}

export interface ProfileHints {
  major_candidates?: ProfileHintCandidate[];
  career_candidates?: ProfileHintCandidate[];
  semester_candidates?: ProfileHintCandidate[];
  confidence_summary?: "high" | "medium" | "low";
  has_relevant_docs?: boolean;
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
  planner_warning?: string | null;
  profile_hints?: ProfileHints;
  planner_meta?: {
    origin?: "start_auto" | "user_input" | "option_select";
    [key: string]: unknown;
  };
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

export interface TimelineItem {
  id: string;
  kind: "chat_user" | "chat_assistant" | "planner_milestone" | "planner_output";
  text: string;
  time: string;
  date: string;
  meta?: {
    planner_step?: string;
    event_type?: "start_auto" | "option_select" | "user_input" | "generate" | "save";
    option_id?: number | null;
    option_label?: string;
    warning?: string | null;
    confidence_summary?: "high" | "medium" | "low";
  };
}

export interface SessionTimelineResponse {
  timeline: TimelineItem[];
  pagination?: {
    page: number;
    page_size: number;
    total: number;
    has_next: boolean;
  };
}

export interface PlannerWizardStep {
  step_key: string;
  title: string;
  question: string;
  options: Array<{ id: number; label: string; value: string }>;
  allow_manual: boolean;
  required?: boolean;
  source_hint?: "document" | "profile" | "mixed" | string;
  reason?: string;
}

export interface PlannerHeaderMeta {
  major_label: string;
  major_confidence_level: "high" | "medium" | "low" | string;
  major_confidence_score: number;
  doc_context_label?: string;
}

export interface PlannerDocRelevance {
  is_relevant: boolean;
  score: number;
  reasons: string[];
}

export interface PlannerMajorCandidate {
  value: string | number;
  label: string;
  confidence: number;
  evidence?: string[];
}

export interface PlannerProfileHintsSummary {
  major_candidates: PlannerMajorCandidate[];
  confidence_summary?: "high" | "medium" | "low";
}

export interface PlannerStartResponse {
  status: "success" | "error";
  planner_run_id?: string;
  session_id?: number;
  wizard_blueprint?: {
    version: string;
    data_level?: Record<string, unknown>;
    profile_hints?: Record<string, unknown>;
    documents_summary?: Array<{ id: number; title: string; uploaded_at?: string }>;
    meta?: Record<string, unknown>;
    steps: PlannerWizardStep[];
  };
  documents_summary?: Array<{ id: number; title: string; uploaded_at?: string }>;
  doc_relevance?: PlannerDocRelevance;
  profile_hints_summary?: PlannerProfileHintsSummary;
  planner_header?: PlannerHeaderMeta;
  progress?: { current: number; estimated_total: number; style?: string };
  ui_hints?: { show_major_header?: boolean; show_path_header?: boolean };
  intent_candidates?: PlannerIntentCandidate[];
  manual_intent_enabled?: boolean;
  next_action?: "choose_intent" | string;
  error_code?: string;
  hint?: string;
  reasons?: string[];
  warning?: string | null;
  required_upload?: boolean;
  progress_hints?: string[];
  planner_meta?: Record<string, unknown>;
  error?: string;
}

export interface PlannerIntentCandidate {
  id: number;
  label: string;
  value: string;
  reason?: string;
}

export interface PlannerNextStepResponse {
  status: "success" | "error";
  step?: PlannerWizardStep;
  done_recommendation?: string;
  step_header?: { path_label?: string; reason?: string };
  progress?: { current: number; estimated_total?: number; max_depth?: number };
  can_generate_now?: boolean;
  path_summary?: string;
  major_state?: {
    major_label?: string;
    source?: "user_override" | "inferred" | "inferred_document" | "unknown" | string;
    major_confidence_level?: "high" | "medium" | "low" | string;
    major_confidence_score?: number;
  };
  ui_hints?: { show_major_header?: boolean; show_path_header?: boolean };
  path_taken?: Array<{
    seq: number;
    step_key: string;
    question?: string;
    answer_value: string;
    answer_mode: "option" | "manual" | string;
  }>;
  error_code?: string;
  hint?: string;
  error?: string;
}

export interface PlannerExecuteResponse {
  status: "success" | "error";
  answer?: string;
  sources?: ChatSource[];
  session_id?: number;
  planner_meta?: Record<string, unknown>;
  error_code?: string;
  hint?: string;
  error?: string;
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

export const getSessionTimeline = async (sessionId: number, page: number = 1, pageSize: number = 100) => {
  const response = await apiClient.get<SessionTimelineResponse>(`/sessions/${sessionId}/timeline/`, {
    params: { page, page_size: pageSize },
  });
  return response.data;
};

export const plannerStartV3 = async ({
  files,
  sessionId,
  reuseDocIds,
}: {
  files?: FileList | File[];
  sessionId?: number;
  reuseDocIds?: number[];
}) => {
  if (files && (Array.isArray(files) ? files.length > 0 : files.length > 0)) {
    const fd = new FormData();
    const arr = Array.isArray(files) ? files : Array.from(files);
    arr.forEach((f) => fd.append("files", f));
    if (sessionId) fd.append("session_id", String(sessionId));
    (reuseDocIds || []).forEach((id) => fd.append("reuse_doc_ids", String(id)));
    const response = await apiClient.post<PlannerStartResponse>("/planner/start/", fd, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: PLANNER_START_TIMEOUT_MS,
    });
    return response.data;
  }
  const response = await apiClient.post<PlannerStartResponse>(
    "/planner/start/",
    {
      session_id: sessionId,
      reuse_doc_ids: reuseDocIds || [],
    },
    { timeout: PLANNER_START_TIMEOUT_MS }
  );
  return response.data;
};

export const plannerExecuteV3 = async (payload: {
  planner_run_id: string;
  session_id?: number;
  answers: Record<string, unknown>;
  path_taken?: Array<Record<string, unknown>>;
  client_summary?: string;
}) => {
  const response = await apiClient.post<PlannerExecuteResponse>("/planner/execute/", payload);
  return response.data;
};

export const plannerNextStepV3 = async (payload: {
  planner_run_id: string;
  step_key: string;
  answer_value: string;
  answer_mode: "option" | "manual";
  client_step_seq: number;
}) => {
  const response = await apiClient.post<PlannerNextStepResponse>("/planner/next-step/", payload);
  return response.data;
};

export const plannerCancelV3 = async (plannerRunId: string) => {
  const response = await apiClient.post<{ status: string; status_detail?: string; error?: string }>(
    "/planner/cancel/",
    { planner_run_id: plannerRunId }
  );
  return response.data;
};

export default apiClient;
