export default function PlannerRelevanceAlert({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-amber-300/80 bg-amber-50/75 px-4 py-3 text-sm font-medium text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
      {message}
    </div>
  );
}
