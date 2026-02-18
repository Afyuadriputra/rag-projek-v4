import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export default function ChatComposer({
  onSend,
  onUploadClick,
  loading,
  deletingDoc = false,
}: {
  onSend: (message: string) => void;
  onUploadClick: () => void;
  loading?: boolean;
  deletingDoc?: boolean;
}) {
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(160, ta.scrollHeight) + "px";
  }, [value]);

  const submit = () => {
    const msg = value.trim();
    if (!msg || loading) return;
    onSend(msg);
    setValue("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  const canSend = !!value.trim() && !loading;

  return (
    <div className="absolute bottom-0 left-0 w-full z-20" data-testid="chat-composer">
      <div className="relative mx-auto w-full max-w-3xl px-4 pb-6 pt-4">
        {/* Tinted liquid shell */}
        <div
          className={cn(
            "relative rounded-[34px] p-[2px]",
            "transition-all duration-500 ease-out",
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
              "shadow-[0_22px_70px_-26px_rgba(0,0,0,0.35)]",
              isFocused ? "shadow-[0_30px_90px_-30px_rgba(0,0,0,0.40)]" : ""
            )}
          />

          {/* Inner glass surface (tinted, but transparent) */}
          <div
            className={cn(
              "relative flex items-end gap-2 rounded-[32px] p-2",
              // ✅ Blur ONLY on composer surface (chat above won't blur)
              "bg-white/8 backdrop-blur-[24px] backdrop-saturate-200",
              // ✅ iOS-ish tint layered on top (still transparent)
              "before:pointer-events-none before:absolute before:inset-0 before:rounded-[32px]",
              "before:bg-[radial-gradient(90%_80%_at_18%_0%,rgba(99,102,241,0.20)_0%,transparent_55%),radial-gradient(90%_80%_at_82%_120%,rgba(59,130,246,0.14)_0%,transparent_55%)]",
              "before:opacity-70",
              "border border-white/22 ring-1 ring-white/12",
              "transition-all duration-500 ease-out",
              isFocused ? "bg-white/12 border-white/32 ring-white/22" : "hover:bg-white/10"
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
              className={cn(
                "group relative flex size-10 flex-shrink-0 items-center justify-center rounded-full",
                "transition-all duration-300 active:scale-95",
                "text-zinc-800/70 hover:text-zinc-950",
                "bg-white/10 hover:bg-white/18",
                "border border-white/18 hover:border-white/32",
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
            <div className="flex-1 py-2">
              <textarea
                data-testid="chat-input"
                ref={taRef}
                value={value}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                onChange={(e) => setValue(e.target.value)}
                placeholder="Tanya sesuatu..."
                rows={1}
                disabled={loading}
                className={cn(
                  "block w-full resize-none bg-transparent px-2",
                  "text-[16px] leading-relaxed text-zinc-950/85 placeholder:text-zinc-700/60 font-light",
                  "border-none focus:ring-0 focus:outline-none",
                  "max-h-[160px] overflow-y-auto scrollbar-hide"
                )}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
              />
              {loading && (
                <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-600/70 font-medium">
                  Input dinonaktifkan sementara
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
                className={cn(
                  "relative flex items-center justify-center rounded-full",
                  "transition-all duration-500 cubic-bezier(0.34, 1.56, 0.64, 1)",
                  canSend
                    ? cn(
                        "size-10",
                        "bg-black/70 text-white",
                        "border border-white/10",
                        "backdrop-blur-[8px]",
                        "shadow-[0_14px_38px_-18px_rgba(0,0,0,0.75)]",
                        "scale-100 opacity-100 rotate-0"
                      )
                    : "size-8 bg-white/10 text-zinc-700/50 scale-90 opacity-0 rotate-45 pointer-events-none"
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
          <p className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-700/50 font-medium">
            {loading ? (
              <>
                <span className="block size-1.5 animate-pulse rounded-full bg-zinc-600/50" />
                {deletingDoc ? "Sedang menghapus..." : "Thinking..."}
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
