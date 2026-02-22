import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";

type PlannerDoc = { id: number; title: string };

export default function PlannerDocPickerSheet({
  open,
  docs,
  selectedIds,
  onClose,
  onConfirm,
  onClear,
}: {
  open: boolean;
  docs: PlannerDoc[];
  selectedIds: number[];
  onClose: () => void;
  onConfirm: (ids: number[]) => void;
  onClear: () => void;
}) {
  const [localSelected, setLocalSelected] = useState<number[]>(selectedIds);

  useEffect(() => {
    if (open) setLocalSelected(selectedIds);
  }, [open, selectedIds]);

  const selectedSet = useMemo(() => new Set(localSelected), [localSelected]);
  const canConfirm = localSelected.length > 0;

  if (!open) return null;

  return (
    <div
      data-testid="planner-doc-picker-sheet"
      className="fixed inset-0 z-[1200] flex items-end justify-center sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="planner-doc-picker-title"
    >
      <button
        type="button"
        aria-label="Tutup pemilih dokumen"
        onClick={onClose}
        className="absolute inset-0 bg-black/35 backdrop-blur-[1px]"
      />

      <div className="relative z-[1201] flex max-h-[82vh] w-[min(720px,94vw)] flex-col overflow-hidden rounded-t-3xl border border-zinc-200 bg-white shadow-2xl sm:rounded-3xl dark:border-zinc-700 dark:bg-zinc-900">
        <div className="sticky top-0 z-10 border-b border-zinc-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-zinc-700 dark:bg-zinc-900/95">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 id="planner-doc-picker-title" className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
                Pilih Dokumen Existing
              </h3>
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">
                Pilih minimal satu dokumen untuk digunakan sebagai sumber planner.
              </p>
            </div>
            <button
              type="button"
              data-testid="planner-doc-picker-close"
              onClick={onClose}
              className="rounded-xl px-2 py-1 text-xs font-semibold text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            >
              Tutup
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-3 py-3">
          {docs.length === 0 ? (
            <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-3 py-4 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-300">
              Belum ada dokumen embedded yang siap dipakai.
            </div>
          ) : (
            <div className="space-y-2">
              {docs.map((doc) => {
                const checked = selectedSet.has(doc.id);
                return (
                  <label
                    key={doc.id}
                    data-testid={`planner-doc-row-${doc.id}`}
                    className={cn(
                      "flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border px-3 py-2.5 transition",
                      checked
                        ? "border-indigo-400 bg-indigo-50/70 dark:border-indigo-700 dark:bg-indigo-950/40"
                        : "border-zinc-200 bg-white hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800/60"
                    )}
                  >
                    <input
                      data-testid={`planner-doc-checkbox-${doc.id}`}
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                      checked={checked}
                      onChange={(e) => {
                        const isChecked = e.target.checked;
                        setLocalSelected((prev) => {
                          if (isChecked) return Array.from(new Set([...prev, doc.id]));
                          return prev.filter((x) => x !== doc.id);
                        });
                      }}
                    />
                    <span className="text-xs font-medium text-zinc-700 dark:text-zinc-200">{doc.title}</span>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        <div className="sticky bottom-0 z-10 flex items-center justify-between gap-2 border-t border-zinc-200 bg-white/95 px-3 py-3 backdrop-blur dark:border-zinc-700 dark:bg-zinc-900/95">
          <div className="text-xs text-zinc-600 dark:text-zinc-300">{localSelected.length} dokumen dipilih</div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="planner-doc-picker-clear"
              onClick={() => {
                setLocalSelected([]);
                onClear();
              }}
              className="min-h-11 rounded-xl border border-zinc-300 px-3 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-100 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              Kosongkan
            </button>
            <button
              type="button"
              data-testid="planner-doc-picker-confirm"
              disabled={!canConfirm}
              onClick={() => onConfirm(localSelected)}
              className="min-h-11 rounded-xl bg-zinc-900 px-4 py-2 text-xs font-semibold text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              Gunakan Dokumen Terpilih
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
