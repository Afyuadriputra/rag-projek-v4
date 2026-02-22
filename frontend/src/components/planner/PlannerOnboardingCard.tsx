import { cn } from "@/lib/utils";
import type { PlannerProfileHintsSummary } from "@/lib/api";
import GlassCard from "@/components/atoms/GlassCard";
import PlannerHeader from "@/components/planner/PlannerHeader";
import PlannerRelevanceAlert from "@/components/planner/PlannerRelevanceAlert";
import PlannerMajorCandidateChips from "@/components/planner/PlannerMajorCandidateChips";

export default function PlannerOnboardingCard({
  hasEmbeddedDocs,
  onUploadNew,
  onOpenDocPicker,
  relevanceError,
  majorSummary,
  selectedDocTitles = [],
  selectedDocCount = 0,
  onClearDocSelection,
  disabled = false,
}: {
  hasEmbeddedDocs: boolean;
  onUploadNew: () => void;
  onOpenDocPicker: () => void;
  relevanceError?: string | null;
  majorSummary?: PlannerProfileHintsSummary | null;
  selectedDocTitles?: string[];
  selectedDocCount?: number;
  onClearDocSelection: () => void;
  disabled?: boolean;
}) {
  const preview = selectedDocTitles.slice(0, 3);
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

      <div className="mt-4 rounded-2xl border border-zinc-200/90 bg-zinc-50/80 p-3 dark:border-zinc-700 dark:bg-zinc-900/45">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-300">
          Sumber aktif planner
        </div>
        <div className="mt-1 text-xs text-zinc-700 dark:text-zinc-200">
          {selectedDocCount > 0
            ? `${selectedDocCount} dokumen dipilih`
            : hasEmbeddedDocs
              ? "Belum ada dokumen yang dipilih"
              : "Belum ada dokumen embedded"}
        </div>
        {preview.length > 0 ? (
          <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-300">
            {preview.join(", ")}
            {selectedDocCount > preview.length ? ` +${selectedDocCount - preview.length} lainnya` : ""}
          </div>
        ) : null}
      </div>

      <div className="mt-4 grid gap-2">
        {hasEmbeddedDocs ? (
          <button
            type="button"
            data-testid="planner-open-doc-picker"
            onClick={onOpenDocPicker}
            disabled={disabled}
            className={cn(
              "flex min-h-12 items-center justify-between rounded-2xl border border-indigo-300/70 bg-indigo-50/70 px-4 py-2 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 dark:border-indigo-800/70 dark:bg-indigo-950/30 dark:text-indigo-200 dark:hover:bg-indigo-950/50",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            <span>Pilih Dokumen Existing</span>
            <span className="rounded-full bg-indigo-200 px-2 py-0.5 text-[10px] font-bold text-indigo-800 dark:bg-indigo-900 dark:text-indigo-100">
              Terdeteksi
            </span>
          </button>
        ) : null}
        {selectedDocCount > 0 ? (
          <button
            type="button"
            data-testid="planner-clear-doc-selection"
            onClick={onClearDocSelection}
            disabled={disabled}
            className={cn(
              "min-h-11 rounded-2xl border border-zinc-300/90 bg-white/70 px-4 py-2 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-900/35 dark:text-zinc-200 dark:hover:bg-zinc-900/60",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            Kosongkan Pilihan Dokumen
          </button>
        ) : null}
        <button
          type="button"
          data-testid="planner-upload-new-docs"
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
