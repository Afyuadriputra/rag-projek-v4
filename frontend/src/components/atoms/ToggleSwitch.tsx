import { cn } from "@/lib/utils";

export default function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "w-[42px] h-6 rounded-full relative transition-all",
        checked ? "bg-black/80" : "bg-[#E5E5E5]"
      )}
    >
      <span
        className={cn(
          "absolute top-[2px] size-5 rounded-full bg-white shadow-sm transition-all",
          checked ? "left-[20px]" : "left-[2px]"
        )}
      />
    </button>
  );
}
