import React, { useState } from "react";
import { router, Link } from "@inertiajs/react";
import { cn } from "@/lib/utils";

export default function Register({
  errors,
  registration_enabled = true,
}: {
  errors?: Record<string, string>;
  registration_enabled?: boolean;
}) {
  const [values, setValues] = useState({
    username: "",
    email: "",
    password: "",
    password_confirmation: "",
  });

  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValues({ ...values, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    router.post("/register/", values, {
      onFinish: () => setLoading(false),
    });
  };

  return (
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-zinc-50 font-sans text-zinc-900 selection:bg-black selection:text-white">
      {/* --- AMBIENT BACKGROUND (Different Hue) --- */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -right-[10%] -top-[10%] h-[50vh] w-[50vw] rounded-full bg-indigo-100/40 blur-[100px]" />
        <div className="absolute -bottom-[10%] -left-[10%] h-[50vh] w-[50vw] rounded-full bg-pink-100/40 blur-[100px]" />
      </div>

      {/* --- CARD CONTAINER --- */}
      <div className="relative z-10 w-full max-w-[420px] px-4 py-8">
        <div className="overflow-hidden rounded-3xl border border-white/40 bg-white/60 p-8 shadow-2xl backdrop-blur-2xl backdrop-saturate-150">
          
          {/* Header */}
          <div className="mb-6 text-center">
            <h1 className="text-xl font-bold tracking-tight text-zinc-900">
              Buat Akun Baru
            </h1>
            <p className="mt-2 text-sm text-zinc-500 font-medium">
              Mulai perjalanan akademikmu dengan AI.
            </p>
          </div>

          {/* Form */}
          {registration_enabled ? (
          <form onSubmit={handleSubmit} className="space-y-4">
             {/* General Error */}
             {errors?.auth && (
              <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50/80 p-3 text-center text-xs font-medium text-red-600 backdrop-blur-sm">
                <span className="material-symbols-outlined text-[16px]">error</span>
                {errors.auth}
              </div>
            )}

            <div className="space-y-3">
              {/* Username */}
              <div>
                <label className="mb-1 block text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                  Username
                </label>
                <input
                  type="text"
                  name="username"
                  value={values.username}
                  onChange={handleChange}
                  className="w-full rounded-xl border border-black/5 bg-white/50 px-4 py-2.5 text-sm font-medium text-zinc-900 outline-none transition-all placeholder:text-zinc-400 focus:border-black/20 focus:bg-white/80 focus:ring-0"
                  placeholder="username_mhs"
                  required
                />
                {errors?.username && (
                  <p className="mt-1 text-xs font-medium text-red-500">{errors.username}</p>
                )}
              </div>

              {/* Email */}
              <div>
                <label className="mb-1 block text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                  Email
                </label>
                <input
                  type="email"
                  name="email"
                  value={values.email}
                  onChange={handleChange}
                  className="w-full rounded-xl border border-black/5 bg-white/50 px-4 py-2.5 text-sm font-medium text-zinc-900 outline-none transition-all placeholder:text-zinc-400 focus:border-black/20 focus:bg-white/80 focus:ring-0"
                  placeholder="nama@kampus.ac.id"
                  required
                />
                {errors?.email && (
                  <p className="mt-1 text-xs font-medium text-red-500">{errors.email}</p>
                )}
              </div>

              {/* Password */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="mb-1 block text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                    Password
                    </label>
                    <input
                    type="password"
                    name="password"
                    value={values.password}
                    onChange={handleChange}
                    className="w-full rounded-xl border border-black/5 bg-white/50 px-4 py-2.5 text-sm font-medium text-zinc-900 outline-none transition-all placeholder:text-zinc-400 focus:border-black/20 focus:bg-white/80 focus:ring-0"
                    placeholder="••••••••"
                    required
                    />
                </div>
                <div>
                    <label className="mb-1 block text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                    Konfirmasi
                    </label>
                    <input
                    type="password"
                    name="password_confirmation"
                    value={values.password_confirmation}
                    onChange={handleChange}
                    className="w-full rounded-xl border border-black/5 bg-white/50 px-4 py-2.5 text-sm font-medium text-zinc-900 outline-none transition-all placeholder:text-zinc-400 focus:border-black/20 focus:bg-white/80 focus:ring-0"
                    placeholder="••••••••"
                    required
                    />
                </div>
              </div>
              {/* Error Password Group */}
              {(errors?.password || errors?.password_confirmation) && (
                  <p className="text-xs font-medium text-red-500">
                    {errors?.password || errors?.password_confirmation}
                  </p>
               )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className={cn(
                "mt-2 group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-black py-3.5 text-sm font-semibold text-white shadow-lg transition-all hover:bg-zinc-800 hover:shadow-xl active:scale-[0.98]",
                loading && "cursor-not-allowed opacity-70"
              )}
            >
              {loading ? (
                <>
                  <span className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Mendaftarkan...
                </>
              ) : (
                <>
                  Buat Akun
                  <span className="material-symbols-outlined text-[18px]">
                    check_circle
                  </span>
                </>
              )}
            </button>
          </form>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs font-medium text-amber-700 backdrop-blur-sm">
                <span className="material-symbols-outlined text-[16px]">block</span>
                Pendaftaran akun baru saat ini dinonaktifkan oleh admin.
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="mt-6 text-center text-xs text-zinc-500 font-medium">
            Sudah punya akun?{" "}
            <Link
              href="/login/"
              className="font-bold text-black underline decoration-zinc-300 underline-offset-4 transition hover:text-zinc-600"
            >
              Masuk di sini
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
