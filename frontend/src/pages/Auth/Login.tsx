import React, { useState } from "react";
import { router, Link } from "@inertiajs/react";
import { cn } from "@/lib/utils";

export default function Login({
  errors,
  registration_enabled = true,
}: {
  errors?: Record<string, string>;
  registration_enabled?: boolean;
}) {
  const [values, setValues] = useState({
    username: "",
    password: "",
  });

  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValues({ ...values, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    router.post("/login/", values, {
      onFinish: () => setLoading(false),
    });
  };

  return (
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-zinc-50 font-sans text-zinc-900 selection:bg-black selection:text-white">
      {/* --- AMBIENT BACKGROUND --- */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -left-[10%] -top-[10%] h-[50vh] w-[50vw] rounded-full bg-blue-100/40 blur-[100px]" />
        <div className="absolute -bottom-[10%] -right-[10%] h-[50vh] w-[50vw] rounded-full bg-purple-100/40 blur-[100px]" />
      </div>

      {/* --- CARD CONTAINER --- */}
      <div className="relative z-10 w-full max-w-[400px] px-4">
        <div className="overflow-hidden rounded-3xl border border-white/40 bg-white/60 p-8 shadow-2xl backdrop-blur-2xl backdrop-saturate-150">

          {/* Header */}
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-black text-white shadow-lg shadow-black/20">
              <span className="material-symbols-outlined text-[24px]">school</span>
            </div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900">
              Welcome Back
            </h1>
            <p className="mt-2 text-sm text-zinc-500 font-medium">
              Masuk untuk melanjutkan analisis akademikmu.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {errors?.auth && (
              <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50/80 p-3 text-xs font-medium text-red-600">
                <span className="material-symbols-outlined text-[16px]">error</span>
                {errors.auth}
              </div>
            )}

            <div className="space-y-4">
              {/* Username */}
              <div>
                <label className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Username
                </label>
                <div className="relative">
                  <input
                    data-testid="login-username"
                    type="text"
                    name="username"
                    value={values.username}
                    onChange={handleChange}
                    className="w-full rounded-xl border border-black/5 bg-white/50 px-4 py-3 pl-10 text-sm font-medium text-zinc-900 outline-none transition-all placeholder:text-zinc-400 focus:border-black/20 focus:bg-white/80 focus:ring-0"
                    placeholder="Masukkan username"
                    required
                  />
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-zinc-400">
                    person
                  </span>
                </div>
              </div>

              {/* Password */}
              <div>
                <label className="mb-1.5 block text-xs font-bold uppercase tracking-wider text-zinc-400">
                  Password
                </label>
                <div className="relative">
                  <input
                    data-testid="login-password"
                    type="password"
                    name="password"
                    value={values.password}
                    onChange={handleChange}
                    className="w-full rounded-xl border border-black/5 bg-white/50 px-4 py-3 pl-10 text-sm font-medium text-zinc-900 outline-none transition-all placeholder:text-zinc-400 focus:border-black/20 focus:bg-white/80 focus:ring-0"
                    placeholder="••••••••"
                    required
                  />
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-zinc-400">
                    lock
                  </span>
                </div>
              </div>
            </div>

            {/* Submit */}
            <button
              data-testid="login-submit"
              type="submit"
              disabled={loading}
              className={cn(
                "group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-black py-3.5 text-sm font-semibold text-white shadow-lg transition-all hover:bg-zinc-800 hover:shadow-xl active:scale-[0.98]",
                loading && "cursor-not-allowed opacity-70"
              )}
            >
              {loading ? (
                <>
                  <span className="size-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Memproses...
                </>
              ) : (
                <>
                  Masuk
                  <span className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-0.5">
                    arrow_forward
                  </span>
                </>
              )}
            </button>
          </form>

          {/* Footer */}
          <div className="mt-8 text-center text-xs text-zinc-500 font-medium">
            {registration_enabled ? (
              <>
                Belum punya akun?{" "}
                <Link
                  href="/register/"
                  className="font-bold text-black underline decoration-zinc-300 underline-offset-4 transition hover:text-zinc-600"
                >
                  Daftar Sekarang
                </Link>
              </>
            ) : (
              <span className="text-zinc-500">Pendaftaran akun baru sedang dinonaktifkan admin.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
