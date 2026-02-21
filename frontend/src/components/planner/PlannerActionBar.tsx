import { cn } from "@/lib/utils";

export default function PlannerActionBar({
  leftLabel,
  rightLabel,
  leftDisabled,
  rightDisabled,
  onLeft,
  onRight,
}: {
  leftLabel: string;
  rightLabel: string;
  leftDisabled?: boolean;
  rightDisabled?: boolean;
  onLeft: () => void;
  onRight: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <button
        type="button"
        onClick={onLeft}
        disabled={leftDisabled}
        className="min-h-11 rounded-2xl border border-zinc-300/85 bg-white/60 px-3.5 py-2 text-xs font-semibold text-zinc-700 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900/35 dark:text-zinc-200 dark:hover:bg-zinc-900/70"
      >
        {leftLabel}
      </button>
      <button
        type="button"
        onClick={onRight}
        disabled={rightDisabled}
        className={cn(
          "min-h-11 rounded-2xl px-4 py-2 text-xs font-semibold text-white transition",
          "bg-zinc-900 hover:bg-black disabled:cursor-not-allowed disabled:opacity-50",
          "dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        )}
      >
        {rightLabel}
      </button>
    </div>
  );
}
