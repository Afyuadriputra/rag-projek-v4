import { cn } from "@/lib/utils";
import type { PlannerProfileHintsSummary } from "@/lib/api";

export default function PlannerOnboardingCard({
  hasEmbeddedDocs,
  onUploadNew,
  onReuseExisting,
  relevanceError,
  majorSummary,
  disabled = false,
}: {
  hasEmbeddedDocs: boolean;
  onUploadNew: () => void;
  onReuseExisting: () => void;
  relevanceError?: string | null;
  majorSummary?: PlannerProfileHintsSummary | null;
  disabled?: boolean;
}) {
  const confidence = (majorSummary?.confidence_summary || "").toLowerCase();
  const confidenceLabel =
    confidence === "high" ? "tinggi" : confidence === "medium" ? "sedang" : confidence === "low" ? "rendah" : "";

  return (
    <div className="mx-auto mb-4 w-[min(900px,92%)] rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <div className="mb-3 text-sm font-bold text-zinc-900 dark:text-zinc-100">Mode Planner Aktif</div>
      <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-300">
        Untuk hasil optimal, unggah dokumen akademik relevan: KHS, KRS, Jadwal, Transkrip, atau Kurikulum.
      </p>
      <p className="mb-4 text-xs text-zinc-500 dark:text-zinc-400">
        Jika dokumen tidak relevan, planner akan ditunda sampai dokumen valid.
      </p>

      {relevanceError && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/35 dark:text-amber-300">
          {relevanceError}
        </div>
      )}

      {!!majorSummary?.major_candidates?.length && (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-xs text-blue-900 dark:border-blue-900/50 dark:bg-blue-950/35 dark:text-blue-200">
          <div className="mb-1 font-semibold">
            Kandidat jurusan terdeteksi{confidenceLabel ? ` (confidence ${confidenceLabel})` : ""}:
          </div>
          <div className="flex flex-wrap gap-2">
            {majorSummary.major_candidates.slice(0, 3).map((c, idx) => (
              <span
                key={`${String(c.value)}-${idx}`}
                className="rounded-full border border-blue-300 px-2 py-1 dark:border-blue-800"
              >
                {c.label}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onUploadNew}
          disabled={disabled}
          className={cn(
            "rounded-xl px-4 py-2 text-xs font-semibold",
            "bg-zinc-900 text-white hover:bg-black",
            disabled && "cursor-not-allowed opacity-60"
          )}
        >
          Unggah Dokumen Baru
        </button>
        {hasEmbeddedDocs && (
          <button
            type="button"
            onClick={onReuseExisting}
            disabled={disabled}
            className={cn(
              "rounded-xl border border-zinc-300 px-4 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            Gunakan Dokumen Existing
          </button>
        )}
      </div>
    </div>
  );
}
