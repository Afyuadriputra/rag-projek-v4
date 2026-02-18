import { cn } from "@/lib/utils";

type ToggleProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
};

export function Toggle({ checked, onChange, className }: ToggleProps) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "w-[42px] h-6 bg-[#E5E5E5] rounded-full relative cursor-pointer transition-all duration-300",
        className
      )}
      aria-pressed={checked}
      aria-label="Toggle theme"
    >
      <span
        className={cn(
          "absolute top-[2px] size-5 bg-white rounded-full shadow-sm transition-all duration-300",
          checked ? "left-[20px]" : "left-[2px]"
        )}
      />
    </button>
  );
}
