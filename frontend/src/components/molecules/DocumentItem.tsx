import { cn } from "@/lib/utils";

export type DocStatus = "analyzed" | "processing";

function getDocMeta(title: string) {
  const lower = title.toLowerCase();

  if (lower.endsWith(".pdf")) return { icon: "picture_as_pdf", label: "PDF" };
  if (lower.endsWith(".csv")) return { icon: "table_view", label: "CSV" };
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) return { icon: "grid_on", label: "Excel" };
  if (lower.endsWith(".md") || lower.endsWith(".txt")) return { icon: "notes", label: "Catatan" };
  if (lower.endsWith(".doc") || lower.endsWith(".docx")) return { icon: "description", label: "Dokumen" };

  return { icon: "draft", label: "File" };
}

export default function DocumentItem({
  title,
  status,
  onDelete,
  isDeleting = false,
  disableDelete = false,
}: {
  title: string;
  status: DocStatus;
  onDelete?: () => void;
  isDeleting?: boolean;
  disableDelete?: boolean;
}) {
  const meta = getDocMeta(title);

  return (
    <div
      className={cn(
        "group relative flex items-center gap-3 rounded-2xl px-3.5 py-3",
        "border border-black/5 bg-white/55 backdrop-blur-md",
        "shadow-[0_10px_30px_-26px_rgba(0,0,0,0.20)]",
        "transition-all duration-300 hover:bg-white/70 hover:shadow-[0_14px_36px_-26px_rgba(0,0,0,0.24)]",
        "active:scale-[0.995]"
      )}
      role="button"
      tabIndex={0}
    >
      {/* Liquid highlight */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-10 rounded-2xl bg-gradient-to-b from-white/70 to-transparent opacity-70" />

      {/* Icon */}
      <div
        className={cn(
          "relative size-10 rounded-xl flex items-center justify-center flex-shrink-0",
          "border border-black/10 bg-white/70",
          "shadow-[0_10px_26px_-22px_rgba(0,0,0,0.18)]"
        )}
      >
        <span className="material-symbols-outlined text-[20px] text-zinc-700">
          {meta.icon}
        </span>
      </div>

      {/* Title + meta */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="truncate text-[13.5px] font-medium text-zinc-800 group-hover:text-black transition-colors">
            {title}
          </h3>
          <span className="hidden lg:inline-flex rounded-full border border-black/10 bg-white/70 px-2 py-0.5 text-[10px] tracking-[0.16em] uppercase text-zinc-500">
            {meta.label}
          </span>
        </div>

        <div className="mt-1 flex items-center gap-2">
          <span
            className={cn(
              "size-1.5 rounded-full",
              status === "processing" ? "bg-zinc-900 animate-pulse" : "bg-zinc-300"
            )}
          />
          <span
            className={cn(
              "text-[12px] text-zinc-500 font-light",
              status === "processing" && "font-medium text-zinc-600"
            )}
          >
            {status === "processing" ? "Sedang diproses…" : "Sudah dianalisis"}
          </span>
        </div>
      </div>

      {/* Actions */}
      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          disabled={isDeleting || disableDelete}
          className={cn(
            "relative inline-flex items-center justify-center",
            "size-9 rounded-xl border border-black/10 bg-white/60",
            "text-zinc-500 hover:text-red-600 hover:bg-white transition-all",
            "opacity-0 group-hover:opacity-100",
            (isDeleting || disableDelete) && "opacity-50 cursor-not-allowed"
          )}
          title="Hapus dokumen"
        >
          {isDeleting ? (
            <span className="size-4 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent" />
          ) : (
            <span className="material-symbols-outlined text-[18px]">delete</span>
          )}
        </button>
      )}
    </div>
  );
}
