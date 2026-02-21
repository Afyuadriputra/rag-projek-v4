import React, { useEffect, useMemo, useRef, useState } from "react";
import { usePage } from "@inertiajs/react";
import { cn } from "@/lib/utils";

// Components
import AppHeader from "@/components/organisms/AppHeader";
import KnowledgeSidebar from "@/components/organisms/KnowledgeSidebar";
import ChatThread from "@/components/organisms/ChatThread";
import ChatComposer from "@/components/molecules/ChatComposer";
import Toast from "@/components/molecules/Toast";

// API & Types
import {
  sendChat,
  uploadDocuments,
  getDocuments,
  getSessions,
  createSession,
  deleteSession,
  getSessionTimeline,
  renameSession,
  deleteDocument,
  plannerStartV3,
  plannerExecuteV3,
  plannerCancelV3,
} from "@/lib/api";
import type {
  DocumentDto,
  DocumentsResponse,
  ChatSessionDto,
  ChatResponse,
  PlannerModeResponse,
  TimelineItem,
  PlannerWizardStep,
  PlannerProfileHintsSummary,
  PlannerStartResponse,
} from "@/lib/api";
import type { ChatItem } from "@/components/molecules/ChatBubble";

// --- Types ---
type StorageInfo = {
  used_bytes: number;
  quota_bytes: number;
  used_pct: number;
  used_human?: string;
  quota_human?: string;
};

type PageProps = {
  user: { id: number; username: string; email: string };
  activeSessionId: number;
  sessions: ChatSessionDto[];
  initialHistory: Array<{
    question: string;
    answer: string;
    time: string;
    date: string;
  }>;
  documents: DocumentDto[];
  storage: StorageInfo;
};

// --- Helper ---
function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

function plannerPanelId(sessionId?: number) {
  return `planner-panel-${sessionId ?? "global"}`;
}

function buildPlannerPanelItem(
  sessionId: number | undefined,
  state: "idle" | "onboarding" | "uploading" | "ready" | "reviewing" | "executing" | "done"
): ChatItem {
  return {
    id: plannerPanelId(sessionId),
    role: "assistant",
    text: "",
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    message_kind: "planner_panel",
    planner_panel_state: state,
    session_id: sessionId,
    updated_at_ts: Date.now(),
  };
}

function isPlannerResponse(res: ChatResponse): res is PlannerModeResponse {
  return (
    (res as PlannerModeResponse)?.type === "planner_step" ||
    (res as PlannerModeResponse)?.type === "planner_output" ||
    (res as PlannerModeResponse)?.type === "planner_generate"
  );
}

function mapTimelineItemToChatItem(t: TimelineItem): ChatItem {
  if (t.kind === "chat_user") {
    return {
      id: t.id,
      role: "user",
      text: t.text,
      time: t.time,
      message_kind: "user",
      updated_at_ts: Date.now(),
    };
  }
  if (t.kind === "chat_assistant") {
    return {
      id: t.id,
      role: "assistant",
      text: t.text,
      time: t.time,
      response_type: "chat",
      message_kind: "assistant_chat",
      updated_at_ts: Date.now(),
    };
  }
  if (t.kind === "planner_output") {
    return {
      id: t.id,
      role: "assistant",
      text: t.text,
      time: t.time,
      response_type: "planner_output",
      planner_step: t.meta?.planner_step,
      planner_meta: {
        event_type: t.meta?.event_type,
        option_id: t.meta?.option_id,
        option_label: t.meta?.option_label,
      },
      message_kind: "assistant_planner_step",
      planner_warning: t.meta?.warning ?? null,
      profile_hints: t.meta?.confidence_summary ? { confidence_summary: t.meta.confidence_summary } : {},
      updated_at_ts: Date.now(),
    };
  }
  return {
    id: t.id,
    role: "assistant",
    text: t.text,
    time: t.time,
    response_type: "planner_step",
    planner_step: t.meta?.planner_step,
    planner_meta: {
      event_type: t.meta?.event_type,
      option_id: t.meta?.option_id,
      option_label: t.meta?.option_label,
    },
    message_kind: "system_mode",
    planner_warning: t.meta?.warning ?? null,
    profile_hints: t.meta?.confidence_summary ? { confidence_summary: t.meta.confidence_summary } : {},
    updated_at_ts: Date.now(),
  };
}

