"use client";

import { createClient } from "@/lib/supabase/client";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) router.replace("/");
    });
  }, [router, supabase]);

  async function handleEmailAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    setIsSubmitting(true);

    const authResult =
      mode === "sign-in"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });

    setIsSubmitting(false);

    if (authResult.error) {
      setErrorMessage(authResult.error.message);
      return;
    }

    router.replace("/");
  }

  async function handleGoogleLogin() {
    setErrorMessage("");

    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        scopes: "https://www.googleapis.com/auth/calendar.events",
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) setErrorMessage(error.message);
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-herald-bg">
      <div className="bg-white/[0.88] rounded-herald shadow-herald-soft p-10 flex flex-col items-center gap-6 w-full max-w-sm animate-section-in">
        <div className="text-center">
          <h1 className="text-[1.8rem] text-herald-text">Herald</h1>
          <p className="text-herald-muted mt-1 text-sm font-light">
            UCSD event discovery
          </p>
        </div>

        <div className="flex w-full rounded-herald-sm bg-herald-surface-soft p-1">
          <button
            type="button"
            onClick={() => {
              setMode("sign-in");
              setErrorMessage("");
            }}
            className={`flex-1 rounded-herald-sm px-3 py-2 text-sm font-bold transition-colors ${
              mode === "sign-in"
                ? "bg-white text-herald-text shadow-sm"
                : "text-herald-muted-hard hover:text-herald-text"
            }`}
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("sign-up");
              setErrorMessage("");
            }}
            className={`flex-1 rounded-herald-sm px-3 py-2 text-sm font-bold transition-colors ${
              mode === "sign-up"
                ? "bg-white text-herald-text shadow-sm"
                : "text-herald-muted-hard hover:text-herald-text"
            }`}
          >
            Sign up
          </button>
        </div>

        <form onSubmit={handleEmailAuth} className="flex w-full flex-col gap-3">
          <label className="flex flex-col gap-1.5 text-sm font-bold text-herald-muted-hard">
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
              className="rounded-herald-sm border border-herald-muted-soft bg-white px-3 py-2.5 text-sm font-light text-herald-text outline-none transition-colors focus:border-herald-accent"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-bold text-herald-muted-hard">
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={
                mode === "sign-in" ? "current-password" : "new-password"
              }
              required
              className="rounded-herald-sm border border-herald-muted-soft bg-white px-3 py-2.5 text-sm font-light text-herald-text outline-none transition-colors focus:border-herald-accent"
            />
          </label>

          {errorMessage ? (
            <p className="text-sm font-light text-red-600">{errorMessage}</p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-herald-sm bg-herald-accent px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-herald-navy disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting
              ? "Please wait..."
              : mode === "sign-in"
                ? "Sign in"
                : "Sign up"}
          </button>
        </form>

        <div className="flex w-full items-center gap-3 text-xs uppercase tracking-wide text-herald-muted">
          <div className="h-px flex-1 bg-herald-muted-soft" />
          or
          <div className="h-px flex-1 bg-herald-muted-soft" />
        </div>

        <button
          onClick={handleGoogleLogin}
          className="flex items-center gap-3 w-full justify-center border border-herald-muted-soft rounded-herald-sm px-4 py-2.5 text-sm font-bold text-herald-muted-hard hover:bg-herald-surface-soft transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          Continue with Google
        </button>
      </div>
    </main>
  );
}
