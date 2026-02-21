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
        title="Mode Planner Aktif"
        subtitle="Untuk hasil optimal, unggah dokumen akademik relevan: KHS, KRS, Jadwal, Transkrip, atau Kurikulum."
      />
      <p className="mb-4 text-xs text-zinc-500 dark:text-zinc-400">
        Jika dokumen tidak relevan, planner akan ditunda sampai dokumen valid.
      </p>

      {relevanceError && <PlannerRelevanceAlert message={relevanceError} />}

      <div className="mt-4">
        <PlannerMajorCandidateChips majorSummary={majorSummary} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onUploadNew}
          disabled={disabled}
          className={cn(
            "min-h-11 rounded-2xl px-4 py-2 text-xs font-semibold transition",
            "bg-zinc-900 text-white hover:bg-black dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200",
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
              "min-h-11 rounded-2xl border border-zinc-300 px-4 py-2 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50/85 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800/75",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            Gunakan Dokumen Existing
          </button>
        )}
      </div>
    </GlassCard>
  );
}
