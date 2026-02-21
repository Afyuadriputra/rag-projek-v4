import SegmentButton from "@/components/atoms/SegmentButton";

type PlannerOption = { id: number; label: string; value: string };

export default function PlannerOptionList({
  options,
  value,
  disabled,
  onSelect,
}: {
  options: PlannerOption[];
  value: string;
  disabled?: boolean;
  onSelect: (value: string) => void;
}) {
  return (
    <div className="grid gap-2">
      {options.map((opt) => (
        <SegmentButton
          key={opt.id}
          type="button"
          active={value === String(opt.value)}
          disabled={disabled}
          onClick={() => onSelect(String(opt.value))}
        >
          {opt.label}
        </SegmentButton>
      ))}
    </div>
  );
}
