import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatINR, type Bill, type BillStatus } from "../api";
import { AppShell } from "../components/AppShell";
import { ErrorText, Spinner } from "../components/Layout";

const STATUS_LABEL: Record<BillStatus, { text: string; cls: string }> = {
  processing: { text: "Reading…", cls: "bg-slate-100 text-slate-700" },
  needs_review: { text: "Needs review", cls: "bg-amber-100 text-amber-800" },
  confirmed: { text: "Confirmed", cls: "bg-emerald-100 text-emerald-800" },
  failed: { text: "Failed", cls: "bg-red-100 text-red-700" },
};

export default function Bills() {
  const [bills, setBills] = useState<Bill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api.listBills().then((r) => { setBills(r.bills); setError(null); }).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const processing = bills?.some((b) => b.status === "processing") ?? false;
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [processing, load]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadBill(file);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <AppShell>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Bills</h2>
        <label className="btn cursor-pointer">
          {uploading ? "Uploading…" : "Upload bill"}
          <input ref={fileInput} type="file" className="sr-only" disabled={uploading}
            accept="image/jpeg,image/png,image/webp,application/pdf"
            onChange={(e) => void onFile(e.target.files?.[0])} />
        </label>
      </div>
      <ErrorText message={error} />
      {bills === null && !error ? (
        <Spinner />
      ) : bills && bills.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          No bills yet. Upload a photo or PDF of a purchase bill (JPG, PNG, WEBP or PDF, up to 10 MB).
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {bills?.map((b) => (
            <li key={b.id}>
              <Link to={`/bills/${b.id}`} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{b.vendor_name || `Bill #${b.id}`}</p>
                  <p className="truncate text-xs text-slate-500">
                    {[b.bill_no, b.bill_date, b.category].filter(Boolean).join(" · ") || b.created_at.slice(0, 10)}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-medium">{formatINR(b.total_paise)}</p>
                  <span className={`rounded px-2 py-0.5 text-xs ${STATUS_LABEL[b.status].cls}`}>
                    {STATUS_LABEL[b.status].text}
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
