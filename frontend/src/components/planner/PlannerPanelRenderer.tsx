import PlannerOnboardingCard from "@/components/planner/PlannerOnboardingCard";
import PlannerWizardCard from "@/components/planner/PlannerWizardCard";
import PlannerReviewCard from "@/components/planner/PlannerReviewCard";
import PlannerProgressOverlay from "@/components/planner/PlannerProgressOverlay";
import PlannerDocPickerSheet from "@/components/planner/PlannerDocPickerSheet";
import type { PlannerProfileHintsSummary, PlannerWizardStep } from "@/lib/api";
import type { PlannerHeaderMeta } from "@/lib/api";

export type PlannerUiState = "idle" | "onboarding" | "uploading" | "branching" | "ready" | "reviewing" | "executing" | "done";

export default function PlannerPanelRenderer({
  state,
  hasEmbeddedDocs,
  relevanceError,
  majorSummary,
  progressMessage,
  progressMode = "start",
  wizardSteps,
  wizardIndex,
  progressCurrent = 1,
  progressEstimatedTotal = 4,
  plannerHeader,
  plannerMajorSource = "inferred",
  plannerStepHeader,
  wizardAnswers,
  plannerCanGenerateNow,
  plannerPathSummary,
  plannerDocs,
  embeddedDocs,
  selectedDocIds,
  selectedDocTitles,
  docPickerOpen,
  loading,
  deletingDocId,
  plannerWarning,
  onUploadNew,
  onOpenDocPicker,
  onConfirmDocPicker,
  onCloseDocPicker,
  onClearDocSelection,
  onSelectOption,
  onChangeManual,
  onNext,
  onBack,
  onEdit,
  onExecute,
}: {
  state: PlannerUiState;
  hasEmbeddedDocs: boolean;
  relevanceError?: string | null;
  majorSummary?: PlannerProfileHintsSummary | null;
  progressMessage: string;
  progressMode?: "start" | "branching" | "execute";
  wizardSteps: PlannerWizardStep[];
  wizardIndex: number;
  progressCurrent?: number;
  progressEstimatedTotal?: number;
  plannerHeader?: PlannerHeaderMeta | null;
  plannerMajorSource?: "user_override" | "inferred" | string;
  plannerStepHeader?: { path_label?: string; reason?: string } | null;
  wizardAnswers: Record<string, string>;
  plannerCanGenerateNow: boolean;
  plannerPathSummary: string;
  plannerDocs: Array<{ id: number; title: string }>;
  embeddedDocs: Array<{ id: number; title: string }>;
  selectedDocIds: number[];
  selectedDocTitles: string[];
  docPickerOpen: boolean;
  loading: boolean;
  deletingDocId: number | null;
  plannerWarning?: string | null;
  onUploadNew: () => void;
  onOpenDocPicker: () => void;
  onConfirmDocPicker: (ids: number[]) => void;
  onCloseDocPicker: () => void;
  onClearDocSelection: () => void;
  onSelectOption: (value: string) => void;
  onChangeManual: (value: string) => void;
  onNext: () => void;
  onBack: () => void;
  onEdit: (stepKey: string) => void;
  onExecute: () => void;
}) {
  const disabled = loading || deletingDocId !== null;

  if (state === "onboarding") {
    return (
      <>
        <PlannerOnboardingCard
          hasEmbeddedDocs={hasEmbeddedDocs}
          onUploadNew={onUploadNew}
          onOpenDocPicker={onOpenDocPicker}
          relevanceError={relevanceError}
          majorSummary={majorSummary}
          selectedDocTitles={selectedDocTitles}
          selectedDocCount={selectedDocIds.length}
          onClearDocSelection={onClearDocSelection}
          disabled={disabled}
        />
        <PlannerDocPickerSheet
          open={docPickerOpen}
          docs={embeddedDocs}
          selectedIds={selectedDocIds}
          onClose={onCloseDocPicker}
          onConfirm={onConfirmDocPicker}
          onClear={onClearDocSelection}
        />
      </>
    );
  }

  if (state === "uploading" || state === "branching" || state === "executing") {
    return <PlannerProgressOverlay message={progressMessage} mode={progressMode} />;
  }

  if (state === "ready" && wizardSteps[wizardIndex]) {
    const step = wizardSteps[wizardIndex];
    return (
      <PlannerWizardCard
        step={step}
        index={wizardIndex}
        total={progressEstimatedTotal || wizardSteps.length}
        progressCurrent={progressCurrent}
        progressTotal={progressEstimatedTotal}
        showMajorHeader={wizardIndex === 0}
        majorLabel={plannerHeader?.major_label || majorSummary?.major_candidates?.[0]?.label || ""}
        majorConfidenceLevel={
          plannerMajorSource === "user_override"
            ? "high"
            : (plannerHeader?.major_confidence_level || majorSummary?.confidence_summary || "low")
        }
        pathLabel={plannerStepHeader?.path_label || plannerPathSummary}
        stepReason={plannerStepHeader?.reason || step.reason || ""}
        value={wizardAnswers[step.step_key] || ""}
        onSelectOption={onSelectOption}
        onChangeManual={onChangeManual}
        onNext={onNext}
        onBack={onBack}
        canGenerateNow={plannerCanGenerateNow}
        onGenerateNow={onExecute}
        pathSummary={plannerPathSummary}
        disabled={disabled}
      />
    );
  }

  if (state === "reviewing") {
    return (
      <PlannerReviewCard
        answers={wizardAnswers}
        docs={plannerDocs}
        majorLabel={plannerHeader?.major_label || majorSummary?.major_candidates?.[0]?.label || ""}
        majorSource={plannerMajorSource}
        onEdit={onEdit}
        onExecute={onExecute}
        executing={loading}
      />
    );
  }

  if (plannerWarning) {
    return (
      <div className="mx-auto w-[min(900px,92%)] rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/35 dark:text-amber-300">
        {plannerWarning}
      </div>
    );
  }

  return null;
}
