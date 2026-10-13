import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Metrics } from "../api";
import { AppShell } from "../components/AppShell";
import { ErrorText, Spinner } from "../components/Layout";

const ms = (v: number | null) => (v === null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function Admin() {
  const [days, setDays] = useState(14);
  const [m, setM] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setM(null);
    api.metrics(days).then((r) => { setM(r); setError(null); }).catch((e: Error) => setError(e.message));
  }, [days]);

  return (
    <AppShell wide>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">AI usage</h2>
        <select aria-label="Time range" className="input w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[7, 14, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}
        </select>
      </div>
      <ErrorText message={error} />
      {!m && !error && <Spinner />}
      {m && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="AI calls" value={String(m.totals.calls)} sub={`${m.totals.prompt_tokens + m.totals.completion_tokens} tokens`} />
            <Stat label="Errors" value={pct(m.totals.error_rate)} sub={`${m.totals.errors} failed`} />
            <Stat label="Cache hit rate" value={pct(m.totals.cache_hit_rate)} sub={`${m.totals.cache_hits} hits`} />
            <Stat label="Latency p50" value={ms(m.latency_ms.p50)} />
            <Stat label="Latency p95" value={ms(m.latency_ms.p95)} />
          </div>
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-medium">Calls per day</h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={m.per_day} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} tick={{ fill: "#475569", fontSize: 11 }} axisLine={{ stroke: "#cbd5e1" }} tickLine={false} interval="preserveStartEnd" />
                  <YAxis allowDecimals={false} tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: "rgba(148,163,184,0.15)" }} contentStyle={{ fontSize: 12 }} formatter={(v) => [String(v), "Calls"]} />
                  <Bar dataKey="calls" fill="#047857" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
          <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <caption className="px-4 pt-3 text-left text-sm font-medium">Calls by purpose</caption>
              <thead className="text-left text-xs text-slate-500">
                <tr><th className="px-4 py-2">Purpose</th><th className="px-2 py-2 text-right">Calls</th><th className="px-2 py-2 text-right">Errors</th><th className="px-2 py-2 text-right">Cached</th><th className="px-2 py-2 text-right">p50</th><th className="px-4 py-2 text-right">p95</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {m.by_purpose.length === 0 && <tr><td colSpan={6} className="px-4 py-4 text-center text-slate-500">No AI calls in this period.</td></tr>}
                {m.by_purpose.map((p) => (
                  <tr key={p.purpose}>
                    <td className="px-4 py-2">{p.purpose}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.calls}</td>
                    <td className={`px-2 py-2 text-right tabular-nums ${p.errors ? "text-red-700" : ""}`}>{p.errors}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{p.cache_hits}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{ms(p.p50_ms)}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{ms(p.p95_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-medium">Background jobs</h3>
            <p className="text-sm text-slate-700">Queued {m.jobs.queued} · Running {m.jobs.running} · Failed {m.jobs.failed} · Done {m.jobs.done}</p>
          </section>
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-sm font-medium">Recent errors</h3>
            {m.recent_errors.length === 0 ? <p className="text-sm text-slate-500">None.</p> : (
              <ul className="space-y-2 text-xs">
                {m.recent_errors.map((e, i) => (
                  <li key={i} className="break-words"><span className="text-slate-500">{e.created_at.replace("T", " ").slice(0, 16)}</span> · {e.purpose} · {e.model}<br /><span className="text-red-700">{e.error}</span></li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </AppShell>
  );
}
