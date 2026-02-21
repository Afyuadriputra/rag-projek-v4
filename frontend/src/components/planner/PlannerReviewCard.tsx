import GlassCard from "@/components/atoms/GlassCard";
import PlannerHeader from "@/components/planner/PlannerHeader";
import PlannerDocSummary from "@/components/planner/PlannerDocSummary";

export default function PlannerReviewCard({
  answers,
  docs,
  onEdit,
  onExecute,
  executing = false,
}: {
  answers: Record<string, string>;
  docs: Array<{ id: number; title: string }>;
  onEdit: (stepKey: string) => void;
  onExecute: () => void;
  executing?: boolean;
}) {
  const entries = Object.entries(answers);
  return (
    <GlassCard className="mx-auto w-[min(900px,92%)]">
      <PlannerHeader title="Ringkasan Rencana" />
      <div className="mb-4">
        <PlannerDocSummary docs={docs} />
      </div>
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div
            key={k}
            className="flex items-start justify-between rounded-2xl border border-zinc-200/90 bg-white/60 p-3 dark:border-zinc-700 dark:bg-zinc-900/35"
          >
            <div>
              <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">{k}</div>
              <div className="text-sm text-zinc-600 dark:text-zinc-300">{v}</div>
            </div>
            <button
              type="button"
              onClick={() => onEdit(k)}
              className="text-xs font-semibold text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            >
              Edit
            </button>
          </div>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onExecute}
          disabled={executing}
          className="min-h-11 rounded-2xl bg-zinc-900 px-4 py-2 text-xs font-semibold text-white transition hover:bg-black disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {executing ? "Memproses..." : "Analisis Dokumen Sekarang"}
        </button>
      </div>
    </GlassCard>
  );
}
