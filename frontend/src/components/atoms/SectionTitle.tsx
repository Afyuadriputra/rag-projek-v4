import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export default function SectionTitle({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100", className)} {...props}>
      {children}
    </h3>
  );
}
