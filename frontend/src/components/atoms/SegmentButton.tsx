import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export default function SegmentButton({
  className,
  active = false,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      className={cn(
        "min-h-11 rounded-2xl border px-3.5 py-2.5 text-left text-xs font-semibold transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70",
        active
          ? "border-zinc-900 bg-zinc-900 text-white shadow-sm dark:border-zinc-200 dark:bg-zinc-100 dark:text-zinc-900"
          : "border-zinc-300/80 bg-white/60 text-zinc-700 hover:bg-white dark:border-zinc-600 dark:bg-zinc-900/40 dark:text-zinc-200 dark:hover:bg-zinc-900/70",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    />
  );
}
