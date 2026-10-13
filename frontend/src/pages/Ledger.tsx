import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api, formatINR, monthLabel,
  type FilterOptions, type LedgerFilters, type LedgerResponse,
} from "../api";
import { AppShell } from "../components/AppShell";
import { ErrorText, Spinner } from "../components/Layout";

const PAGE = 25;

export default function Ledger() {
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [filters, setFilters] = useState<LedgerFilters>({ status: "confirmed" });
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<LedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.ledgerFilters().then(setOptions).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const t = setTimeout(() => { setFilters((f) => ({ ...f, q: search || undefined })); setOffset(0); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let live = true;
    setData(null);
    api.ledger(filters, PAGE, offset).then((r) => { if (live) { setData(r); setError(null); } })
      .catch((e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [filters, offset]);

  const set = (k: keyof LedgerFilters) => (e: { target: { value: string } }) => {
    setFilters((f) => ({ ...f, [k]: e.target.value || undefined }));
    setOffset(0);
  };
  const reset = () => { setFilters({ status: "confirmed" }); setSearch(""); setOffset(0); };
  const t = data?.totals;

  return (
    <AppShell wide>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-lg font-semibold">Ledger</h2>
        <div className="flex gap-2">
          {(["csv", "xlsx"] as const).map((f) =>
            filters.month ? (
              <a key={f} href={api.exportUrl(filters.month, f)} download
                className="flex-1 rounded-md border border-emerald-700 px-3 py-2 text-center text-sm font-medium text-emerald-800 sm:flex-none">
                {f === "csv" ? "Download CSV" : "Download Excel"}
              </a>
            ) : (
              <span key={f} aria-disabled="true" title="Pick a month to export"
                className="flex-1 rounded-md border border-slate-200 px-3 py-2 text-center text-sm text-slate-400 sm:flex-none">
                {f === "csv" ? "Download CSV" : "Download Excel"}
              </span>
            ),
          )}
        </div>
      </div>
      {!filters.month && <p className="-mt-2 mb-3 text-xs text-slate-500">Pick a month to enable export.</p>}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-6">
        <select aria-label="Month" className="input" value={filters.month ?? ""} onChange={set("month")}>
          <option value="">All months</option>
          {options?.months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
        </select>
        <select aria-label="Category" className="input" value={filters.category ?? ""} onChange={set("category")}>
          <option value="">All categories</option>
          {options?.categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select aria-label="Vendor" className="input" value={filters.vendor_id ?? ""} onChange={set("vendor_id")}>
          <option value="">All vendors</option>
          {options?.vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
        <select aria-label="Status" className="input" value={filters.status ?? ""} onChange={set("status")}>
          <option value="confirmed">Confirmed</option>
          <option value="needs_review">Needs review</option>
          <option value="failed">Failed</option>
        </select>
        <input aria-label="Search" type="search" className="input col-span-2 lg:col-span-2" placeholder="Search vendor, bill no, category"
          value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <ErrorText message={error} />
      {!data && !error && <Spinner />}
      {data && data.entries.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No bills match.{" "}
          {Object.values(filters).filter(Boolean).length > 1 || search ? (
            <button className="text-emerald-700 underline" onClick={reset}>Clear filters</button>
          ) : (
            <>Confirmed bills appear here. <Link to="/bills" className="text-emerald-700 underline">Go to Bills</Link></>
          )}
        </p>
      )}
      {data && data.entries.length > 0 && t && (
        <>
          <dl className="mb-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
            {[["Bills", String(data.total_count)], ["Taxable", formatINR(t.taxable)], ["CGST + SGST", formatINR(t.cgst + t.sgst)], ["IGST", formatINR(t.igst)], ["Total", formatINR(t.total)]].map(([k, v]) => (
              <div key={k} className="rounded-md bg-white px-3 py-2 ring-1 ring-slate-200">
                <dt className="text-slate-500">{k}</dt>
                <dd className="font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="hidden overflow-x-auto rounded-lg border border-slate-200 bg-white md:block">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2">Date</th><th className="px-3 py-2">Vendor</th><th className="px-3 py-2">Bill no</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2 text-right">Taxable</th><th className="px-3 py-2 text-right">CGST</th>
                  <th className="px-3 py-2 text-right">SGST</th><th className="px-3 py-2 text-right">IGST</th>
                  <th className="px-3 py-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.entries.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-50">
                    <td className="px-3 py-2 tabular-nums">{e.bill_date ?? "—"}</td>
                    <td className="px-3 py-2"><Link className="text-emerald-800 underline" to={`/bills/${e.id}`}>{e.vendor_name || `Bill #${e.id}`}</Link></td>
                    <td className="px-3 py-2">{e.bill_no ?? "—"}</td>
                    <td className="px-3 py-2">{e.category ?? "—"}</td>
                    {[e.taxable_paise, e.cgst_paise, e.sgst_paise, e.igst_paise, e.total_paise].map((v, i) => (
                      <td key={i} className={`px-3 py-2 text-right tabular-nums ${i === 4 ? "font-medium" : ""}`}>{formatINR(v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white md:hidden">
            {data.entries.map((e) => (
              <li key={e.id}>
                <Link to={`/bills/${e.id}`} className="block px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="truncate font-medium">{e.vendor_name || `Bill #${e.id}`}</p>
                    <p className="shrink-0 font-medium tabular-nums">{formatINR(e.total_paise)}</p>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{[e.bill_date, e.bill_no, e.category].filter(Boolean).join(" · ")}</p>
                  <p className="mt-0.5 text-xs text-slate-500">GST {formatINR((e.cgst_paise ?? 0) + (e.sgst_paise ?? 0) + (e.igst_paise ?? 0))}</p>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-slate-500">{offset + 1}–{Math.min(offset + PAGE, data.total_count)} of {data.total_count}</span>
            <div className="flex gap-2">
              <button className="rounded-md border border-slate-300 px-3 py-1.5 disabled:opacity-40" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
              <button className="rounded-md border border-slate-300 px-3 py-1.5 disabled:opacity-40" disabled={offset + PAGE >= data.total_count} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
