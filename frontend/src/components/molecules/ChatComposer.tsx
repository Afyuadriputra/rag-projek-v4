import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export default function ChatComposer({
  onSend,
  onUploadClick,
  loading,
  deletingDoc = false,
  plannerLockReason,
  docs = [],
}: {
  onSend: (message: string) => void;
  onUploadClick: () => void;
  loading?: boolean;
  deletingDoc?: boolean;
  plannerLockReason?: string;
  docs?: Array<{ id: number; title: string }>;
}) {
  const MAX_TEXTAREA_HEIGHT = 160;
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [mentionIndex, setMentionIndex] = useState(0);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const composingRef = useRef(false);

  const resizeTextarea = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(MAX_TEXTAREA_HEIGHT, ta.scrollHeight)}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [value, resizeTextarea]);

  const submit = useCallback(() => {
    const msg = value.trim();
    if (!msg || loading) return;
    onSend(msg);
    setValue("");
    const ta = taRef.current;
    if (ta) ta.style.height = "auto";
  }, [loading, onSend, value]);

  const canSend = !!value.trim() && !loading;
  const cursorPos = taRef.current?.selectionStart ?? value.length;

  const mentionState = useMemo(() => {
    const left = value.slice(0, cursorPos);
    const match = left.match(/(?:^|\s)@([^\s@]*)$/);
    if (!match) return null;
    const full = match[0];
    const atOffset = full.lastIndexOf("@");
    const start = (match.index ?? 0) + atOffset;
    return {
      query: (match[1] || "").trim().toLowerCase(),
      start,
      end: cursorPos,
    };
  }, [cursorPos, value]);

  const mentionCandidates = useMemo(() => {
    if (!mentionState || !isFocused) return [];
    const query = mentionState.query;
    const list = docs.filter((d) => {
        const title = (d.title || "").toLowerCase();
        return !query || title.includes(query);
      })
      .slice(0, 8);
    return list;
  }, [docs, isFocused, mentionState]);

  useEffect(() => {
    setMentionIndex(0);
  }, [mentionCandidates.length, mentionState?.query]);

  const applyMention = useCallback((title: string) => {
    const ta = taRef.current;
    if (!ta || !mentionState) return;
    const before = value.slice(0, mentionState.start);
    const after = value.slice(mentionState.end);
    const inserted = `@${title} `;
    const next = `${before}${inserted}${after}`;
    setValue(next);
    requestAnimationFrame(() => {
      const pos = before.length + inserted.length;
      ta.focus();
      ta.setSelectionRange(pos, pos);
      resizeTextarea();
    });
  }, [mentionState, resizeTextarea, value]);

  return (
    <div className="absolute bottom-0 left-0 w-full z-20" data-testid="chat-composer">
      <div className="relative mx-auto w-full max-w-3xl px-4 pb-6 pt-4">
        {/* Tinted liquid shell */}
        <div
          className={cn(
            "relative rounded-[34px] p-[2px]",
            "transition-[transform] duration-300 ease-out motion-reduce:transition-none",
            isFocused ? "-translate-y-[2px]" : "hover:-translate-y-[1px]"
          )}
        >
          {/* Specular rim */}
          <div
            className={cn(
              "pointer-events-none absolute inset-0 rounded-[34px]",
              "bg-[conic-gradient(from_180deg_at_50%_50%,rgba(255,255,255,0.70),rgba(255,255,255,0.10),rgba(255,255,255,0.45),rgba(255,255,255,0.08),rgba(255,255,255,0.70))]",
              "opacity-70"
            )}
          />

          {/* Ambient tinted halo (subtle blue/purple like iOS) */}
          <div
            className={cn(
              "pointer-events-none absolute -inset-[10px] rounded-[42px]",
              "bg-[radial-gradient(60%_70%_at_20%_10%,rgba(99,102,241,0.22)_0%,transparent_60%),radial-gradient(55%_65%_at_85%_120%,rgba(59,130,246,0.18)_0%,transparent_55%)]",
              "blur-[14px] opacity-80"
            )}
          />

          {/* Shadow */}
          <div
            className={cn(
              "pointer-events-none absolute inset-0 rounded-[34px]",
              "transition-shadow duration-300 ease-out motion-reduce:transition-none shadow-[0_22px_70px_-26px_rgba(0,0,0,0.35)]",
              isFocused ? "shadow-[0_30px_90px_-30px_rgba(0,0,0,0.40)]" : ""
            )}
          />

          {/* Inner glass surface (tinted, but transparent) */}
          <div
            className={cn(
              "relative flex items-end gap-2 rounded-[32px] p-2",
              // ✅ Blur ONLY on composer surface (chat above won't blur)
              "bg-white/8 backdrop-blur-[24px] backdrop-saturate-200 dark:bg-zinc-900/60",
              // ✅ iOS-ish tint layered on top (still transparent)
              "before:pointer-events-none before:absolute before:inset-0 before:rounded-[32px]",
              "before:bg-[radial-gradient(90%_80%_at_18%_0%,rgba(99,102,241,0.20)_0%,transparent_55%),radial-gradient(90%_80%_at_82%_120%,rgba(59,130,246,0.14)_0%,transparent_55%)]",
              "before:opacity-70",
              "border border-white/22 ring-1 ring-white/12 dark:border-zinc-700/70 dark:ring-zinc-700/40",
              "transition-[background-color,border-color,box-shadow] duration-300 ease-out motion-reduce:transition-none",
              isFocused ? "bg-white/12 border-white/32 ring-white/22 dark:bg-zinc-900/80 dark:border-zinc-600 dark:ring-zinc-600/40" : "hover:bg-white/10 dark:hover:bg-zinc-900/70"
            )}
          >
            {/* Specular highlight streaks */}
            <div className="pointer-events-none absolute inset-x-6 top-1 h-[1px] bg-gradient-to-r from-transparent via-white/60 to-transparent opacity-75" />
            <div className="pointer-events-none absolute inset-x-10 top-2 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent opacity-60" />

            {/* Soft bloom */}
            <div className="pointer-events-none absolute inset-0 rounded-[32px] bg-[radial-gradient(95%_70%_at_22%_0%,rgba(255,255,255,0.26)_0%,transparent_58%)]" />
            <div className="pointer-events-none absolute inset-0 rounded-[32px] bg-[radial-gradient(95%_70%_at_78%_120%,rgba(255,255,255,0.14)_0%,transparent_55%)]" />

            {/* Grain / noise (no external image) */}
            <div
              className="pointer-events-none absolute inset-0 rounded-[32px] opacity-[0.10] mix-blend-overlay"
              style={{
                backgroundImage: `
                  repeating-linear-gradient(0deg, rgba(255,255,255,0.06) 0px, rgba(255,255,255,0.06) 1px, rgba(0,0,0,0.00) 2px, rgba(0,0,0,0.00) 3px),
                  repeating-linear-gradient(90deg, rgba(0,0,0,0.04) 0px, rgba(0,0,0,0.04) 1px, rgba(0,0,0,0.00) 2px, rgba(0,0,0,0.00) 3px)
                `,
              }}
            />

            {/* UPLOAD BUTTON (tinted glass) */}
            <button
              data-testid="chat-upload"
              type="button"
              onClick={onUploadClick}
              disabled={loading}
              aria-label={deletingDoc ? "Unggah dinonaktifkan saat menghapus dokumen" : "Unggah dokumen"}
              className={cn(
                "group relative flex size-10 flex-shrink-0 items-center justify-center rounded-full touch-manipulation",
                "transition-[transform,background-color,border-color,color,opacity] duration-200 active:scale-95 motion-reduce:transition-none",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-800/60 focus-visible:ring-offset-2 dark:focus-visible:ring-zinc-300/70 dark:focus-visible:ring-offset-zinc-900",
                "text-zinc-800/70 hover:text-zinc-950 dark:text-zinc-300 dark:hover:text-zinc-100",
                "bg-white/10 hover:bg-white/18 dark:bg-zinc-800/70 dark:hover:bg-zinc-800",
                "border border-white/18 hover:border-white/32 dark:border-zinc-700 dark:hover:border-zinc-500",
                "shadow-[inset_0_1px_0_rgba(255,255,255,0.40)]",
                loading && "opacity-50 cursor-not-allowed"
              )}
              title={deletingDoc ? "Sedang menghapus dokumen..." : "Unggah dokumen"}
            >
              <span className="material-symbols-outlined text-[22px] transition-transform duration-300 group-hover:rotate-12">
                add_circle
              </span>
              <span className="pointer-events-none absolute inset-x-2 top-1 h-3 rounded-full bg-white/18 blur-[7px] opacity-80" />
            </button>

            {/* TEXT AREA */}
            <div className="relative flex-1 py-2">
              {mentionCandidates.length > 0 && (
                <div
                  className={cn(
                    "absolute bottom-full left-0 right-0 mb-2 max-h-44 overflow-y-auto rounded-2xl border p-1 shadow-xl backdrop-blur-xl",
                    "bg-white/90 border-zinc-200 dark:bg-zinc-900/95 dark:border-zinc-700"
                  )}
                  data-testid="mention-dropdown"
                >
                  {mentionCandidates.map((doc, idx) => (
                    <button
                      key={doc.id}
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        applyMention(doc.title);
                      }}
                      className={cn(
                        "w-full rounded-xl px-3 py-2 text-left text-xs transition",
                        idx === mentionIndex
                          ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                          : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      )}
                    >
                      @{doc.title}
                    </button>
                  ))}
                </div>
              )}
              <textarea
                data-testid="chat-input"
                ref={taRef}
                value={value}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                onChange={(e) => setValue(e.target.value)}
                onInput={resizeTextarea}
                placeholder="Tanya sesuatu..."
                rows={1}
                disabled={loading}
                aria-label="Input chat"
                className={cn(
                  "block w-full min-h-[40px] resize-none bg-transparent px-2",
                  "text-[16px] leading-relaxed text-zinc-950/85 placeholder:text-zinc-700/60 font-light dark:text-zinc-100 dark:placeholder:text-zinc-500",
                  "border-none focus:ring-0 focus:outline-none",
                  "max-h-[160px] overflow-y-auto scrollbar-hide"
                )}
                onCompositionStart={() => {
                  composingRef.current = true;
                }}
                onCompositionEnd={() => {
                  composingRef.current = false;
                }}
                onKeyDown={(e) => {
                  if (composingRef.current || e.nativeEvent.isComposing) return;
                  if (mentionCandidates.length > 0) {
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setMentionIndex((prev) => Math.min(prev + 1, mentionCandidates.length - 1));
                      return;
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setMentionIndex((prev) => Math.max(prev - 1, 0));
                      return;
                    }
                    if (e.key === "Tab" || e.key === "Enter") {
                      e.preventDefault();
                      const pick = mentionCandidates[mentionIndex];
                      if (pick) applyMention(pick.title);
                      return;
                    }
                    if (e.key === "Escape") {
                      e.preventDefault();
                      setMentionIndex(0);
                      return;
                    }
                  }
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
              />
              {loading && (
                <div
                  className={cn(
                    "mt-1 text-[10px] font-medium text-zinc-600/70 dark:text-zinc-400",
                    plannerLockReason ? "tracking-normal normal-case" : "uppercase tracking-[0.2em]"
                  )}
                >
                  {plannerLockReason || "Input dinonaktifkan sementara"}
                </div>
              )}
            </div>

            {/* SEND BUTTON */}
            <div className="flex size-10 items-center justify-center">
              <button
                data-testid="chat-send"
                type="button"
                onClick={submit}
                disabled={!canSend}
                aria-label={loading ? "Proses berjalan" : "Kirim pesan"}
                className={cn(
                  "relative flex size-10 items-center justify-center rounded-full touch-manipulation",
                  "transition-[transform,background-color,border-color,color,opacity] duration-200 motion-reduce:transition-none",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-800/60 focus-visible:ring-offset-2 dark:focus-visible:ring-zinc-300/70 dark:focus-visible:ring-offset-zinc-900",
                  canSend
                    ? cn(
                        "bg-black/70 text-white",
                        "border border-white/10",
                        "backdrop-blur-[8px]",
                        "shadow-[0_14px_38px_-18px_rgba(0,0,0,0.75)]",
                        "scale-100 opacity-100"
                      )
                    : "bg-white/10 text-zinc-700/50 border border-white/10 scale-100 opacity-70 dark:bg-zinc-800/80 dark:text-zinc-500 dark:border-zinc-700"
                )}
                title={loading ? "Stop" : "Kirim"}
              >
                <span className="pointer-events-none absolute inset-x-2 top-1 h-3 rounded-full bg-white/14 blur-[7px] opacity-85" />
                <span className="material-symbols-outlined text-[20px]">
                  {loading ? "stop" : "arrow_upward"}
                </span>
              </button>
            </div>
          </div>
        </div>

        {/* Status line */}
        <div className="mt-3 flex justify-center">
          <p
            aria-live="polite"
            className={cn(
              "flex items-center gap-2 text-[10px] font-medium text-zinc-700/50 dark:text-zinc-400",
              loading && plannerLockReason ? "tracking-normal normal-case" : "uppercase tracking-[0.2em]"
            )}
          >
            {loading ? (
              <>
                <span className="block size-1.5 animate-pulse rounded-full bg-zinc-600/50" />
                {deletingDoc ? "Sedang menghapus…" : plannerLockReason || "Thinking…"}
              </>
            ) : (
              "Academic AI • Context Aware"
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
