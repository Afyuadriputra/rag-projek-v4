import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { cn } from "@/lib/utils";

export type ChatRole = "assistant" | "user";

export type ChatSource = {
  source: string;
  snippet: string;
};

export type PlannerOptionItem = {
  id: number;
  label: string;
  value: string;
  detected?: boolean;
  confidence?: number;
};

export type ChatItem = {
  id: string;
  role: ChatRole;
  text: string;
  time?: string; // "HH:MM"
  sources?: ChatSource[]; // ✅ NEW: rujukan dari backend (optional)
  response_type?: "chat" | "planner_step" | "planner_output" | "planner_generate";
  planner_step?: string;
  planner_options?: PlannerOptionItem[];
  allow_custom?: boolean;
  session_state?: Record<string, unknown>;
  planner_warning?: string | null;
  profile_hints?: Record<string, unknown>;
  message_kind?: "user" | "assistant_chat" | "assistant_planner_step" | "system_mode" | "planner_panel";
  planner_panel_state?: "idle" | "onboarding" | "uploading" | "ready" | "reviewing" | "executing" | "done";
  planner_panel_payload?: Record<string, unknown>;
  session_id?: number;
  updated_at_ts?: number;
  planner_meta?: Record<string, unknown>;
};

function normalizeText(text: string) {
  return (text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\\n/g, "\n")
    .trim();
}

/**
 * Normalize Markdown agar tetap rapi meskipun model berbeda.
 * - Rapikan spacing heading & list
 * - Pastikan ada newline sebelum heading
 * - Kurangi “tabel tab-separated” yang sering keluar dari model (tetap tampil rapi via fallback <pre>)
 */
