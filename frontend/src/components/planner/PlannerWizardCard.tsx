import { cn } from "@/lib/utils";
import type { PlannerWizardStep } from "@/lib/api";

export default function PlannerWizardCard({
  step,
  index,
  total,
  value,
  onSelectOption,
  onChangeManual,
  onNext,
  onBack,
  disabled = false,
}: {
  step: PlannerWizardStep;
  index: number;
  total: number;
  value: string;
  onSelectOption: (v: string) => void;
  onChangeManual: (v: string) => void;
  onNext: () => void;
  onBack: () => void;
  disabled?: boolean;
}) {
  const sourceHintLabel =
    step.source_hint === "document"
      ? "Dari Dokumen"
      : step.source_hint === "profile"
        ? "Dari Profil"
        : "Gabungan";

  return (
    <div className="mx-auto mb-4 w-[min(900px,92%)] rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Sesi {index + 1} dari {total}</div>
        <div className="inline-flex items-center gap-2">
          {!!step.required && (
            <span className="rounded-full border border-rose-200 px-2 py-0.5 text-[10px] font-semibold text-rose-700 dark:border-rose-900 dark:text-rose-300">
              Wajib
            </span>
          )}
          <span className="rounded-full border border-zinc-300 px-2 py-0.5 text-[10px] font-semibold text-zinc-600 dark:border-zinc-600 dark:text-zinc-300">
            {sourceHintLabel}
          </span>
        </div>
      </div>
      <h3 className="mb-3 text-sm font-bold text-zinc-900 dark:text-zinc-100">{step.title}</h3>
      <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-300">{step.question}</p>

      <div className="mb-3 flex flex-wrap gap-2">
        {step.options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelectOption(String(opt.value))}
            className={cn(
              "rounded-xl border px-3 py-2 text-xs font-semibold transition",
              value === String(opt.value)
                ? "border-zinc-900 bg-zinc-900 text-white"
                : "border-zinc-300 text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {step.allow_manual && (
        <textarea
          value={value}
          disabled={disabled}
          onChange={(e) => onChangeManual(e.target.value)}
          placeholder="Atau tulis manual..."
          className="mb-4 w-full rounded-xl border border-zinc-300 bg-white p-3 text-sm text-zinc-800 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          rows={3}
        />
      )}

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          disabled={disabled || index === 0}
          className="rounded-xl border border-zinc-300 px-3 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          Kembali
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={disabled || !value.trim()}
          className="rounded-xl bg-zinc-900 px-4 py-2 text-xs font-semibold text-white hover:bg-black disabled:opacity-50"
        >
          Lanjut
        </button>
      </div>
    </div>
  );
}
