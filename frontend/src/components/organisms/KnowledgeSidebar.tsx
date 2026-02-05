import React from "react";
import DocumentItem from "@/components/molecules/DocumentItem";
import type { DocStatus } from "@/components/molecules/DocumentItem";
import ProgressBar from "@/components/atoms/ProgressBar";
import { cn } from "@/lib/utils";

type StorageInfo = {
  used_bytes: number;
  quota_bytes: number;
  used_pct: number;
  used_human?: string;
  quota_human?: string;
};

export default function KnowledgeSidebar({
  onUploadClick,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  onLoadMoreSessions,
  onDeleteDocument,
  deletingDocId,
  disableUpload = false,
  docs,
  sessions = [],
  activeSessionId,
  hasMoreSessions = false,
  loadingMoreSessions = false,
  storage,
  storagePct = 0,
  className,
}: {
  onUploadClick: () => void;
  onCreateSession: () => void;
  onSelectSession: (sessionId: number) => void;
  onDeleteSession: (sessionId: number) => void;
  onRenameSession: (sessionId: number, title: string) => void;
  onLoadMoreSessions: () => void;
  onDeleteDocument: (docId: number) => void;
  deletingDocId?: number | null;
  disableUpload?: boolean;
  docs: Array<{ id: number; title: string; status: DocStatus }>;
  sessions?: Array<{ id: number; title: string; updated_at: string }>;
  activeSessionId?: number;
  hasMoreSessions?: boolean;
  loadingMoreSessions?: boolean;
  storage?: StorageInfo;
  storagePct?: number;
  className?: string;
}) {
  const [editingId, setEditingId] = React.useState<number | null>(null);
  const [editingTitle, setEditingTitle] = React.useState("");
  const analyzedCount = docs.filter((d) => d.status === "analyzed").length;
  const processingCount = docs.filter((d) => d.status === "processing").length;

  const usedPct = storage?.used_pct ?? storagePct;

  return (
    <aside
      data-testid="knowledge-sidebar"
      className={cn(
        "relative flex w-full flex-col h-full border-r border-zinc-200/50 bg-white/50 backdrop-blur-3xl",
        className
      )}
    >
      {/* --- Header Section --- */}
      <div className="flex flex-col gap-6 p-6 pb-2">
        {/* Title & Stats */}
        <div>
          <h2 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-zinc-900/40">
            <span className="material-symbols-outlined text-[16px]">
              library_books
            </span>
            Knowledge Base
          </h2>
          <div className="mt-4 flex items-baseline gap-1">
            <span className="text-3xl font-light text-zinc-900">
              {docs.length}
            </span>
            <span className="text-sm font-medium text-zinc-400">Dokumen</span>
          </div>

          {(processingCount > 0 || analyzedCount > 0) && (
            <div className="mt-3 flex gap-3">
              {processingCount > 0 && (
                <div className="flex items-center gap-2 rounded-full border border-amber-100/50 bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700">
                  <span className="relative flex size-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"></span>
                    <span className="relative inline-flex size-1.5 rounded-full bg-amber-500"></span>
                  </span>
                  Memproses {processingCount}
                </div>
              )}
              {analyzedCount > 0 && (
                <div className="flex items-center gap-2 rounded-full border border-emerald-100/50 bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  Siap {analyzedCount}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Upload Button */}
        <button
          onClick={onUploadClick}
          disabled={disableUpload}
          className={cn(
            "group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-zinc-900 py-3 text-white shadow-lg shadow-zinc-200 transition-all hover:bg-zinc-800 hover:shadow-xl active:scale-[0.98]",
            disableUpload && "cursor-not-allowed opacity-60"
          )}
        >
          <span className="material-symbols-outlined text-[20px] transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5">
            cloud_upload
          </span>
          <span className="text-[13px] font-medium tracking-wide">
            Unggah Dokumen
          </span>
        </button>
      </div>

      {/* --- Chat Sessions --- */}
      <div className="px-4 pb-2">
        <div className="mb-2 flex items-center justify-between px-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
            Chat
          </div>
          <button
            data-testid="session-create"
            type="button"
            onClick={onCreateSession}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold text-zinc-600 hover:bg-zinc-100"
          >
            <span className="material-symbols-outlined text-[14px]">add</span>
            Chat Baru
          </button>
        </div>

        <div className="max-h-[180px] overflow-y-auto scrollbar-hide">
          {sessions.length > 0 ? (
            <div className="space-y-1">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className={cn(
                    "group flex items-center justify-between gap-2 rounded-xl px-3 py-2 text-[12px] transition",
                    activeSessionId === s.id
                      ? "bg-zinc-900 text-white"
                      : "bg-white/60 text-zinc-700 hover:bg-white"
                  )}
                >
                  {editingId === s.id ? (
                    <div className="flex flex-1 items-center gap-2">
                      <input
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        className={cn(
                          "flex-1 rounded-md px-2 py-1 text-[12px]",
                          activeSessionId === s.id
                            ? "border border-white/20 bg-white/10 text-white placeholder:text-white/70"
                            : "border border-zinc-200 bg-white text-zinc-800 placeholder:text-zinc-400"
                        )}
                        placeholder="Judul chat"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            onRenameSession(s.id, editingTitle);
                            setEditingId(null);
                          }
                          if (e.key === "Escape") {
                            setEditingId(null);
                          }
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          onRenameSession(s.id, editingTitle);
                          setEditingId(null);
                        }}
                        className="rounded-md p-1 text-white/80 hover:text-white"
                        title="Simpan"
                      >
                        <span className="material-symbols-outlined text-[16px]">check</span>
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        data-testid={`session-item-${s.id}`}
                        type="button"
                        onClick={() => onSelectSession(s.id)}
                        className="flex-1 truncate text-left"
                        title={s.title}
                      >
                        {s.title || "Chat Baru"}
                      </button>
                      <div className="flex items-center gap-1">
                        <button
                          data-testid={`session-rename-${s.id}`}
                          type="button"
                          onClick={() => {
                            setEditingId(s.id);
                            setEditingTitle(s.title || "Chat Baru");
                          }}
                          className={cn(
                            "rounded-md p-1 transition",
                            activeSessionId === s.id
                              ? "text-white/80 hover:text-white"
                              : "text-zinc-400 hover:text-zinc-800"
                          )}
                          title="Rename chat"
                        >
                          <span className="material-symbols-outlined text-[16px]">edit</span>
                        </button>
                        <button
                          data-testid={`session-delete-${s.id}`}
                          type="button"
                          onClick={() => onDeleteSession(s.id)}
                          className={cn(
                            "rounded-md p-1 transition",
                            activeSessionId === s.id
                              ? "text-white/80 hover:text-white"
                              : "text-zinc-400 hover:text-red-600"
                          )}
                          title="Hapus chat"
                        >
                          <span className="material-symbols-outlined text-[16px]">delete</span>
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
              {hasMoreSessions && (
                <button
                  data-testid="sessions-load-more"
                  type="button"
                  onClick={onLoadMoreSessions}
                  disabled={loadingMoreSessions}
                  className="mt-2 w-full rounded-xl border border-zinc-200 bg-white/70 px-3 py-2 text-[11px] font-semibold text-zinc-600 hover:bg-white disabled:opacity-60"
                >
                  {loadingMoreSessions ? "Memuat..." : "Muat lagi"}
                </button>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50/50 p-4 text-center text-[11px] text-zinc-500">
              Belum ada chat. Klik “Chat Baru”.
            </div>
          )}
        </div>
      </div>

      {/* --- Scrollable List --- */}
      <div
        data-testid="doc-list"
        className="scrollbar-hide flex-1 overflow-y-auto px-4 py-2"
      >
        {docs.length > 0 ? (
          <div className="space-y-1">
            <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              Daftar Berkas
            </div>
            {docs.map((d, idx) => (
              <div key={d.id ?? idx} className="relative">
                <DocumentItem
                  testId={d.id ? `doc-${d.id}` : undefined}
                  title={d.title}
                  status={d.status}
                  onDelete={() => onDeleteDocument(d.id)}
                  isDeleting={deletingDocId === d.id}
                  disableDelete={deletingDocId !== null && deletingDocId !== d.id}
                />
                {deletingDocId === d.id && (
                  <div className="pointer-events-none absolute inset-0 rounded-2xl border border-zinc-200 bg-white/60 backdrop-blur-[2px]">
                    <div className="absolute inset-y-0 left-0 w-[40%] animate-pulse bg-gradient-to-r from-transparent via-white/70 to-transparent" />
                    <div className="absolute right-3 top-3 rounded-full bg-white/80 px-2.5 py-1 text-[10px] font-semibold text-zinc-600 shadow-sm">
                      Menghapus...
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-zinc-200 bg-zinc-50/50 p-6 text-center">
            <div className="mb-3 rounded-full bg-zinc-100 p-3">
              <span className="material-symbols-outlined text-[24px] text-zinc-300">
                folder_open
              </span>
            </div>
            <h3 className="text-sm font-medium text-zinc-900">
              Belum ada data
            </h3>
            <p className="mt-1 max-w-[180px] text-xs leading-relaxed text-zinc-500">
              Unggah file PDF/Excel akademikmu untuk memulai analisis AI.
            </p>
          </div>
        )}
      </div>

      {/* --- Footer Storage Info --- */}
      <div className="border-t border-zinc-100 bg-white/40 p-5 backdrop-blur-md">
        <div className="mb-3 flex items-end justify-between">
          <div className="flex flex-col">
            <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Penyimpanan
            </span>
          </div>
        </div>

        <ProgressBar
          value={usedPct}
          usedBytes={storage?.used_bytes}
          quotaBytes={storage?.quota_bytes}
        />

        <div className="mt-3 flex items-center gap-1.5 text-[10px] text-zinc-400">
          <span className="material-symbols-outlined text-[12px]">lock</span>
          <span>Enkripsi End-to-End • Privat</span>
        </div>
      </div>
    </aside>
  );
}
