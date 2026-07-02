"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

const VALID_USERNAME = "xicmo123";
const VALID_PASSWORD = "afeck123";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (username.trim() !== VALID_USERNAME || password !== VALID_PASSWORD) {
      setError("帳號或密碼錯誤");
      return;
    }

    setLoading(true);

    document.cookie = `auth_session=true; path=/; max-age=${60 * 60 * 24 * 7}; samesite=lax`;

    router.push("/");
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 px-4 py-10 text-slate-900">
      <div className="mx-auto flex w-full max-w-lg flex-col gap-8">
        <section className="rounded-[2rem] border border-slate-200/70 bg-white/95 px-8 py-10 shadow-[0_25px_80px_-40px_rgba(15,23,42,0.3)] backdrop-blur-xl">
          <div className="mb-8 space-y-3 text-center">
            <p className="text-sm uppercase tracking-[0.3em] text-slate-500">NetWorth Tracker</p>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">資產管理中心</h1>
            <p className="mx-auto max-w-xs text-sm leading-6 text-slate-600">
              請登入以存取您的資產管理中心。
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="username" className="mb-2 block text-sm font-medium text-slate-700">
                帳號
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                placeholder="請輸入帳號"
                autoComplete="username"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
                密碼
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                placeholder="請輸入密碼"
                autoComplete="current-password"
                required
              />
            </div>

            {error ? (
              <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-rose-100">
                {error}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="inline-flex w-full items-center justify-center rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {loading ? "登入中..." : "登入"}
            </button>
          </form>

          
        </section>
      </div>
    </main>
  );
}
