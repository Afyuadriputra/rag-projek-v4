import { useState } from "react";
import { Link } from "@inertiajs/react"; // Import Link untuk navigasi Inertia
import NavTabs from "@/components/molecules/NavTabs";
import ToggleSwitch from "@/components/atoms/ToggleSwitch";
import Avatar from "@/components/atoms/Avatar";
import { cn } from "@/lib/utils";

export default function AppHeader({
  dark,
  onToggleDark,
  mode,
  onModeChange,
  modeDisabled = false,
  user, // Update: Menerima object user lengkap, bukan cuma username
}: {
  dark: boolean;
  onToggleDark: (v: boolean) => void;
  mode: "chat" | "planner";
  onModeChange: (mode: "chat" | "planner") => void;
  modeDisabled?: boolean;
  user: { username: string; email: string };
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header
      className={cn(
        "sticky top-0 z-20 flex h-16 w-full flex-none items-center justify-between px-4 transition-all md:px-8",
        "bg-white/60 backdrop-blur-xl backdrop-saturate-150",
        "border-b border-white/20 shadow-[0_4px_30px_rgba(0,0,0,0.03)]"
      )}
    >
      {/* --- LEFT SECTION (Logo) --- */}
      <div className="flex items-center gap-3 pl-12 md:pl-0">
        <div className="group flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-zinc-800 to-black shadow-lg shadow-black/20 transition-transform duration-500 hover:rotate-6 hover:scale-105">
          <span className="material-symbols-outlined text-[20px] font-light text-white">
            school
          </span>
        </div>
        <h1 className="hidden text-[13px] font-semibold tracking-[0.2em] text-zinc-800 uppercase sm:block">
          Academic AI
        </h1>
      </div>

      {/* --- CENTER SECTION (Nav) --- */}
      <div className="absolute left-1/2 hidden -translate-x-1/2 md:flex md:items-center md:gap-3">
        <NavTabs active="Chat" />
        <div className="flex items-center rounded-full border border-white/40 bg-white/55 p-1 shadow-sm backdrop-blur-md">
          <button
            data-testid="mode-chat"
            type="button"
            disabled={modeDisabled}
            onClick={() => onModeChange("chat")}
            className={cn(
              "rounded-full px-3 py-1 text-[11px] font-semibold tracking-wide transition",
              mode === "chat" ? "bg-zinc-900 text-white" : "text-zinc-600 hover:text-zinc-900",
              modeDisabled && "cursor-not-allowed opacity-60"
            )}
          >
            💬 Chat
          </button>
          <button
            data-testid="mode-planner"
            type="button"
            disabled={modeDisabled}
            onClick={() => onModeChange("planner")}
            className={cn(
              "rounded-full px-3 py-1 text-[11px] font-semibold tracking-wide transition",
              mode === "planner" ? "bg-zinc-900 text-white" : "text-zinc-600 hover:text-zinc-900",
              modeDisabled && "cursor-not-allowed opacity-60"
            )}
          >
            📋 Plan
          </button>
        </div>
      </div>

      {/* --- RIGHT SECTION (Actions) --- */}
      <div className="flex items-center gap-3 md:gap-5">
        <div className="flex items-center rounded-full border border-white/40 bg-white/55 p-1 shadow-sm backdrop-blur-md md:hidden">
          <button
            data-testid="mode-chat-mobile"
            type="button"
            disabled={modeDisabled}
            onClick={() => onModeChange("chat")}
            className={cn(
              "rounded-full px-2.5 py-1 text-[10px] font-semibold transition",
              mode === "chat" ? "bg-zinc-900 text-white" : "text-zinc-600",
              modeDisabled && "cursor-not-allowed opacity-60"
            )}
          >
            💬
          </button>
          <button
            data-testid="mode-planner-mobile"
            type="button"
            disabled={modeDisabled}
            onClick={() => onModeChange("planner")}
            className={cn(
              "rounded-full px-2.5 py-1 text-[10px] font-semibold transition",
              mode === "planner" ? "bg-zinc-900 text-white" : "text-zinc-600",
              modeDisabled && "cursor-not-allowed opacity-60"
            )}
          >
            📋
          </button>
        </div>
        
        {/* Control Group */}
        <div className="flex items-center gap-1 rounded-full border border-white/40 bg-white/40 p-1 pr-3 backdrop-blur-md shadow-sm">
          <div className="flex items-center gap-2 pl-1">
             <span className="material-symbols-outlined text-[16px] text-zinc-400">
                {dark ? "dark_mode" : "light_mode"}
             </span>
             <ToggleSwitch checked={dark} onChange={onToggleDark} />
          </div>
          <div className="mx-2 h-4 w-px bg-zinc-300/50" />
          <button className="group relative flex size-8 items-center justify-center rounded-full transition-colors hover:bg-black/5">
            <span className="material-symbols-outlined text-[20px] text-zinc-500 transition-colors group-hover:text-zinc-800">
              notifications
            </span>
            <span className="absolute right-1.5 top-1.5 size-2 rounded-full border border-white bg-red-500 shadow-sm" />
          </button>
        </div>

        {/* Profile Section with Dropdown */}
        <div className="relative">
            <button 
                data-testid="user-menu-button"
                onClick={() => setMenuOpen(!menuOpen)}
                className="flex items-center gap-3 outline-none"
            >
                <div className="hidden text-right md:block">
                    <p className="text-[12px] font-semibold text-zinc-700 leading-tight">
                        {user.username}
                    </p>
                    <p className="text-[10px] text-zinc-400 font-medium tracking-wide uppercase">
                        Mahasiswa
                    </p>
                </div>
                
                <div className="relative transition-transform hover:scale-105 active:scale-95">
                    <div className={cn("rounded-full border-2 shadow-md transition-colors", menuOpen ? "border-black" : "border-white")}>
                        <Avatar imageUrl="https://lh3.googleusercontent.com/aida-public/AB6AXuAoTjR3RYjL2AEMA-cRAUKJ2RD9-jLlLh15wfkA75ckExydx9hpo_jeGgce18JPCU0vo2ys5ZiQ_EaSug1uZKAqe-BMsENRTlrSGbbQGssUNxu_ZfX0zw7Cel15Rdz7KFpT2MAHeD1cz-Z0cBnD0ClUnQxb1XklqULYuxZLy9UxbawMuBMdCQrDfL6Z81vJPpKPlgCzsPTfbCum3Xvjd8uuD6MEMnfJPr--MZ4Ap6HlFui0hshnJJ6Bvta7btSimet0VXW9ql3bBC_l" />
                    </div>
                    <div className="absolute bottom-0 right-0 size-2.5 rounded-full border-[1.5px] border-white bg-green-500 shadow-sm" />
                </div>
            </button>

            {/* --- DROPDOWN MENU (LOGOUT) --- */}
            {menuOpen && (
                <>
                    {/* Backdrop untuk menutup menu saat klik luar */}
                    <div 
                        className="fixed inset-0 z-30 cursor-default" 
                        onClick={() => setMenuOpen(false)} 
                    />
                    
                    {/* Menu Content */}
                    <div className="absolute right-0 top-full z-40 mt-3 w-56 overflow-hidden rounded-2xl border border-white/40 bg-white/80 p-1 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-200">
                        <div className="px-4 py-3 border-b border-black/5">
                            <p className="text-xs font-medium text-zinc-500">Masuk sebagai</p>
                            <p className="truncate text-sm font-bold text-zinc-900">{user.email}</p>
                        </div>
                        
                        <div className="p-1">
                            <Link
                                data-testid="logout-link"
                                href="/logout/" // Sesuai endpoint Django
                                className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
                            >
                                <span className="material-symbols-outlined text-[18px]">logout</span>
                                Keluar
                            </Link>
                        </div>
                    </div>
                </>
            )}
        </div>

      </div>
    </header>
  );
}
