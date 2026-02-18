import React from "react";
import { cn } from "@/lib/utils";

export default function Badge({
  children,
  className,
}: React.PropsWithChildren<{ className?: string }>) {
  return (
    <span
      className={cn(
        "px-4 py-1 rounded-full bg-black/5 text-[10px] font-medium uppercase",
        "tracking-[0.2em] text-zinc-500 border border-black/5",
        className
      )}
    >
      {children}
    </span>
  );
}
