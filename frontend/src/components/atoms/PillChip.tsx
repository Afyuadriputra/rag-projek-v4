import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type PillVariant = "default" | "info" | "warn" | "success";

const variantClass: Record<PillVariant, string> = {
  default: "border-zinc-300/80 text-zinc-700 dark:border-zinc-600 dark:text-zinc-200",
  info: "border-sky-300/80 bg-sky-50/60 text-sky-700 dark:border-sky-900/60 dark:bg-sky-950/25 dark:text-sky-300",
  warn: "border-rose-300/80 bg-rose-50/65 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/25 dark:text-rose-300",
  success:
    "border-emerald-300/80 bg-emerald-50/65 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/25 dark:text-emerald-300",
};

export default function PillChip({
  className,
  children,
  variant = "default",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: PillVariant }) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold",
        variantClass[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