function normalizeMarkdown(md: string) {
  let s = normalizeText(md);

  // Normalisasi newline berlebihan
  s = s.replace(/\n{3,}/g, "\n\n");

  // Pastikan heading selalu diawali newline (biar tidak nempel ke paragraf)
  s = s.replace(/([^\n])\n(##\s+)/g, "$1\n\n$2");
  s = s.replace(/([^\n])\n(###\s+)/g, "$1\n\n$2");

  // Normalize bullet list: kadang model pakai "•" / "-" tanpa spasi
  s = s.replace(/^\s*•\s?/gm, "- ");
  s = s.replace(/^\s*-\s{0,1}(?=\S)/gm, "- ");

  // Normalize "Opsi cepat" chips: [..] tetap satu baris per item (lebih enak dibaca)
  // Jika model menulis: "- [A] [B]" -> pecah jadi baris
  s = s.replace(/-\s*(\[[^\]]+\])\s+(\[[^\]]+\])/g, "- $1\n- $2");

  return s;
}

function toPlainString(children: any): string {
  if (children == null) return "";
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(toPlainString).join("");
  return String(children);
}

function looksLikeTabularPlaintext(text: string) {
  // Deteksi tabel yang dikirim model pakai TAB atau banyak spasi (bukan markdown table)
  // Contoh: "Semester\tKode\tMata Kuliah\tSKS"
  const lines = (text || "").split("\n").filter(Boolean);
  if (lines.length < 2) return false;

  const tabLines = lines.filter((l) => l.includes("\t")).length;
  if (tabLines >= Math.min(3, lines.length)) return true;

  // Heuristik spasi banyak: minimal 2 kolom dengan gap spasi >= 2, beberapa baris
  const spaced = lines.filter((l) => /\S+\s{2,}\S+/.test(l)).length;
  return spaced >= Math.min(3, lines.length);
}

// --- 1. Custom Animation Styles (Inject CSS) ---
const animationStyles = `
  @keyframes slideUpFade {
    0% { opacity: 0; transform: translateY(8px) scale(0.98); }
    100% { opacity: 1; transform: translateY(0) scale(1); }
  }
  @keyframes pulse-subtle {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0,0,0,0); }
    50% { box-shadow: 0 0 0 2px rgba(0,0,0,0.05); }
  }
  @keyframes bounce-slow {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-3px); }
  }
  .animate-entry {
    animation: slideUpFade 0.4s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
  }
  .animate-pulse-subtle {
    animation: pulse-subtle 3s infinite ease-in-out;
  }
  .dot-1 { animation: bounce-slow 1s infinite 0ms; }
  .dot-2 { animation: bounce-slow 1s infinite 200ms; }
  .dot-3 { animation: bounce-slow 1s infinite 400ms; }
`;

export default function ChatBubble({
  item,
  onSelectOption,
  optionsEnabled = false,
  showPlannerOptions = false,
}: {
  item: ChatItem;
  onSelectOption?: (optionId: number, label: string) => void;
  optionsEnabled?: boolean;
  showPlannerOptions?: boolean;
}) {
  const isUser = item.role === "user";
  const isSystemMode = item.message_kind === "system_mode";
  const isPlannerStep = item.message_kind === "assistant_planner_step";
  const plannerEventType = String(item.planner_meta?.event_type ?? "");
  const isPlannerMilestone =
    isSystemMode &&
    ["start_auto", "option_select", "user_input", "save"].includes(plannerEventType);
  const raw = normalizeText(item.text);

  // Untuk AI: normalize markdown agar stabil lintas model
  const content = isUser ? raw : normalizeMarkdown(raw);

  // ✅ NEW: rapikan sources (unik per judul) tanpa mengubah tampilan utama
  const sources = useMemo(() => {
    const r = item.sources ?? [];
    const seen = new Set<string>();
    const uniq: ChatSource[] = [];
    for (const s of r) {
      const key = s?.source ?? "unknown";
      if (seen.has(key)) continue;
      seen.add(key);
      uniq.push({
        source: key,
        snippet: (s?.snippet ?? "").trim(),
      });
    }
    return uniq;
  }, [item.sources]);

  // ✅ NEW: toggle panel rujukan (default tertutup)
  const [showSources, setShowSources] = useState(false);
  const plannerOptions = item.planner_options ?? [];
  const plannerStep = String(item.planner_meta?.step ?? item.planner_step ?? "");
  const questionCandidates = useMemo(() => {
    const hints = item.profile_hints as Record<string, unknown> | undefined;
    const rawCandidates = hints?.question_candidates;
    if (!Array.isArray(rawCandidates)) return [];
    return rawCandidates
      .filter((q): q is Record<string, unknown> => !!q && typeof q === "object")
      .map((q) => ({
        step: String(q.step ?? "").trim(),
      }))
      .filter((q) => q.step.length > 0);
  }, [item.profile_hints]);
  const isQuestionDetectedFromDocument =
    !isUser &&
    item.response_type === "planner_step" &&
    plannerStep.length > 0 &&
    questionCandidates.some((q) => q.step === plannerStep);
  const canShowPlannerOptions =
    !isUser && showPlannerOptions && plannerOptions.length > 0;

  // Fallback: kalau model kirim "tabel plaintext" (tab/spaces) -> tampilkan pre-block rapi
  const showPlainTableFallback = !isUser && looksLikeTabularPlaintext(content) && !content.includes("|");

  return (
    <>
      <style>{animationStyles}</style>

      <div
        className={cn(
          "animate-entry flex w-full min-w-0 gap-2 md:gap-4 opacity-0",
          "items-start",
          isUser ? "flex-row-reverse" : "flex-row"
        )}
      >
        {/* --- AVATAR --- */}
        <div className="flex-shrink-0 mt-1">
          {isUser ? (
            <div className="flex size-8 md:size-10 items-center justify-center rounded-full border border-zinc-200 bg-white shadow-sm dark:border-zinc-700 dark:bg-zinc-800">
              <span className="material-symbols-outlined text-[18px] text-zinc-700 dark:text-zinc-200">
                person
              </span>
            </div>
          ) : (
            <div className="animate-pulse-subtle flex size-8 md:size-10 items-center justify-center rounded-xl bg-zinc-900 shadow-md shadow-zinc-900/10">
              <span className="material-symbols-outlined text-[18px] text-white">
                smart_toy
              </span>
            </div>
          )}
        </div>

        {/* --- CONTENT WRAPPER --- */}
        <div
          className={cn(
            "flex min-w-0 flex-col",
            "max-w-[90%] md:max-w-[75%] lg:max-w-[65%]",
            isUser ? "items-end" : "items-start"
          )}
        >
          {/* Meta Info */}
          <div
            className={cn(
              "mb-1.5 flex items-center gap-2 opacity-80 select-none",
              isUser ? "flex-row-reverse" : "flex-row"
            )}
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 md:text-[11px] dark:text-zinc-400">
              {isUser ? "Mahasiswa" : isSystemMode ? "Planner Aktif" : "Academic AI"}
            </span>
            <span className="text-[10px] text-zinc-400 md:text-[11px] dark:text-zinc-500">
              {item.time}
            </span>
          </div>

          {/* --- BUBBLE BOX --- */}
          <div
            className={cn(
              "relative max-w-full min-w-0 overflow-hidden shadow-sm transition-all duration-300",
              "px-4 py-3 md:px-6 md:py-4",
              isUser
                ? "rounded-2xl rounded-tr-sm bg-zinc-900 text-zinc-50 hover:bg-black"
                : isSystemMode
                  ? "rounded-2xl rounded-tl-sm border border-blue-200 bg-blue-50/70 text-zinc-800 dark:border-blue-900/60 dark:bg-blue-950/35 dark:text-zinc-100"
                  : "rounded-2xl rounded-tl-sm border border-zinc-200 bg-white text-zinc-800 hover:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:border-zinc-500"
            )}
          >
            {isUser ? (
              <div className="whitespace-pre-wrap break-words text-[14px] font-normal leading-relaxed md:text-[15px]">
                {content}
              </div>
            ) : (
              <div className="prose prose-zinc max-w-none break-words text-[14px] leading-relaxed md:text-[15px] dark:prose-invert">
                {showPlainTableFallback ? (
                  // Fallback kalau model kasih tabel pakai TAB/spasi (bukan markdown table)
                  <div className="my-2 overflow-hidden rounded-xl border border-zinc-200 shadow-sm dark:border-zinc-700">
                    <div className="overflow-x-auto bg-zinc-50 dark:bg-zinc-900">
                      <pre className="m-0 whitespace-pre p-4 text-[12px] leading-relaxed text-zinc-800 dark:text-zinc-100">
                        {content}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSanitize]}
                    components={{
                      h1: ({ children }) => (
                        <h1 className="mb-3 mt-1 text-lg font-bold text-zinc-900 dark:text-zinc-100">
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className="mb-2 mt-4 text-base font-bold text-zinc-900 dark:text-zinc-100">
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className="mb-2 mt-3 text-sm font-bold text-zinc-900 dark:text-zinc-100">
                          {children}
                        </h3>
                      ),
                      p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                      ul: ({ children }) => (
                        <ul className="mb-3 list-disc space-y-1 pl-4 marker:text-zinc-400 dark:marker:text-zinc-500 md:pl-5">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="mb-3 list-decimal space-y-1 pl-4 marker:text-zinc-400 dark:marker:text-zinc-500 md:pl-5">
                          {children}
                        </ol>
                      ),
                      li: ({ children }) => <li className="pl-1">{children}</li>,
                      strong: ({ children }) => (
                        <strong className="font-semibold text-zinc-900 dark:text-zinc-100">{children}</strong>
                      ),
                      em: ({ children }) => <em className="italic text-zinc-600 dark:text-zinc-300">{children}</em>,
                      blockquote: ({ children }) => (
                        <blockquote className="my-4 border-l-4 border-zinc-300 bg-zinc-50 px-4 py-2 italic text-zinc-600 dark:border-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-300">
                          {children}
                        </blockquote>
                      ),
                      hr: () => <hr className="my-6 border-zinc-200 dark:border-zinc-700" />,
                      code: ({ inline, className, children }: any) => {
                        const text = toPlainString(children);

                        if (inline) {
                          return (
                            <code className="rounded border border-zinc-200 bg-zinc-100 px-1.5 py-0.5 text-[13px] font-medium text-pink-600 dark:border-zinc-700 dark:bg-zinc-800 dark:text-pink-300">
                              {text}
                            </code>
                          );
                        }

                        return (
                          <div className="group relative my-4 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-md dark:border-zinc-700">
                            <div className="flex items-center justify-between bg-zinc-800/50 px-3 py-1.5 text-xs text-zinc-400 dark:text-zinc-500">
                              <span>Snippet</span>
                            </div>
                            <div className="overflow-x-auto p-4">
                              <code className={cn("text-xs text-zinc-100 md:text-sm font-mono", className)}>
                                {text}
                              </code>
                            </div>
                          </div>
                        );
                      },
                      table: ({ children }) => (
                        <div className="my-4 overflow-hidden rounded-xl border border-zinc-200 shadow-sm dark:border-zinc-700">
                          <div className="overflow-x-auto">
                            <table className="w-full min-w-[300px] border-collapse text-left text-sm">
                              {children}
                            </table>
                          </div>
                        </div>
                      ),
                      thead: ({ children }) => <thead className="bg-zinc-50 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">{children}</thead>,
                      tbody: ({ children }) => <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-700 dark:bg-zinc-900">{children}</tbody>,
                      tr: ({ children }) => <tr className="transition-colors hover:bg-zinc-50/50 dark:hover:bg-zinc-800/60">{children}</tr>,
                      th: ({ children }) => (
                        <th className="border-b border-zinc-200 px-4 py-3 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                          {children}
                        </th>
                      ),
                      td: ({ children }) => <td className="align-top px-4 py-3 text-zinc-600 dark:text-zinc-300">{children}</td>,
                    }}
                  >
                    {content}
                  </ReactMarkdown>
                )}
                {isQuestionDetectedFromDocument && (
                  <div
                    data-testid="planner-doc-detected-question"
                    className="mt-3 inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300"
                  >
                    Terdeteksi dari dokumen
                  </div>
                )}

                {canShowPlannerOptions && (
                  <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800/50">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-600 dark:text-zinc-300">
                        {isPlannerStep || isSystemMode ? "Pilihan Step" : "Pilihan"}
                      </span>
                      {item.planner_step && (
                        <span className="text-[10px] font-semibold text-zinc-400 dark:text-zinc-500">
                          {item.planner_step}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-col gap-2">
                      {plannerOptions.map((opt) => (
                        <button
                          key={`${item.id}-${opt.id}`}
                          data-testid={`planner-option-${opt.id}`}
                          type="button"
                          disabled={!optionsEnabled}
                          onClick={() => onSelectOption?.(opt.id, opt.label)}
                          className={cn(
                            "w-full rounded-lg border px-3 py-2 text-left text-[12px] font-medium transition",
                            optionsEnabled
                              ? "border-zinc-300 bg-white text-zinc-700 hover:border-zinc-800 hover:text-zinc-900 active:scale-[0.99] dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:border-zinc-400 dark:hover:text-zinc-100"
                              : "cursor-not-allowed border-zinc-200 bg-zinc-100 text-zinc-400 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-500"
                          )}
                        >
                          <span className="mr-2 inline-flex size-5 items-center justify-center rounded-full border border-zinc-300 text-[10px] font-bold dark:border-zinc-600">
                            {opt.id}
                          </span>
                          {opt.label}
                          {opt.detected && (
                            <span
                              data-testid={`planner-option-detected-${opt.id}`}
                              className="ml-2 inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300"
                            >
                              Terdeteksi dari dokumen
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {isPlannerMilestone && (
                  <div className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-100/60 px-2 py-1 text-[10px] font-semibold text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300">
                    <span className="material-symbols-outlined text-[12px]">flag</span>
                    Milestone Planner
                    {item.planner_step ? ` · ${item.planner_step}` : ""}
                  </div>
                )}

                {/* Footer Actions */}
                {!isPlannerMilestone && (
                <div className="mt-4 flex items-center justify-between border-t border-zinc-100 pt-3 dark:border-zinc-700">
                  <span className="flex items-center gap-1.5 text-[10px] font-medium text-zinc-400 dark:text-zinc-500">
                    <span className="material-symbols-outlined text-[14px]">verified_user</span>
                    Sumber Terverifikasi
                  </span>

                  <div className="flex items-center gap-2">
                    {sources.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setShowSources((v) => !v)}
                        className="group flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-800 active:scale-95 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                        title="Lihat rujukan"
                      >
                        <span className="material-symbols-outlined text-[14px] text-zinc-400 group-hover:text-zinc-800 dark:text-zinc-500 dark:group-hover:text-zinc-100">
                          {showSources ? "expand_less" : "expand_more"}
                        </span>
                        Rujukan
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => navigator.clipboard?.writeText?.(content)}
                      className="group flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-800 active:scale-95 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                      title="Salin jawaban"
                    >
                      <span className="material-symbols-outlined text-[14px] text-zinc-400 group-hover:text-zinc-800 dark:text-zinc-500 dark:group-hover:text-zinc-100">
                        content_copy
                      </span>
                      Salin
                    </button>
                  </div>
                </div>
                )}

                {/* Panel rujukan */}
                {!isPlannerMilestone && sources.length > 0 && showSources && (
                  <div className="mt-3 overflow-hidden rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900">
                    <div className="flex items-center justify-between border-b border-zinc-200 bg-white px-3 py-2 dark:border-zinc-700 dark:bg-zinc-800">
                      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-zinc-700 dark:text-zinc-200">
                        <span className="material-symbols-outlined text-[16px] text-zinc-500 dark:text-zinc-400">
                          library_books
                        </span>
                        Rujukan Dokumen
                      </span>
                      <span className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500">
                        {sources.length} sumber
                      </span>
                    </div>

                    <div className="divide-y divide-zinc-200 dark:divide-zinc-700">
                      {sources.map((s, idx) => (
                        <div key={`${s.source}-${idx}`} className="px-3 py-2">
                          <div className="text-[12px] font-semibold text-zinc-800 dark:text-zinc-100">
                            {s.source}
                          </div>
                          {s.snippet ? (
                            <div className="mt-1 text-[12px] leading-relaxed text-zinc-600 dark:text-zinc-300">
                              {s.snippet}
                            </div>
                          ) : (
                            <div className="mt-1 text-[12px] leading-relaxed italic text-zinc-500 dark:text-zinc-400">
                              (Tidak ada cuplikan)
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// --- 2. Typing Indicator Component (Exported) ---
// Gunakan ini di ChatThread saat loading: {loading && <TypingBubble />}
export function TypingBubble() {
  return (
    <div className="animate-entry flex w-full items-start gap-2 md:gap-4 opacity-0">
      {/* Avatar AI */}
      <div className="flex-shrink-0 mt-1">
        <div className="flex size-8 md:size-10 items-center justify-center rounded-xl bg-zinc-900 shadow-md">
          <span className="material-symbols-outlined text-[18px] text-white">smart_toy</span>
        </div>
      </div>

      {/* Bubble */}
      <div className="flex flex-col items-start max-w-[90%] md:max-w-[75%]">
        <div className="mb-1.5 flex items-center gap-2 opacity-80">
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 md:text-[11px] dark:text-zinc-400">
            Academic AI
          </span>
          <span className="text-[10px] text-zinc-400 md:text-[11px] dark:text-zinc-500">Sedang mengetik...</span>
        </div>

        <div className="rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-3 shadow-sm dark:border-zinc-700 dark:bg-zinc-900 md:px-6 md:py-4">
          <div className="flex items-center gap-1">
            <div className="dot-1 h-2 w-2 rounded-full bg-zinc-400" />
            <div className="dot-2 h-2 w-2 rounded-full bg-zinc-400" />
            <div className="dot-3 h-2 w-2 rounded-full bg-zinc-400" />
          </div>
        </div>
      </div>
    </div>
  );
}
