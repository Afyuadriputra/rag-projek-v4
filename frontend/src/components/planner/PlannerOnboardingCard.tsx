import { cn } from "@/lib/utils";
import type { PlannerProfileHintsSummary } from "@/lib/api";
import GlassCard from "@/components/atoms/GlassCard";
import PlannerHeader from "@/components/planner/PlannerHeader";
import PlannerRelevanceAlert from "@/components/planner/PlannerRelevanceAlert";
import PlannerMajorCandidateChips from "@/components/planner/PlannerMajorCandidateChips";

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
  return (
    <GlassCard className="mx-auto w-[min(900px,92%)]">
      <PlannerHeader
        title="Setup Dokumen Planner"
        subtitle="Gunakan dokumen existing atau unggah baru untuk memulai analisis adaptif."
      />
      <p className="mb-4 text-xs text-zinc-500 dark:text-zinc-400">
        Untuk hasil akurat, gunakan KHS, KRS, Jadwal, Transkrip, atau Kurikulum yang valid.
      </p>

      {relevanceError && <PlannerRelevanceAlert message={relevanceError} />}

      <div className="mt-4">
        <PlannerMajorCandidateChips majorSummary={majorSummary} />
      </div>

      <div className="mt-4 grid gap-2">
        {hasEmbeddedDocs ? (
          <button
            type="button"
            onClick={onReuseExisting}
            disabled={disabled}
            className={cn(
              "flex min-h-12 items-center justify-between rounded-2xl border border-indigo-300/70 bg-indigo-50/70 px-4 py-2 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 dark:border-indigo-800/70 dark:bg-indigo-950/30 dark:text-indigo-200 dark:hover:bg-indigo-950/50",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            <span>Gunakan Dokumen Existing</span>
            <span className="rounded-full bg-indigo-200 px-2 py-0.5 text-[10px] font-bold text-indigo-800 dark:bg-indigo-900 dark:text-indigo-100">
              Terdeteksi
            </span>
          </button>
        ) : null}
        <button
          type="button"
          onClick={onUploadNew}
          disabled={disabled}
          className={cn(
            "min-h-12 rounded-2xl border border-dashed border-zinc-300/90 bg-white/70 px-4 py-2 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50/85 dark:border-zinc-600 dark:bg-zinc-900/35 dark:text-zinc-200 dark:hover:bg-zinc-900/60",
            disabled && "cursor-not-allowed opacity-60"
          )}
        >
          Unggah Dokumen Baru
        </button>
      </div>
    </GlassCard>
  );
}
