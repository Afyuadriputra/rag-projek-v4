import React from "react";
import { cn } from "@/lib/utils";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: string; // material symbols name
  size?: "sm" | "md" | "lg";
};

const sizeClass: Record<NonNullable<Props["size"]>, string> = {
  sm: "p-2",
  md: "p-2.5",
  lg: "p-3.5",
};

export default function IconButton({
  icon,
  size = "md",
  className,
  ...rest
}: Props) {
  return (
    <button
      className={cn(
        "rounded-xl transition-colors inline-flex items-center justify-center",
        "text-zinc-400 hover:text-black hover:bg-black/5",
        sizeClass[size],
        className
      )}
      {...rest}
    >
      <span className="material-symbols-outlined text-[22px] font-light">
        {icon}
      </span>
    </button>
  );
}
