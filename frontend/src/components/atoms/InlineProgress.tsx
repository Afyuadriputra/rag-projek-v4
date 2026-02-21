import { cn } from "@/lib/utils";

export default function InlineProgress({
  message,
  className,
}: {
  message: string;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-200">
        <span className="size-3 animate-spin rounded-full border-2 border-zinc-400/50 border-t-zinc-700 dark:border-zinc-600 dark:border-t-zinc-200" />
        {message}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-200/70 dark:bg-zinc-700/80">
        <div className="h-full w-1/3 animate-[planner_progress_1.2s_ease-in-out_infinite] rounded-full bg-zinc-700/80 dark:bg-zinc-200/85" />
      </div>
      <style>{`@keyframes planner_progress{0%{transform:translateX(-120%)}100%{transform:translateX(320%)}}`}</style>
    </div>
  );
}
