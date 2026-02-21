export default function PlannerProgressOverlay({ message }: { message: string }) {
  return (
    <div className="mx-auto mb-4 w-[min(900px,92%)] rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm font-medium text-blue-800 dark:border-blue-900/50 dark:bg-blue-950/35 dark:text-blue-200">
      {message}
    </div>
  );
}
