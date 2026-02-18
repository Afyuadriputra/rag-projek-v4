import { cn } from "@/lib/utils";

export default function Toast({
  open,
  kind,
  message,
  onClose,
}: {
  open: boolean;
  kind: "success" | "error";
  message: string;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div data-testid="toast" className="fixed top-20 right-6 z-[999]">
      <div
        className={cn(
          "glass-card rounded-2xl px-4 py-3 border shadow-sm min-w-[280px] max-w-[420px]",
          kind === "success" ? "border-black/10" : "border-black/10"
        )}
      >
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined text-[20px]">
            {kind === "success" ? "check_circle" : "error"}
          </span>
          <div className="flex-1">
            <div className="text-[11px] uppercase tracking-widest text-zinc-500 font-semibold mb-1">
              {kind === "success" ? "Success" : "Error"}
            </div>
            <div data-testid="toast-message" className="text-[13px] text-zinc-700">{message}</div>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-black">
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      </div>
    </div>
  );
}