export default function Index() {
  const SESSIONS_PAGE_SIZE = 20;
  const { props } = usePage<PageProps>();
  const { user, initialHistory, documents: initialDocs, storage: initialStorage, sessions: initialSessions, activeSessionId } = props;

  // State
  const [dark, setDark] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const persisted = window.localStorage.getItem("theme");
    if (persisted === "dark") return true;
    if (persisted === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });
  const [documents, setDocuments] = useState<DocumentDto[]>(initialDocs ?? []);
  const [storage, setStorage] = useState<StorageInfo | undefined>(initialStorage);
  const [sessions, setSessions] = useState<ChatSessionDto[]>(initialSessions ?? []);
  const [activeSession, setActiveSession] = useState<number | undefined>(activeSessionId);
  const [sessionsPage, setSessionsPage] = useState(1);
  const [sessionsHasNext, setSessionsHasNext] = useState(false);
  const [sessionsLoadingMore, setSessionsLoadingMore] = useState(false);
  const [mode, setMode] = useState<"chat" | "planner">("chat");
  const [plannerUiState, setPlannerUiState] = useState<"idle" | "onboarding" | "uploading" | "ready" | "reviewing" | "executing" | "done">("idle");
  const [plannerRunId, setPlannerRunId] = useState<string | null>(null);
  const [wizardSteps, setWizardSteps] = useState<PlannerWizardStep[]>([]);
  const [wizardAnswers, setWizardAnswers] = useState<Record<string, string>>({});
  const [wizardIndex, setWizardIndex] = useState(0);
  const [plannerDocs, setPlannerDocs] = useState<Array<{ id: number; title: string }>>([]);
  const [plannerProgressMessage, setPlannerProgressMessage] = useState("Memvalidasi dokumen...");
  const [plannerRelevanceError, setPlannerRelevanceError] = useState<string | null>(null);
  const [plannerMajorSummary, setPlannerMajorSummary] = useState<PlannerProfileHintsSummary | null>(null);
  const [plannerStateBySession, setPlannerStateBySession] = useState<Record<number, Record<string, unknown>>>({});
  const [plannerInitializedBySession, setPlannerInitializedBySession] = useState<Record<number, boolean>>({});
  const [plannerWarningBySession, setPlannerWarningBySession] = useState<Record<number, string | null>>({});
  const [activePlannerOptionMessageId, setActivePlannerOptionMessageId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [confirmDeleteDocId, setConfirmDeleteDocId] = useState<number | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<number | null>(null);
  const [dragActive, setDragActive] = useState(false);

  // ✅ scroll container ref
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // ✅ composer height & safe area padding
  const [composerH, setComposerH] = useState(220); // fallback
  const [safeBottom, setSafeBottom] = useState(0);

  // Toast State
  const [toast, setToast] = useState<{
    open: boolean;
    kind: "success" | "error";
    msg: string;
  }>({ open: false, kind: "success", msg: "" });

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // --- Effects ---
  useEffect(() => {
    const root = document.documentElement;
    if (dark) {
      root.classList.add("dark");
      root.style.colorScheme = "dark";
      window.localStorage.setItem("theme", "dark");
      return;
    }
    root.classList.remove("dark");
    root.style.colorScheme = "light";
    window.localStorage.setItem("theme", "light");
  }, [dark]);

  // ✅ Auto-load sessions on mount (fresh login / avoid stale state)
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await getSessions(1, SESSIONS_PAGE_SIZE);
        if (!cancelled) {
          setSessions(res.sessions ?? []);
          setSessionsPage(1);
          setSessionsHasNext(!!res.pagination?.has_next);
        }
      } catch {
        // silent
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // ✅ Safe-area bottom (iPhone)
  useEffect(() => {
    const updateSafeArea = () => {
      // VisualViewport lebih akurat di iOS ketika keyboard muncul
      // Tapi safe inset tetap kita gunakan dari CSS env() via padding calc.
      // Untuk fallback JS: ambil perkiraan dari viewport.
      const vv = window.visualViewport;
      if (!vv) return;

      // Ini bukan "safe area" literal, tapi membantu saat keyboard / bar berubah.
      // Kita simpan 0-16 agar tidak overpad.
      setSafeBottom(0);
    };

    updateSafeArea();
    window.visualViewport?.addEventListener("resize", updateSafeArea);
    window.addEventListener("orientationchange", updateSafeArea);

    return () => {
      window.visualViewport?.removeEventListener("resize", updateSafeArea);
      window.removeEventListener("orientationchange", updateSafeArea);
    };
  }, []);

  // ✅ ukur tinggi composer dari elemen aslinya (absolute)
  useEffect(() => {
    let ro: ResizeObserver | null = null;
    let cancelled = false;

    const attach = () => {
      const el = document.querySelector('[data-testid="chat-composer"]') as HTMLElement | null;
      if (!el) return false;

      const update = () => {
        const h = el.getBoundingClientRect().height;
        // + extra spacing supaya konten terakhir benar-benar bebas dari overlay
        setComposerH(Math.ceil(h) + 16);
      };

      update();
      ro = new ResizeObserver(() => update());
      ro.observe(el);
      return true;
    };

    // retry beberapa kali karena Inertia kadang render bertahap
    let tries = 0;
    const tick = () => {
      if (cancelled) return;
      tries += 1;
      const ok = attach();
      if (!ok && tries < 20) requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelled = true;
      ro?.disconnect();
    };
  }, [user.id]);

  // --- Data Logic ---
  const refreshDocuments = async () => {
    try {
      const res: DocumentsResponse = await getDocuments();
      setDocuments(res.documents ?? []);
      if (res.storage) setStorage(res.storage as StorageInfo);
    } catch {
      // silent fail
    }
  };

  const initialItems = useMemo<ChatItem[]>(() => {
    const arr: ChatItem[] = [];
    if (!initialHistory || initialHistory.length === 0) {
      arr.push({
        id: uid(),
        role: "assistant",
        text:
          "Belum ada riwayat chat di sesi ini.\n\n" +
          "Kamu bisa:\n" +
          "- Upload KRS/KHS/Transkrip\n" +
          "- Tanya rekap jadwal per hari\n" +
          "- Cek total SKS\n",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      });
      return arr;
    }
    for (const h of initialHistory) {
      arr.push({ id: uid(), role: "user", text: h.question, time: h.time });
      arr.push({ id: uid(), role: "assistant", text: h.answer, time: h.time });
    }
    return arr;
  }, [initialHistory]);

  const [items, setItems] = useState<ChatItem[]>(initialItems);

  const activeSessionIdNum = typeof activeSession === "number" ? activeSession : undefined;
  const plannerWarning = activeSessionIdNum ? plannerWarningBySession[activeSessionIdNum] ?? null : null;
  const shouldRenderPlannerPanel =
    mode === "planner" && plannerUiState !== "idle" && plannerUiState !== "done";

  const itemsWithPlannerPanel = useMemo(() => {
    const base = items.filter((it) => it.message_kind !== "planner_panel");
    if (!shouldRenderPlannerPanel) return base;
    return [...base, buildPlannerPanelItem(activeSessionIdNum, plannerUiState)];
  }, [items, shouldRenderPlannerPanel, activeSessionIdNum, plannerUiState]);

  // ✅ Inertia reuse fix: sinkronkan ulang items saat user/history berubah
  useEffect(() => {
    setItems(initialItems);
  }, [user.id, initialItems]);

  useEffect(() => {
    let cancelled = false;
    const loadTimeline = async () => {
      if (!activeSessionIdNum) return;
      try {
        const res = await getSessionTimeline(activeSessionIdNum, 1, 200);
        if (cancelled) return;
        const mapped = (res.timeline ?? []).map(mapTimelineItemToChatItem);
        if (mapped.length > 0) {
          setItems(mapped);
        }
      } catch {
        // fallback to initialHistory mapping
      }
    };
    loadTimeline();
    return () => {
      cancelled = true;
    };
  }, [activeSessionIdNum]);

  // ✅ auto-scroll lebih “nempel bawah” (pakai scrollHeight besar)
  useEffect(() => {
    const t = setTimeout(() => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight + 9999, behavior: "smooth" });
    }, 120);
    return () => clearTimeout(t);
  }, [items, composerH, plannerUiState, mode]);

  useEffect(() => {
    if (mode === "planner") {
      setPlannerUiState((prev) => (prev === "idle" ? "onboarding" : prev));
      return;
    }
    setPlannerUiState("idle");
  }, [mode]);

  const upsertPlannerSystemMessage = (
    sessionId: number,
    messageId: string,
    timeStr: string,
    res: PlannerModeResponse
  ) => {
    const aiText = (res as any).answer ?? (res as any).error ?? "Maaf, tidak ada jawaban.";
    setItems((prev) => {
      const idx = prev.findIndex(
        (m) =>
          m.role === "assistant" &&
          m.session_id === sessionId &&
          m.message_kind === "system_mode" &&
          m.response_type === res.type &&
          m.planner_step === res.planner_step
      );

      const nextMsg: ChatItem = {
        id: idx >= 0 ? prev[idx].id : messageId,
        role: "assistant",
        text: aiText,
        time: timeStr,
        response_type: res.type,
        planner_step: res.planner_step,
        planner_options: res.options ?? [],
        allow_custom: res.allow_custom,
        session_state: res.session_state as Record<string, unknown>,
        planner_warning: res.planner_warning ?? null,
        profile_hints: (res.profile_hints as Record<string, unknown> | undefined) ?? {},
        planner_meta: (res.planner_meta as Record<string, unknown> | undefined) ?? {},
        message_kind: "system_mode",
        session_id: sessionId,
        updated_at_ts: Date.now(),
      };

      if (idx >= 0) {
        const cloned = [...prev];
        cloned[idx] = nextMsg;
        return cloned;
      }
      return [...prev, nextMsg];
    });
  };

  const pushAssistantResponse = (
    res: ChatResponse,
    timeStr: string,
    reqMeta?: { isAutoPlannerStart?: boolean; optionId?: number }
  ) => {
    const aiText = (res as any).answer ?? (res as any).error ?? "Maaf, tidak ada jawaban.";
    const messageId = uid();
    const sessionId = activeSessionIdNum;

    if (isPlannerResponse(res)) {
      let resolvedPlannerMessageId = messageId;
      if (sessionId) {
        setPlannerStateBySession((prev) => ({
          ...prev,
          [sessionId]: (res.session_state as Record<string, unknown>) ?? {},
        }));
        setPlannerInitializedBySession((prev) => ({ ...prev, [sessionId]: true }));
        setPlannerWarningBySession((prev) => ({
          ...prev,
          [sessionId]: (res.planner_warning as string | null | undefined) ?? null,
        }));
      }
      setActivePlannerOptionMessageId((res.options?.length ?? 0) > 0 ? messageId : null);

      const isAutoPlannerStart = !!reqMeta?.isAutoPlannerStart && !reqMeta?.optionId;
      if (isAutoPlannerStart && sessionId) {
        const existing = items.find(
          (m) =>
            m.role === "assistant" &&
            m.session_id === sessionId &&
            m.message_kind === "system_mode" &&
            m.response_type === res.type &&
            m.planner_step === res.planner_step
        );
        if (existing?.id) {
          resolvedPlannerMessageId = existing.id;
        }
        upsertPlannerSystemMessage(sessionId, messageId, timeStr, res);
      } else {
        setItems((prev) => [
          ...prev,
          {
            id: messageId,
            role: "assistant",
            text: aiText,
            time: timeStr,
            response_type: res.type,
            planner_step: res.planner_step,
            planner_options: res.options ?? [],
            allow_custom: res.allow_custom,
            session_state: res.session_state as Record<string, unknown>,
            planner_warning: res.planner_warning ?? null,
            profile_hints: (res.profile_hints as Record<string, unknown> | undefined) ?? {},
            planner_meta: (res.planner_meta as Record<string, unknown> | undefined) ?? {},
            message_kind: "assistant_planner_step",
            session_id: sessionId,
            updated_at_ts: Date.now(),
          },
        ]);
      }
      setActivePlannerOptionMessageId((res.options?.length ?? 0) > 0 ? resolvedPlannerMessageId : null);
      return;
    }

    setItems((prev) => [
      ...prev,
      {
        id: messageId,
        role: "assistant",
        text: aiText,
        time: timeStr,
        sources: (res as any).sources ?? [],
        response_type: "chat",
        message_kind: "assistant_chat",
        session_id: sessionId,
        updated_at_ts: Date.now(),
      },
    ]);
  };

  const handleFilesUpload = async (files: FileList | File[]) => {
    const normalized = Array.isArray(files) ? files : Array.from(files);
    if (!normalized.length) return;
    const dt = new DataTransfer();
    normalized.forEach((f) => dt.items.add(f));

    setLoading(true);
    setMobileMenuOpen(false);
    try {
      const res = await uploadDocuments(dt.files);
      setToast({ open: true, kind: res.status === "success" ? "success" : "error", msg: res.msg });
      await refreshDocuments();
    } catch (err: any) {
      const msg = err?.response?.data?.msg ?? err?.message ?? "Upload gagal.";
      setToast({ open: true, kind: "error", msg });
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async ({
    message,
    optionId,
    echoUser = true,
    userEchoText,
    sendMode,
    isAutoPlannerStart = false,
  }: {
    message: string;
    optionId?: number;
    echoUser?: boolean;
    userEchoText?: string;
    sendMode?: "chat" | "planner";
    isAutoPlannerStart?: boolean;
  }) => {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const requestMode = sendMode ?? mode;

    if (echoUser) {
      const userText = userEchoText ?? message;
      if (userText.trim()) {
        setItems((prev) => [
          ...prev,
          {
            id: uid(),
            role: "user",
            text: userText,
            time: timeStr,
            message_kind: "user",
            session_id: activeSessionIdNum,
            updated_at_ts: Date.now(),
          },
        ]);
      }
    }

    setLoading(true);
    try {
      const res = await sendChat({
        message,
        mode: requestMode,
        option_id: optionId,
        session_id: activeSession,
      });
      pushAssistantResponse(res, timeStr, { isAutoPlannerStart, optionId });
      if (!isPlannerResponse(res) && (res as any).session_id && (res as any).session_id !== activeSession) {
        setActiveSession((res as any).session_id);
      }
      try {
        const s = await getSessions(1, SESSIONS_PAGE_SIZE);
        setSessions(s.sessions ?? []);
        setSessionsPage(1);
        setSessionsHasNext(!!s.pagination?.has_next);
      } catch {
        // silent
      }
    } catch (e: any) {
      const msg = e?.response?.data?.error ?? e?.message ?? "Gagal terhubung ke AI.";
      setToast({ open: true, kind: "error", msg });
    } finally {
      setLoading(false);
    }
  };

  // --- Handlers ---
  const onSend = async (message: string) => {
    if (mode === "planner" && plannerUiState !== "done" && plannerUiState !== "idle") return;
    await sendMessage({ message, echoUser: true });
  };

  const onSelectPlannerOption = async (optionId: number, label: string) => {
    if (mode !== "planner" || loading) return;
    await sendMessage({
      message: "",
      optionId,
      echoUser: true,
      userEchoText: `Pilih opsi ${optionId}: ${label}`,
    });
  };

  const onToggleMode = async (nextMode: "chat" | "planner") => {
    if (nextMode === mode || loading) return;
    if (mode === "planner" && plannerRunId && plannerUiState !== "done" && plannerUiState !== "idle") {
      try {
        await plannerCancelV3(plannerRunId);
      } catch {
        // no-op
      }
      setPlannerRunId(null);
      setWizardSteps([]);
      setWizardAnswers({});
      setWizardIndex(0);
      setPlannerDocs([]);
      setPlannerRelevanceError(null);
      setPlannerMajorSummary(null);
      setPlannerUiState("idle");
    }
    setMode(nextMode);
  };

  const onUploadClick = () => fileInputRef.current?.click();

  const applyPlannerStartSuccess = (res: PlannerStartResponse) => {
    setPlannerRunId(res.planner_run_id || null);
    setWizardSteps(res.wizard_blueprint?.steps || []);
    setWizardAnswers({});
    setWizardIndex(0);
    setPlannerDocs((res.documents_summary || []).map((d) => ({ id: Number(d.id), title: String(d.title) })));
    setPlannerRelevanceError(null);
    setPlannerMajorSummary(res.profile_hints_summary || null);
    setPlannerUiState("ready");
  };

  const handlePlannerStartError = (res: PlannerStartResponse, fallbackMsg: string) => {
    const errMsg = res.error || fallbackMsg;
    if (res.error_code === "IRRELEVANT_DOCUMENTS") {
      setPlannerRelevanceError(errMsg);
      setPlannerMajorSummary(res.profile_hints_summary || null);
      setPlannerUiState("onboarding");
      return;
    }
    setToast({ open: true, kind: "error", msg: errMsg });
    setPlannerUiState("onboarding");
  };

  const startPlannerFromFiles = async (files: FileList | File[]) => {
    const normalized = Array.isArray(files) ? files : Array.from(files);
    if (!normalized.length) return;
    setPlannerUiState("uploading");
    setPlannerProgressMessage("Memvalidasi dokumen...");
    setPlannerRelevanceError(null);
    setLoading(true);
    try {
      setPlannerProgressMessage("Mengekstrak teks...");
      const res = await plannerStartV3({
        files: normalized,
        sessionId: activeSession,
      });
      if (res.status !== "success" || !res.planner_run_id || !res.wizard_blueprint) {
        handlePlannerStartError(res, "Planner start gagal.");
        return;
      }
      setPlannerProgressMessage("Menyusun sesi planner...");
      applyPlannerStartSuccess(res);
      await refreshDocuments();
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message || "Planner start gagal." });
      setPlannerUiState("onboarding");
    } finally {
      setLoading(false);
    }
  };

  const onPlannerReuseExisting = async () => {
    const ids = documents.filter((d) => d.is_embedded).map((d) => d.id);
    if (!ids.length) {
      setToast({ open: true, kind: "error", msg: "Tidak ada dokumen existing yang siap dipakai." });
      return;
    }
    setPlannerUiState("uploading");
    setPlannerProgressMessage("Mengenali tipe dokumen...");
    setPlannerRelevanceError(null);
    setLoading(true);
    try {
      const res = await plannerStartV3({
        sessionId: activeSession,
        reuseDocIds: ids,
      });
      if (res.status !== "success" || !res.planner_run_id || !res.wizard_blueprint) {
        handlePlannerStartError(res, "Planner start gagal.");
        return;
      }
      applyPlannerStartSuccess(res);
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message || "Planner start gagal." });
      setPlannerUiState("onboarding");
    } finally {
      setLoading(false);
    }
  };

  const onPlannerSelectOption = (value: string) => {
    const step = wizardSteps[wizardIndex];
    if (!step) return;
    setWizardAnswers((prev) => ({ ...prev, [step.step_key]: value }));
  };

  const onPlannerManualChange = (value: string) => {
    const step = wizardSteps[wizardIndex];
    if (!step) return;
    setWizardAnswers((prev) => ({ ...prev, [step.step_key]: value }));
  };

  const onPlannerNext = () => {
    if (wizardIndex >= wizardSteps.length - 1) {
      setPlannerUiState("reviewing");
      return;
    }
    setWizardIndex((v) => Math.min(v + 1, wizardSteps.length - 1));
  };

  const onPlannerBack = () => {
    setWizardIndex((v) => Math.max(v - 1, 0));
  };

  const onPlannerEdit = (stepKey: string) => {
    const idx = wizardSteps.findIndex((s) => s.step_key === stepKey);
    if (idx >= 0) {
      setWizardIndex(idx);
      setPlannerUiState("ready");
    }
  };

  const onPlannerExecute = async () => {
    if (!plannerRunId) return;
    setPlannerUiState("executing");
    setPlannerProgressMessage("Menyusun hasil akhir...");
    setLoading(true);
    try {
      const firstAnswer = Object.values(wizardAnswers)[0] || "akademik umum";
      const summary = `Analisis planner fokus ${firstAnswer}`;
      const userTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setItems((prev) => [
        ...prev,
        {
          id: uid(),
          role: "user",
          text: summary,
          time: userTime,
          message_kind: "user",
          session_id: activeSessionIdNum,
          updated_at_ts: Date.now(),
        },
      ]);
      const res = await plannerExecuteV3({
        planner_run_id: plannerRunId,
        session_id: activeSession,
        answers: wizardAnswers,
        client_summary: summary,
      });
      if (res.status !== "success" || !res.answer) {
        throw new Error(res.error || "Eksekusi planner gagal.");
      }
      setItems((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: res.answer || "",
          time: userTime,
          response_type: "chat",
          message_kind: "assistant_chat",
          sources: res.sources || [],
          session_id: activeSessionIdNum,
          updated_at_ts: Date.now(),
        },
      ]);
      setPlannerUiState("done");
      setPlannerRunId(null);
      setWizardSteps([]);
      setWizardAnswers({});
      setWizardIndex(0);
      setPlannerDocs([]);
      setPlannerRelevanceError(null);
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message || "Eksekusi planner gagal." });
      setPlannerUiState("reviewing");
    } finally {
      setLoading(false);
    }
  };

  const onUploadChange: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    if (mode === "planner" && (plannerUiState === "onboarding" || plannerUiState === "uploading")) {
      await startPlannerFromFiles(files);
    } else {
      await handleFilesUpload(files);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const onDeleteDocument = async (docId: number) => {
    setConfirmDeleteDocId(docId);
  };

  const onCreateSession = async () => {
    try {
      const res = await createSession();
      const newSession = res.session;
      setPlannerStateBySession((prev) => {
        const next = { ...prev };
        delete next[newSession.id];
        return next;
      });
      setPlannerInitializedBySession((prev) => {
        const next = { ...prev };
        delete next[newSession.id];
        return next;
      });
      setPlannerWarningBySession((prev) => {
        const next = { ...prev };
        delete next[newSession.id];
        return next;
      });
      setSessions((prev) => [newSession, ...prev.filter((s) => s.id !== newSession.id)]);
      setActiveSession(newSession.id);
      setItems([
        {
          id: uid(),
          role: "assistant",
          text:
            "Belum ada riwayat chat di sesi ini.\n\n" +
            "Kamu bisa:\n" +
            "- Upload KRS/KHS/Transkrip\n" +
            "- Tanya rekap jadwal per hari\n" +
            "- Cek total SKS\n",
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      setActivePlannerOptionMessageId(null);
      setMobileMenuOpen(false);
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message ?? "Gagal membuat chat." });
    }
  };

  const onSelectSession = async (sessionId: number) => {
    if (sessionId === activeSession) return;
    setActiveSession(sessionId);
    setActivePlannerOptionMessageId(null);
    setLoading(true);
    try {
      const res = await getSessionTimeline(sessionId, 1, 200);
      const timeline = res.timeline ?? [];
      if (timeline.length === 0) {
        setItems([
          {
            id: uid(),
            role: "assistant",
            text:
              "Belum ada riwayat chat di sesi ini.\n\n" +
              "Kamu bisa:\n" +
              "- Upload KRS/KHS/Transkrip\n" +
              "- Tanya rekap jadwal per hari\n" +
              "- Cek total SKS\n",
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          },
        ]);
      } else {
        setItems(timeline.map(mapTimelineItemToChatItem));
      }
      setMobileMenuOpen(false);
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message ?? "Gagal memuat chat." });
    } finally {
      setLoading(false);
    }
  };

  const onDeleteSession = async (sessionId: number) => {
    setConfirmDeleteId(sessionId);
  };

  const onRenameSession = async (sessionId: number, title: string) => {
    try {
      const res = await renameSession(sessionId, title);
      const updated = res.session;
      setSessions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message ?? "Gagal rename chat." });
    }
  };

  const onLoadMoreSessions = async () => {
    if (!sessionsHasNext || sessionsLoadingMore) return;
    setSessionsLoadingMore(true);
    try {
      const nextPage = sessionsPage + 1;
      const res = await getSessions(nextPage, SESSIONS_PAGE_SIZE);
      setSessions((prev) => [...prev, ...(res.sessions ?? [])]);
      setSessionsPage(nextPage);
      setSessionsHasNext(!!res.pagination?.has_next);
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message ?? "Gagal memuat sesi." });
    } finally {
      setSessionsLoadingMore(false);
    }
  };

  const onDragOverChat: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    if (loading || deletingDocId !== null) return;
    setDragActive(true);
  };

  const onDragLeaveChat: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    const related = e.relatedTarget as Node | null;
    if (related && e.currentTarget.contains(related)) return;
    setDragActive(false);
  };

  const onDropChat: React.DragEventHandler<HTMLDivElement> = async (e) => {
    e.preventDefault();
    setDragActive(false);
    if (loading || deletingDocId !== null) return;
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    await handleFilesUpload(files);
  };

  // ✅ padding bawah final: composer + safe area (CSS env) + sedikit ekstra
  // `env(safe-area-inset-bottom)` akan bekerja di iOS Safari.
  const chatPaddingBottom = `calc(${composerH}px + env(safe-area-inset-bottom) + ${safeBottom}px + 32px)`;

  return (
    <div
      className={cn(
        "relative flex h-[100dvh] w-full flex-col overflow-hidden font-sans transition-colors",
        dark
          ? "bg-zinc-950 text-zinc-100 selection:bg-zinc-200 selection:text-zinc-900"
          : "bg-zinc-50 text-zinc-900 selection:bg-black selection:text-white"
      )}
    >
      {/* 1. AMBIENT BACKGROUND */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className={cn("absolute -left-[10%] -top-[10%] h-[50vh] w-[50vw] rounded-full blur-[100px]", dark ? "bg-cyan-500/10" : "bg-blue-100/40")} />
        <div className={cn("absolute -bottom-[10%] -right-[10%] h-[50vh] w-[50vw] rounded-full blur-[100px]", dark ? "bg-violet-500/10" : "bg-indigo-100/40")} />
      </div>

      {/* 2. HEADER */}
      <div className="relative z-10 flex-none">
        <AppHeader
          dark={dark}
          onToggleDark={setDark}
          mode={mode}
          onModeChange={onToggleMode}
          modeDisabled={loading || deletingDocId !== null}
          user={user}
        />
      </div>

      {/* 3. MAIN LAYOUT */}
      <div className="relative flex flex-1 min-h-0 min-w-0 overflow-hidden">
        {deletingDocId !== null && (
          <div className={cn("pointer-events-none absolute inset-0 z-20 backdrop-blur-[1px]", dark ? "bg-zinc-900/35" : "bg-white/40")}>
            <div className={cn("absolute right-4 top-4 rounded-full px-3 py-1 text-[11px] font-semibold shadow-sm", dark ? "bg-zinc-900/90 text-zinc-200" : "bg-white/80 text-zinc-600")}>
              <span className="inline-flex items-center gap-2">
                <span className="size-3 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent" />
                Menghapus dokumen...
              </span>
            </div>
          </div>
        )}
        {/* --- DESKTOP SIDEBAR --- */}
        <div className="hidden h-full md:flex">
          <KnowledgeSidebar
            onUploadClick={onUploadClick}
            onCreateSession={onCreateSession}
            onSelectSession={onSelectSession}
            onDeleteSession={onDeleteSession}
            onRenameSession={onRenameSession}
            onLoadMoreSessions={onLoadMoreSessions}
            onDeleteDocument={onDeleteDocument}
            deletingDocId={deletingDocId}
            disableUpload={deletingDocId !== null}
            sessions={sessions}
            activeSessionId={activeSession}
            hasMoreSessions={sessionsHasNext}
            loadingMoreSessions={sessionsLoadingMore}
            docs={documents.map((d) => ({
              id: d.id,
              title: d.title,
              status: d.is_embedded ? "analyzed" : "processing",
            }))}
            storage={storage}
          />
        </div>

        {/* --- MOBILE SIDEBAR (Drawer) --- */}
        <div
          className={cn(
            "fixed inset-0 z-40 backdrop-blur-sm transition-opacity duration-300 md:hidden",
            dark ? "bg-black/45" : "bg-black/20",
            mobileMenuOpen ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
          onClick={() => setMobileMenuOpen(false)}
        />
        <div
          className={cn(
            "fixed inset-y-0 left-0 z-50 w-[280px] backdrop-blur-2xl transition-transform duration-300 ease-out md:hidden shadow-2xl",
            dark ? "bg-zinc-900/95" : "bg-white/90",
            mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <KnowledgeSidebar
            onUploadClick={onUploadClick}
            onCreateSession={onCreateSession}
            onSelectSession={onSelectSession}
            onDeleteSession={onDeleteSession}
            onRenameSession={onRenameSession}
            onLoadMoreSessions={onLoadMoreSessions}
            onDeleteDocument={onDeleteDocument}
            deletingDocId={deletingDocId}
            disableUpload={deletingDocId !== null}
            sessions={sessions}
            activeSessionId={activeSession}
            hasMoreSessions={sessionsHasNext}
            loadingMoreSessions={sessionsLoadingMore}
            docs={documents.map((d) => ({
              id: d.id,
              title: d.title,
              status: d.is_embedded ? "analyzed" : "processing",
            }))}
            storage={storage}
          />
        </div>

        {/* --- CHAT AREA --- */}
        <main
          data-testid="chat-drop-target"
          className="relative z-0 flex h-full flex-1 min-h-0 min-w-0 flex-col"
          onDragOver={onDragOverChat}
          onDragLeave={onDragLeaveChat}
          onDrop={onDropChat}
        >
          {dragActive && (
            <div
              data-testid="chat-drop-overlay"
              className={cn(
                "pointer-events-none absolute inset-0 z-20 flex items-center justify-center backdrop-blur-[1px]",
                dark ? "bg-zinc-100/10" : "bg-zinc-900/10"
              )}
            >
              <div className={cn("rounded-2xl border-2 border-dashed px-6 py-4 text-center shadow-lg", dark ? "border-zinc-400 bg-zinc-900/90" : "border-zinc-500 bg-white/80")}>
                <div className={cn("text-sm font-semibold", dark ? "text-zinc-100" : "text-zinc-800")}>Drop file di sini</div>
                <div className={cn("mt-1 text-xs", dark ? "text-zinc-300" : "text-zinc-500")}>PDF/XLSX/CSV/MD/TXT</div>
              </div>
            </div>
          )}
          {/* Mobile Menu Trigger */}
          <button
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Buka panel menu"
            className={cn(
              "absolute left-4 top-4 z-30 flex size-10 items-center justify-center rounded-full shadow-sm backdrop-blur-md transition active:scale-95 md:hidden",
              dark
                ? "border border-zinc-700/70 bg-zinc-900/70 text-zinc-200"
                : "border border-black/5 bg-white/60 text-zinc-600"
            )}
          >
            <span className="material-symbols-outlined text-[20px]">menu</span>
          </button>

          {/* CHAT THREAD CONTAINER */}
          <div
            ref={scrollRef}
            id="chat-scroll-container"
            className="chat-scrollbar flex-1 min-h-0 min-w-0 w-full overflow-y-auto overscroll-contain touch-pan-y pt-20 md:pt-4"
            style={{
              paddingBottom: chatPaddingBottom,
              scrollbarGutter: "stable",
              scrollbarWidth: "thin",
              scrollbarColor: dark ? "rgba(212,212,216,0.42) transparent" : "rgba(63,63,70,0.35) transparent",
            }}
          >
            <ChatThread
              items={itemsWithPlannerPanel}
              mode={mode}
              activePlannerOptionMessageId={activePlannerOptionMessageId}
              optionsLocked={loading || deletingDocId !== null}
              onSelectPlannerOption={onSelectPlannerOption}
              plannerPanelProps={{
                state: plannerUiState,
                hasEmbeddedDocs: documents.some((d) => d.is_embedded),
                relevanceError: plannerRelevanceError,
                majorSummary: plannerMajorSummary,
                progressMessage: plannerProgressMessage,
                wizardSteps,
                wizardIndex,
                wizardAnswers,
                plannerDocs,
                loading,
                deletingDocId,
                plannerWarning,
                onUploadNew: onUploadClick,
                onReuseExisting: onPlannerReuseExisting,
                onSelectOption: onPlannerSelectOption,
                onChangeManual: onPlannerManualChange,
                onNext: onPlannerNext,
                onBack: onPlannerBack,
                onEdit: onPlannerEdit,
                onExecute: onPlannerExecute,
              }}
            />
          </div>

          {/* Composer */}
          <ChatComposer
            onSend={onSend}
            onUploadClick={onUploadClick}
            loading={
              loading ||
              deletingDocId !== null ||
              (mode === "planner" && plannerUiState !== "done" && plannerUiState !== "idle")
            }
            deletingDoc={deletingDocId !== null}
            docs={documents.map((d) => ({ id: d.id, title: d.title }))}
          />
        </main>
      </div>

      {/* Hidden File Input */}
      <input
        data-testid="upload-input"
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={onUploadChange}
        accept=".pdf,.xlsx,.xls,.csv,.md,.txt"
      />

      {/* Toast */}
      <Toast
        open={toast.open}
        kind={toast.kind}
        message={toast.msg}
        onClose={() => setToast((p) => ({ ...p, open: false }))}
      />

      {/* Confirm Delete Modal */}
      {confirmDeleteId !== null && (
        <div data-testid="confirm-delete-session" className="fixed inset-0 z-[1000] flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm dark:bg-black/50"
            onClick={() => setConfirmDeleteId(null)}
          />
          <div className="relative z-[1001] w-[92%] max-w-[420px] rounded-2xl border border-white/40 bg-white/80 p-5 shadow-2xl backdrop-blur-xl dark:border-zinc-700/70 dark:bg-zinc-900/90">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-950/35 dark:text-red-300">
                <span className="material-symbols-outlined text-[20px]">delete</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Hapus chat ini?</div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">Riwayat chat akan dihapus permanen.</div>
              </div>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDeleteId(null)}
                className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                Batal
              </button>
              <button
                data-testid="confirm-delete-session-btn"
                type="button"
                onClick={async () => {
                  const id = confirmDeleteId;
                  if (id == null) return;
                  try {
                    await deleteSession(id);
                    const next = sessions.filter((s) => s.id !== id);
                    setSessions(next);
                    setPlannerStateBySession((prev) => {
                      const cloned = { ...prev };
                      delete cloned[id];
                      return cloned;
                    });
                    setPlannerInitializedBySession((prev) => {
                      const cloned = { ...prev };
                      delete cloned[id];
                      return cloned;
                    });
                    setPlannerWarningBySession((prev) => {
                      const cloned = { ...prev };
                      delete cloned[id];
                      return cloned;
                    });
                    if (activeSession === id) {
                      const fallback = next[0]?.id;
                      if (fallback) {
                        await onSelectSession(fallback);
                      } else {
                        setActiveSession(undefined);
                        setActivePlannerOptionMessageId(null);
                        setItems([
                          {
                            id: uid(),
                            role: "assistant",
                            text:
                              "Belum ada riwayat chat di sesi ini.\n\n" +
                              "Kamu bisa:\n" +
                              "- Upload KRS/KHS/Transkrip\n" +
                              "- Tanya rekap jadwal per hari\n" +
                              "- Cek total SKS\n",
                            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                          },
                        ]);
                      }
                    }
                  } catch (e: any) {
                    setToast({ open: true, kind: "error", msg: e?.message ?? "Gagal menghapus chat." });
                  } finally {
                    setConfirmDeleteId(null);
                  }
                }}
                className="rounded-xl bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-700"
              >
                Hapus
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Delete Document Modal */}
      {confirmDeleteDocId !== null && (
        <div data-testid="confirm-delete-doc" className="fixed inset-0 z-[1000] flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm dark:bg-black/50"
            onClick={() => setConfirmDeleteDocId(null)}
          />
          <div className="relative z-[1001] w-[92%] max-w-[420px] rounded-2xl border border-white/40 bg-white/80 p-5 shadow-2xl backdrop-blur-xl dark:border-zinc-700/70 dark:bg-zinc-900/90">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-950/35 dark:text-red-300">
                <span className="material-symbols-outlined text-[20px]">delete</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Hapus dokumen ini?</div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  File dan embedding di vector DB akan dihapus permanen.
                </div>
              </div>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDeleteDocId(null)}
                className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                Batal
              </button>
              <button
                data-testid="confirm-delete-doc-btn"
                type="button"
                onClick={async () => {
                  const id = confirmDeleteDocId;
                  if (id == null) return;
                  setDeletingDocId(id);
                  setLoading(true);
                  try {
                    await deleteDocument(id);
                    await refreshDocuments();
                    setToast({ open: true, kind: "success", msg: "Dokumen berhasil dihapus." });
                  } catch (e: any) {
                    const status = e?.response?.status;
                    const serverMsg = e?.response?.data?.msg;
                    if (status === 404) {
                      setToast({ open: true, kind: "error", msg: "Dokumen tidak ditemukan di server." });
                    } else {
                      setToast({ open: true, kind: "error", msg: serverMsg ?? e?.message ?? "Gagal menghapus dokumen." });
                    }
                  } finally {
                    setLoading(false);
                    setDeletingDocId(null);
                    setConfirmDeleteDocId(null);
                  }
                }}
                disabled={deletingDocId === confirmDeleteDocId}
                className={cn(
                  "rounded-xl bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-700",
                  deletingDocId === confirmDeleteDocId && "opacity-70 cursor-not-allowed"
                )}
              >
                {deletingDocId === confirmDeleteDocId ? (
                  <span className="inline-flex items-center gap-2">
                    <span className="size-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                    Menghapus...
                  </span>
                ) : (
                  "Hapus"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
