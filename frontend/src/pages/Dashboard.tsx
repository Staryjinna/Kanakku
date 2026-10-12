import { useEffect, useState } from "react";
import { api, type Health } from "../api";
import { useAuth } from "../auth";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
  }, []);

  return (
    <div className="mx-auto min-h-screen w-full max-w-3xl px-4 py-6">
      <header className="mb-6 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-emerald-800">Kanakku AI</h1>
          <p className="truncate text-sm text-slate-600">{user?.business_name}</p>
        </div>
        <button onClick={() => void logout()} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
          Log out
        </button>
      </header>
      <section className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
        <p className="font-medium">Welcome, {user?.name}.</p>
        <p className="mt-1 text-sm text-slate-500">
          Nothing here yet. Bills, ledger and GST help will appear as they are added.
        </p>
      </section>
      <footer className="mt-6 text-xs text-slate-500" aria-live="polite">
        {healthError
          ? "Server status unavailable"
          : health
            ? `Database: ${health.db} · AI model server: ${health.ollama}`
            : "Checking status…"}
      </footer>
    </div>
  );
}
