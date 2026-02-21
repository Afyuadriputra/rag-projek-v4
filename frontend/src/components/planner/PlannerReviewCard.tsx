import GlassCard from "@/components/atoms/GlassCard";
import PlannerHeader from "@/components/planner/PlannerHeader";
import PlannerDocSummary from "@/components/planner/PlannerDocSummary";

export default function PlannerReviewCard({
  answers,
  docs,
  majorLabel,
  majorSource = "inferred",
  onEdit,
  onExecute,
  executing = false,
}: {
  answers: Record<string, string>;
  docs: Array<{ id: number; title: string }>;
  majorLabel?: string;
  majorSource?: "user_override" | "inferred" | string;
  onEdit: (stepKey: string) => void;
  onExecute: () => void;
  executing?: boolean;
}) {
  const labelMap: Record<string, string> = {
    intent: "Fokus Analisis",
    topic_interest: "Minat Bidang",
    topic_area: "Area Spesifik",
  };
  const humanize = (k: string) => {
    if (labelMap[k]) return labelMap[k];
    const txt = String(k || "").replace(/_/g, " ").trim();
    return txt ? txt.charAt(0).toUpperCase() + txt.slice(1) : "Langkah";
  };
  const entries = Object.entries(answers);
  return (
    <GlassCard className="mx-auto w-[min(900px,92%)]">
      <PlannerHeader title="Ringkasan Rencana" />
      {!!majorLabel && (
        <div className="mb-3 rounded-2xl border border-indigo-200 bg-indigo-50/70 px-3 py-2 text-xs text-indigo-800 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200">
          Jurusan: <b>{majorLabel}</b> ({majorSource === "user_override" ? "dari user" : "dari inferensi"})
        </div>
      )}
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
              <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">{humanize(k)}</div>
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
