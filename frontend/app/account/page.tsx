import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { redirect } from "next/navigation";
import Header from "@/components/Header";
import FooterNav from "@/components/FooterNav";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

async function getUsage(accessToken: string) {
  const res = await fetch(`${API_URL}/api/usage`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

export default async function AccountPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const usage = await getUsage(session.access_token);

  async function signOut() {
    "use server";
    const supabase = await createClient();
    await supabase.auth.signOut();
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-herald-bg pb-24">
      <Header title="Account" />

      <div className="max-w-xl mx-auto px-6 py-10 flex flex-col gap-6 animate-section-in">
        <h2 className="text-[1.8rem] text-herald-text">Account</h2>

        <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6 flex flex-col gap-4">
          <h3 className="text-[1.3rem] text-herald-text">Profile</h3>
          <div className="flex flex-col gap-2 text-sm text-herald-muted-hard font-light">
            <div className="flex gap-2">
              <span className="font-bold text-herald-muted w-20 shrink-0 text-[0.84rem] uppercase tracking-wide">Email</span>
              <span>{session.user.email}</span>
            </div>
            <div className="flex gap-2">
              <span className="font-bold text-herald-muted w-20 shrink-0 text-[0.84rem] uppercase tracking-wide">Name</span>
              <span>{session.user.user_metadata?.full_name ?? "\u2014"}</span>
            </div>
          </div>
        </div>

        {usage && (
          <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6 flex flex-col gap-4">
            <h3 className="text-[1.3rem] text-herald-text">Scan usage</h3>
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-herald-muted-hard font-light">
                  {usage.scans_used} of {usage.scans_limit} scans used this month
                </span>
                <span className="text-herald-muted font-medium">
                  {usage.scans_remaining} remaining
                </span>
              </div>
              <div className="w-full bg-herald-surface-soft rounded-full h-2">
                <div
                  className="bg-herald-accent h-2 rounded-full transition-all"
                  style={{
                    width: `${Math.min(
                      (usage.scans_used / usage.scans_limit) * 100,
                      100
                    )}%`,
                  }}
                />
              </div>
              <p className="text-xs text-herald-muted font-light">
                Limit resets on the 1st of each month.
              </p>
            </div>
          </div>
        )}

        <div className="bg-white/[0.88] rounded-herald shadow-herald-card p-6">
          <form action={signOut}>
            <button
              type="submit"
              className="text-sm font-bold text-herald-danger hover:text-red-800 transition-colors"
            >
              Sign out
            </button>
          </form>
        </div>
      </div>
      <FooterNav user={session.user} />
    </main>
  );
}
