import type { PlannerWizardStep } from "@/lib/api";
import GlassCard from "@/components/atoms/GlassCard";
import PillChip from "@/components/atoms/PillChip";
import PlannerHeader from "@/components/planner/PlannerHeader";
import PlannerOptionList from "@/components/planner/PlannerOptionList";
import PlannerManualInput from "@/components/planner/PlannerManualInput";
import PlannerActionBar from "@/components/planner/PlannerActionBar";

export default function PlannerWizardCard({
  step,
  index,
  total,
  progressCurrent,
  progressTotal,
  showMajorHeader = false,
  majorLabel = "",
  majorConfidenceLevel = "low",
  pathLabel = "",
  stepReason = "",
  value,
  onSelectOption,
  onChangeManual,
  onNext,
  onBack,
  canGenerateNow = false,
  onGenerateNow,
  pathSummary = "",
  disabled = false,
}: {
  step: PlannerWizardStep;
  index: number;
  total: number;
  progressCurrent?: number;
  progressTotal?: number;
  showMajorHeader?: boolean;
  majorLabel?: string;
  majorConfidenceLevel?: "high" | "medium" | "low" | string;
  pathLabel?: string;
  stepReason?: string;
  value: string;
  onSelectOption: (v: string) => void;
  onChangeManual: (v: string) => void;
  onNext: () => void;
  onBack: () => void;
  canGenerateNow?: boolean;
  onGenerateNow?: () => void;
  pathSummary?: string;
  disabled?: boolean;
}) {
  const current = progressCurrent || index + 1;
  const estimatedTotal = progressTotal || total;
  const confText =
    majorConfidenceLevel === "high"
      ? "High Conf"
      : majorConfidenceLevel === "medium"
        ? "Medium Conf"
        : "Low Conf";

  const sourceHintLabel =
    step.source_hint === "document"
      ? "Dari Dokumen"
      : step.source_hint === "profile"
        ? "Dari Profil"
        : "Gabungan";

  return (
    <GlassCard className="mx-auto w-[min(900px,92%)]">
      {showMajorHeader ? (
        <div className="mb-3 rounded-2xl bg-indigo-600/95 p-3 text-white">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs uppercase tracking-wider text-indigo-100">Jurusan Terdeteksi</div>
            <span className="rounded-full border border-indigo-300/60 bg-indigo-500/30 px-2 py-0.5 text-[10px] font-bold">
              {confText}
            </span>
          </div>
          <div className="mt-1 text-sm font-bold">{majorLabel || "-"}</div>
        </div>
      ) : (
        <div className="mb-3 rounded-2xl border border-zinc-200/80 bg-zinc-50/90 p-3 dark:border-zinc-700 dark:bg-zinc-900/50">
          <div className="text-[11px] font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-300">
            ✨ Path: {pathLabel || "Analisis"}
          </div>
          {!!stepReason && <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{stepReason}</div>}
        </div>
      )}

      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Step {current}/{estimatedTotal}
        </span>
        <div className="inline-flex items-center gap-2">
          {!!step.required && <PillChip variant="warn">Wajib</PillChip>}
          <PillChip>{sourceHintLabel}</PillChip>
        </div>
      </div>
      <PlannerHeader title={step.title} subtitle={step.question} />

      <PlannerOptionList options={step.options} value={value} disabled={disabled} onSelect={onSelectOption} />

      {step.allow_manual && (
        <div className="mt-3">
          <PlannerManualInput value={value} disabled={disabled} onChange={onChangeManual} />
        </div>
      )}

      <div className="mt-4">
        <PlannerActionBar
          leftLabel="Kembali"
          rightLabel="Lanjut"
          leftDisabled={disabled || index === 0}
          rightDisabled={disabled || !value.trim()}
          onLeft={onBack}
          onRight={onNext}
        />
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-zinc-200/70 pt-3 dark:border-zinc-700/70">
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {canGenerateNow
              ? pathSummary || "Data sudah cukup. Kamu bisa langsung generate."
              : "Jika sudah cukup, kamu bisa lanjut ke analisis tanpa menjawab semua langkah."}
          </p>
          <button
            type="button"
            disabled={disabled || !onGenerateNow}
            onClick={onGenerateNow}
            className="min-h-10 rounded-2xl bg-zinc-900 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-black disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            Analisis Sekarang
          </button>
        </div>
      </div>
    </GlassCard>
  );
}
