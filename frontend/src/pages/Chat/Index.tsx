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
import { sendChat, uploadDocuments, getDocuments, getSessions, createSession, deleteSession, getSessionHistory, renameSession, deleteDocument } from "@/lib/api";
import type { DocumentDto, DocumentsResponse, ChatSessionDto } from "@/lib/api";
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

export default function Index() {
  const SESSIONS_PAGE_SIZE = 20;
  const { props } = usePage<PageProps>();
  const { user, initialHistory, documents: initialDocs, storage: initialStorage, sessions: initialSessions, activeSessionId } = props;

  // State
  const [dark, setDark] = useState(false);
  const [documents, setDocuments] = useState<DocumentDto[]>(initialDocs ?? []);
  const [storage, setStorage] = useState<StorageInfo | undefined>(initialStorage);
  const [sessions, setSessions] = useState<ChatSessionDto[]>(initialSessions ?? []);
  const [activeSession, setActiveSession] = useState<number | undefined>(activeSessionId);
  const [sessionsPage, setSessionsPage] = useState(1);
  const [sessionsHasNext, setSessionsHasNext] = useState(false);
  const [sessionsLoadingMore, setSessionsLoadingMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [confirmDeleteDocId, setConfirmDeleteDocId] = useState<number | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<number | null>(null);

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
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
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

  // ✅ Inertia reuse fix: sinkronkan ulang items saat user/history berubah
  useEffect(() => {
    setItems(initialItems);
  }, [user.id, initialItems]);

  // ✅ auto-scroll lebih “nempel bawah” (pakai scrollHeight besar)
  useEffect(() => {
    const t = setTimeout(() => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight + 9999, behavior: "smooth" });
    }, 120);
    return () => clearTimeout(t);
  }, [items, composerH]);

  // --- Handlers ---
  const onSend = async (message: string) => {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    setItems((prev) => [
      ...prev,
      { id: uid(), role: "user", text: message, time: timeStr },
    ]);

    setLoading(true);
    try {
      const res = await sendChat(message, activeSession);
      const aiText = res.answer ?? res.error ?? "Maaf, tidak ada jawaban.";
      setItems((prev) => [
        ...prev,
        { id: uid(), role: "assistant", text: aiText, time: timeStr },
      ]);
      if (res.session_id && res.session_id !== activeSession) {
        setActiveSession(res.session_id);
      }
      // refresh session list to update title/updated_at
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

  const onUploadClick = () => fileInputRef.current?.click();

  const onUploadChange: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setLoading(true);
    setMobileMenuOpen(false);

    try {
      const res = await uploadDocuments(files);
      setToast({ open: true, kind: res.status === "success" ? "success" : "error", msg: res.msg });
      await refreshDocuments();
    } catch (err: any) {
      const msg = err?.response?.data?.msg ?? err?.message ?? "Upload gagal.";
      setToast({ open: true, kind: "error", msg });
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const onDeleteDocument = async (docId: number) => {
    setConfirmDeleteDocId(docId);
  };

  const onCreateSession = async () => {
    try {
      const res = await createSession();
      const newSession = res.session;
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
      setMobileMenuOpen(false);
    } catch (e: any) {
      setToast({ open: true, kind: "error", msg: e?.message ?? "Gagal membuat chat." });
    }
  };

  const onSelectSession = async (sessionId: number) => {
    if (sessionId === activeSession) return;
    setActiveSession(sessionId);
    setLoading(true);
    try {
      const res = await getSessionHistory(sessionId);
      const hist = res.history ?? [];
      if (hist.length === 0) {
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
        const arr: ChatItem[] = [];
        for (const h of hist) {
          arr.push({ id: uid(), role: "user", text: h.question, time: h.time });
          arr.push({ id: uid(), role: "assistant", text: h.answer, time: h.time });
        }
        setItems(arr);
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

  // ✅ padding bawah final: composer + safe area (CSS env) + sedikit ekstra
  // `env(safe-area-inset-bottom)` akan bekerja di iOS Safari.
  const chatPaddingBottom = `calc(${composerH}px + env(safe-area-inset-bottom) + ${safeBottom}px + 12px)`;

  return (
    <div className="relative flex h-[100dvh] w-full flex-col overflow-hidden bg-zinc-50 font-sans text-zinc-900 selection:bg-black selection:text-white">
      {/* 1. AMBIENT BACKGROUND */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -left-[10%] -top-[10%] h-[50vh] w-[50vw] rounded-full bg-blue-100/40 blur-[100px]" />
        <div className="absolute -bottom-[10%] -right-[10%] h-[50vh] w-[50vw] rounded-full bg-indigo-100/40 blur-[100px]" />
      </div>

      {/* 2. HEADER */}
      <div className="relative z-10 flex-none">
        <AppHeader dark={dark} onToggleDark={setDark} user={user} />
      </div>

      {/* 3. MAIN LAYOUT */}
      <div className="relative flex flex-1 min-h-0 min-w-0 overflow-hidden">
        {deletingDocId !== null && (
          <div className="pointer-events-none absolute inset-0 z-20 bg-white/40 backdrop-blur-[1px]">
            <div className="absolute right-4 top-4 rounded-full bg-white/80 px-3 py-1 text-[11px] font-semibold text-zinc-600 shadow-sm">
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
            "fixed inset-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity duration-300 md:hidden",
            mobileMenuOpen ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
          onClick={() => setMobileMenuOpen(false)}
        />
        <div
          className={cn(
            "fixed inset-y-0 left-0 z-50 w-[280px] bg-white/90 backdrop-blur-2xl transition-transform duration-300 ease-out md:hidden shadow-2xl",
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
        <main className="relative z-0 flex h-full flex-1 min-h-0 min-w-0 flex-col">
          {/* Mobile Menu Trigger */}
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="absolute left-4 top-4 z-30 flex size-10 items-center justify-center rounded-full border border-black/5 bg-white/60 text-zinc-600 shadow-sm backdrop-blur-md transition active:scale-95 md:hidden"
          >
            <span className="material-symbols-outlined text-[20px]">menu</span>
          </button>

          {/* CHAT THREAD CONTAINER */}
          <div
            ref={scrollRef}
            className="flex-1 min-h-0 min-w-0 w-full overflow-y-auto overscroll-contain touch-pan-y scrollbar-hide pt-20 md:pt-4"
            style={{ paddingBottom: chatPaddingBottom }}
          >
            <ChatThread items={items} />
          </div>

          {/* Composer */}
          <ChatComposer
            onSend={onSend}
            onUploadClick={onUploadClick}
            loading={loading || deletingDocId !== null}
            deletingDoc={deletingDocId !== null}
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
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={() => setConfirmDeleteId(null)}
          />
          <div className="relative z-[1001] w-[92%] max-w-[420px] rounded-2xl border border-white/40 bg-white/80 p-5 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600">
                <span className="material-symbols-outlined text-[20px]">delete</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-zinc-900">Hapus chat ini?</div>
                <div className="text-xs text-zinc-500">Riwayat chat akan dihapus permanen.</div>
              </div>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDeleteId(null)}
                className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-600 hover:bg-zinc-50"
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
                    if (activeSession === id) {
                      const fallback = next[0]?.id;
                      if (fallback) {
                        await onSelectSession(fallback);
                      } else {
                        setActiveSession(undefined);
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
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={() => setConfirmDeleteDocId(null)}
          />
          <div className="relative z-[1001] w-[92%] max-w-[420px] rounded-2xl border border-white/40 bg-white/80 p-5 shadow-2xl backdrop-blur-xl">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600">
                <span className="material-symbols-outlined text-[20px]">delete</span>
              </div>
              <div>
                <div className="text-sm font-semibold text-zinc-900">Hapus dokumen ini?</div>
                <div className="text-xs text-zinc-500">
                  File dan embedding di vector DB akan dihapus permanen.
                </div>
              </div>
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDeleteDocId(null)}
                className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-xs font-semibold text-zinc-600 hover:bg-zinc-50"
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
