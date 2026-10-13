import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, formatINR, monthLabel, type Dashboard as Data } from "../api";
import { useAuth } from "../auth";
import { AppShell } from "../components/AppShell";
import { CategoryChart } from "../components/CategoryChart";
import { ErrorText, Spinner } from "../components/Layout";

function Tile({ label, value, sub, to }: { label: string; value: string; sub?: ReactNode; to?: string }) {
  const body = (
    <>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </>
  );
  const cls = "block rounded-lg border border-slate-200 bg-white p-4";
  return to ? <Link to={to} className={`${cls} hover:border-emerald-400`}>{body}</Link> : <div className={cls}>{body}</div>;
}

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboard().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <AppShell>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Hello, {user?.name}</h2>
          {data && <p className="text-sm text-slate-500">{monthLabel(data.month)}</p>}
        </div>
        <Link to="/bills" className="btn">Upload a bill</Link>
      </div>
      <ErrorText message={error} />
      {!data && !error && <Spinner />}
      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Tile label="Purchases this month" value={formatINR(data.purchases_paise)} sub={`${data.bills} confirmed bill${data.bills === 1 ? "" : "s"}`} to="/ledger" />
            <Tile label="Input GST this month" value={formatINR(data.input_gst.total_paise)}
              sub={<>{(["cgst", "sgst", "igst"] as const).map((k) => <span key={k} className="block">{k.toUpperCase()} {formatINR(data.input_gst[`${k}_paise`])}</span>)}</>} />
            <Tile label="Bills needing review" value={String(data.needs_review)} sub={data.needs_review ? "Review and confirm" : "All caught up"} to="/bills" />
            <Tile label="Overdue receivables" value={formatINR(data.overdue.amount_paise)}
              sub={`${data.overdue.count} invoice${data.overdue.count === 1 ? "" : "s"} overdue`} to="/followups" />
          </div>
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-medium">Top spending categories</h3>
            {data.top_categories.length === 0 ? (
              <p className="text-sm text-slate-500">No confirmed bills this month yet. Upload a bill and confirm it to see your spending here.</p>
            ) : (
              <CategoryChart data={data.top_categories} title="Spending by category this month" />
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}
