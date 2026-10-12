import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Health } from "../api";
import { useAuth } from "../auth";
import { AppShell } from "../components/AppShell";

export default function Dashboard() {
  const { user } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [review, setReview] = useState<number | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
    api.listBills("needs_review").then((r) => setReview(r.total)).catch(() => setReview(null));
  }, []);

  return (
    <AppShell>
      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <p className="font-medium">Welcome, {user?.name}.</p>
        <p className="mt-1 text-sm text-slate-500">Upload a purchase bill and Kanakku will read it for you to check.</p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <Link to="/bills" className="btn">Upload a bill</Link>
          {review ? (
            <Link to="/bills" className="inline-flex items-center justify-center rounded-md border border-amber-400 bg-amber-50 px-4 py-2 text-sm text-amber-900">
              {review} bill{review > 1 ? "s" : ""} waiting for review
            </Link>
          ) : null}
        </div>
      </section>
      <footer className="mt-6 text-xs text-slate-500" aria-live="polite">
        {healthError
          ? "Server status unavailable"
          : health
            ? `Database: ${health.db} · AI model server: ${health.ollama}`
            : "Checking status…"}
      </footer>
    </AppShell>
  );
}
