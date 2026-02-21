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
    <GlassCard className="mx-auto w-[min(900px,92%)]">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Sesi {index + 1} dari {total}
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
      </div>
    </GlassCard>
  );
}
