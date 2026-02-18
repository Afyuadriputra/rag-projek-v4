import { cn } from "@/lib/utils";

export default function NavTabs({
  active = "Chat",
}: {
  active?: "Dashboard" | "Chat" | "Settings";
}) {
  const tabs: Array<typeof active> = ["Dashboard", "Chat", "Settings"];
  return (
    <div className="hidden md:flex items-center gap-6 text-[13px] font-medium tracking-wide text-zinc-500">
      {tabs.map((t) => (
        <button
          key={t}
          className={cn(
            "transition-colors duration-300",
            t === active
              ? "text-black border-b border-black pb-0.5"
              : "hover:text-black"
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
