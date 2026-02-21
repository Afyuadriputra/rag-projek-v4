import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export default function GlassCard({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-3xl border border-white/35 bg-white/55 p-5 shadow-[0_10px_35px_-18px_rgba(20,20,30,0.35)] backdrop-blur-xl",
        "before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-16 before:bg-gradient-to-b before:from-white/55 before:to-transparent",
        "dark:border-zinc-700/55 dark:bg-zinc-900/45",
        className
      )}
      {...props}
    />
  );
}
