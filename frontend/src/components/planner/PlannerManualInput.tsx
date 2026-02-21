export default function PlannerManualInput({
  value,
  disabled,
  placeholder = "Atau tulis manual...",
  onChange,
}: {
  value: string;
  disabled?: boolean;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <textarea
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={3}
      className="w-full rounded-2xl border border-zinc-300/90 bg-white/65 p-3 text-sm text-zinc-800 backdrop-blur-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60 dark:border-zinc-600 dark:bg-zinc-900/40 dark:text-zinc-100"
    />
  );
}
