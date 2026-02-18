import { cn } from "@/lib/utils";

function bytesToMB(bytes: number) {
  return bytes / (1024 * 1024);
}

function fmtMB(bytes: number) {
  const mb = bytesToMB(bytes);
  if (mb < 10) return `${mb.toFixed(2)} MB`;
  if (mb < 100) return `${mb.toFixed(1)} MB`;
  return `${mb.toFixed(0)} MB`;
}

export default function ProgressBar({
  value, // 0..100
  usedBytes,
  quotaBytes,
  className,
}: {
  value: number;
  usedBytes?: number;
  quotaBytes?: number;
  className?: string;
}) {
  const v = Math.max(0, Math.min(100, value));
  
  // Logic: Hitam elegan normalnya, Merah jika kritis (>90%)
  const isCritical = v > 90;
  const barColor = isCritical 
    ? "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.4)]" 
    : "bg-zinc-900 shadow-[0_2px_10px_rgba(0,0,0,0.15)]";

  const hasCaps =
    typeof usedBytes === "number" && typeof quotaBytes === "number" && quotaBytes > 0;

  const tooltipText = hasCaps
    ? `${fmtMB(usedBytes!)} / ${fmtMB(quotaBytes!)}`
    : `${v.toFixed(0)}%`;

  return (
    <div className={cn("group relative w-full", className)}>
      {/* 1. Track (Background Lintasan) */}
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200/50 backdrop-blur-sm">
        
        {/* 2. Fill (Isian dengan Animasi Liquid) */}
        <div
          className={cn(
            "relative h-full rounded-full transition-all duration-1000 cubic-bezier(0.4, 0, 0.2, 1)", // Efek pegas halus
            barColor
          )}
          style={{ width: `${v}%` }}
        >
          {/* Liquid Shine (Kilau Kaca di bagian atas bar) */}
          <div className="absolute inset-x-0 top-0 h-[50%] bg-gradient-to-b from-white/30 to-transparent opacity-80" />
          
          {/* Subtle Pulse (Hanya jika kritis) */}
          {isCritical && (
             <div className="absolute inset-0 animate-pulse bg-white/20" />
          )}
        </div>
      </div>

      {/* 3. Floating Tooltip (Muncul saat Hover) */}
      <div
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2",
          "scale-90 opacity-0 transition-all duration-300 ease-out",
          "group-hover:scale-100 group-hover:opacity-100 group-hover:-translate-y-1"
        )}
      >
        <div className="relative flex items-center gap-2 rounded-lg bg-zinc-900/90 px-3 py-1.5 text-xs font-medium text-white shadow-xl backdrop-blur-md">
            {/* Tiny Arrow */}
            <div className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-zinc-900/90" />
            
            <span className="material-symbols-outlined text-[14px] text-zinc-400">
                database
            </span>
            <span>{tooltipText}</span>
        </div>
      </div>
    </div>
  );
}