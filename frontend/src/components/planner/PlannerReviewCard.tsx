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
    <div className="mx-auto mb-4 w-[min(900px,92%)] rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <h3 className="mb-3 text-sm font-bold text-zinc-900 dark:text-zinc-100">Ringkasan Rencana</h3>
      <div className="mb-4 text-xs text-zinc-500">Dokumen: {docs.map((d) => d.title).join(", ") || "-"}</div>
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-start justify-between rounded-xl border border-zinc-200 p-3 dark:border-zinc-700">
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
          className="rounded-xl bg-zinc-900 px-4 py-2 text-xs font-semibold text-white hover:bg-black disabled:opacity-60"
        >
          {executing ? "Memproses..." : "Analisis Dokumen Sekarang"}
        </button>
      </div>
    </div>
  );
}
