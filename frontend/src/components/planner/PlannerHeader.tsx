import SectionTitle from "@/components/atoms/SectionTitle";
import PillChip from "@/components/atoms/PillChip";
import { cn } from "@/lib/utils";

export default function PlannerHeader({
  title,
  subtitle,
  rightLabel,
  className,
}: {
  title: string;
  subtitle?: string;
  rightLabel?: string;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-3", className)}>
      <div className="space-y-1">
        <SectionTitle>{title}</SectionTitle>
        {subtitle && <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">{subtitle}</p>}
      </div>
      {rightLabel && <PillChip variant="info">{rightLabel}</PillChip>}
    </div>
  );
}
