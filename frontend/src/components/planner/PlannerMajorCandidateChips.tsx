import PillChip from "@/components/atoms/PillChip";
import type { PlannerProfileHintsSummary } from "@/lib/api";

export default function PlannerMajorCandidateChips({
  majorSummary,
}: {
  majorSummary?: PlannerProfileHintsSummary | null;
}) {
  if (!majorSummary?.major_candidates?.length) return null;
  const confidence = (majorSummary.confidence_summary || "").toLowerCase();
  const confidenceLabel =
    confidence === "high" ? "tinggi" : confidence === "medium" ? "sedang" : confidence === "low" ? "rendah" : "";

  return (
    <div className="space-y-2 rounded-2xl border border-sky-300/65 bg-sky-50/60 p-3 dark:border-sky-900/50 dark:bg-sky-950/25">
      <p className="text-xs font-semibold text-sky-900 dark:text-sky-200">
        Kandidat jurusan terdeteksi{confidenceLabel ? ` (confidence ${confidenceLabel})` : ""}:
      </p>
      <div className="flex flex-wrap gap-2">
        {majorSummary.major_candidates.slice(0, 3).map((c, idx) => (
          <PillChip key={`${String(c.value)}-${idx}`} variant="info">
            {c.label}
          </PillChip>
        ))}
      </div>
    </div>
  );
}
