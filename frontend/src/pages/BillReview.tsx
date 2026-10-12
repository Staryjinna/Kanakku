import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api, ApiError, CATEGORIES, paiseToRupees, rupeesToPaise,
  type Bill, type BillUpdate, type Issue,
} from "../api";
import { AppShell } from "../components/AppShell";
import { ErrorText, Spinner } from "../components/Layout";

interface ItemForm { description: string; hsn: string; qty: string; rate: string; gst_rate: string; amount: string }
interface Form {
  vendor_name: string; vendor_gstin: string; bill_no: string; bill_date: string; category: string;
  taxable: string; cgst: string; sgst: string; igst: string; total: string; items: ItemForm[];
}

function toForm(b: Bill): Form {
  return {
    vendor_name: b.vendor_name ?? "", vendor_gstin: b.vendor_gstin ?? "", bill_no: b.bill_no ?? "",
    bill_date: b.bill_date ?? "", category: b.category ?? "other",
    taxable: paiseToRupees(b.taxable_paise), cgst: paiseToRupees(b.cgst_paise),
    sgst: paiseToRupees(b.sgst_paise), igst: paiseToRupees(b.igst_paise), total: paiseToRupees(b.total_paise),
    items: b.items.map((i) => ({
      description: i.description, hsn: i.hsn ?? "", qty: String(i.qty), rate: paiseToRupees(i.rate_paise),
      gst_rate: i.gst_rate === null ? "" : String(i.gst_rate), amount: paiseToRupees(i.amount_paise),
    })),
  };
}

function toUpdate(f: Form): BillUpdate | string {
  const money = (t: string, label: string) => {
    const v = rupeesToPaise(t);
    if (Number.isNaN(v)) throw new Error(`${label} is not a valid amount`);
    return v;
  };
  try {
    return {
      vendor_name: f.vendor_name || null, vendor_gstin: f.vendor_gstin || null, bill_no: f.bill_no || null,
      bill_date: f.bill_date || null, category: f.category,
      taxable_paise: money(f.taxable, "Taxable value"), cgst_paise: money(f.cgst, "CGST"),
      sgst_paise: money(f.sgst, "SGST"), igst_paise: money(f.igst, "IGST"), total_paise: money(f.total, "Total"),
      items: f.items.map((i, n) => ({
        description: i.description, hsn: i.hsn || null,
        qty: Number(i.qty) || 0,
        rate_paise: money(i.rate, `Line ${n + 1} rate`) ?? 0,
        gst_rate: i.gst_rate === "" ? null : Number(i.gst_rate),
        amount_paise: money(i.amount, `Line ${n + 1} amount`) ?? 0,
      })),
    };
  } catch (e) {
    return (e as Error).message;
  }
}

function FieldBox({ name, label, issues, low, children }: {
  name: string; label: string; issues: Issue[]; low: string[]; children: (cls: string) => ReactNode;
}) {
  const here = issues.filter((i) => i.field === name);
  const worst = here.some((i) => i.severity === "error") ? "error" : here.length ? "warning" : null;
  const unsure = low.includes(name);
  const cls = worst === "error" ? "border-red-500 bg-red-50" : worst === "warning" || unsure ? "border-amber-400 bg-amber-50" : "";
  return (
    <div>
      <label className="label">{label}{unsure && !worst ? <span className="ml-2 text-xs font-normal text-amber-700">please check</span> : null}</label>
      {children(cls)}
      {here.map((i) => <p key={i.code} className={`mt-1 text-xs ${i.severity === "error" ? "text-red-700" : "text-amber-700"}`}>{i.message}</p>)}
    </div>
  );
}

export default function BillReview() {
  const id = Number(useParams().id);
  const [bill, setBill] = useState<Bill | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [override, setOverride] = useState(false);

  const apply = useCallback((b: Bill) => {
    setBill(b);
    setIssues(b.issues);
    setForm(toForm(b));
  }, []);

  useEffect(() => {
    api.getBill(id).then(apply).catch((e: Error) => setError(e.message));
  }, [id, apply]);

  const processing = bill?.status === "processing";
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(() => { api.getBill(id).then(apply).catch(() => undefined); }, 2000);
    return () => clearInterval(t);
  }, [processing, id, apply]);

  if (error && !bill) return <AppShell><ErrorText message={error} /><Link to="/bills" className="mt-4 inline-block text-emerald-700 underline">Back to bills</Link></AppShell>;
  if (!bill || !form) return <AppShell><Spinner /></AppShell>;

  const readOnly = bill.status === "confirmed" || processing;
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const setItem = (n: number, k: keyof ItemForm, v: string) =>
    setForm({ ...form, items: form.items.map((it, i) => (i === n ? { ...it, [k]: v } : it)) });
  const issuesFor = (field: string) => issues.filter((i) => i.field === field);

  async function run(action: () => Promise<Bill>) {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      apply(await action());
    } catch (e) {
      if (e instanceof ApiError && e.issues.length) setIssues(e.issues);
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function save(): Promise<Bill> {
    const upd = toUpdate(form as Form);
    if (typeof upd === "string") return Promise.reject(new Error(upd));
    return api.updateBill(id, upd);
  }

  const hasErrors = issues.some((i) => i.severity === "error");

  const text = (k: keyof Form, label: string, name = k as string) => (
    <FieldBox issues={issues} low={bill.low_confidence} name={name} label={label}>
      {(cls) => <input className={`input ${cls}`} disabled={readOnly} value={form[k] as string} onChange={set(k)} />}
    </FieldBox>
  );

  return (
    <AppShell wide>
      <div className="mb-4 flex items-center gap-3">
        <Link to="/bills" className="text-sm text-emerald-700 underline">← Bills</Link>
        <h2 className="text-lg font-semibold">Bill #{bill.id}</h2>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="Original bill" className="rounded-lg border border-slate-200 bg-white p-2 lg:sticky lg:top-4 lg:self-start">
          {bill.file_kind === "pdf" ? (
            <iframe title="Original bill" src={api.billFileUrl(id)} className="h-[60vh] w-full lg:h-[80vh]" />
          ) : (
            <img src={api.billFileUrl(id)} alt="Original bill" className="mx-auto max-h-[80vh] w-full object-contain" />
          )}
        </section>
        <section aria-label="Extracted details" className="space-y-4">
          {processing && <p className="rounded-md bg-slate-100 px-3 py-2 text-sm">Reading your bill… this can take a minute on a local model.</p>}
          {bill.status === "failed" && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              <p>We could not read this bill. {bill.error}</p>
              <button className="mt-2 underline" onClick={() => void api.retryBill(id).then(() => api.getBill(id)).then(apply)}>Try again</button>
              <span className="mx-1">or</span>fill in the details below by hand.
            </div>
          )}
          {bill.status === "confirmed" && <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">Confirmed and saved to your ledger.</p>}
          <p className="text-sm text-slate-500">Check every field against the bill. Highlighted fields need attention.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {text("vendor_name", "Vendor")}
            {text("vendor_gstin", "Vendor GSTIN")}
            {text("bill_no", "Bill number")}
            <FieldBox issues={issues} low={bill.low_confidence} name="bill_date" label="Bill date">
              {(cls) => <input type="date" className={`input ${cls}`} disabled={readOnly} value={form.bill_date} onChange={set("bill_date")} />}
            </FieldBox>
            <FieldBox issues={issues} low={bill.low_confidence} name="category" label="Category">
              {(cls) => (
                <select className={`input ${cls}`} disabled={readOnly} value={form.category} onChange={set("category")}>
                  {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                </select>
              )}
            </FieldBox>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {text("taxable", "Taxable (₹)")}
            {text("cgst", "CGST (₹)")}
            {text("sgst", "SGST (₹)")}
            {text("igst", "IGST (₹)")}
            {text("total", "Total (₹)")}
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">Items</h3>
            {form.items.length === 0 && <p className="text-sm text-slate-500">No line items.</p>}
            <div className="space-y-3">
              {form.items.map((it, n) => (
                <div key={n} className="rounded-md border border-slate-200 bg-white p-3">
                  <input aria-label={`Item ${n + 1} description`} className="input mb-2" disabled={readOnly} value={it.description}
                    onChange={(e) => setItem(n, "description", e.target.value)} placeholder="Description" />
                  <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                    {(["hsn", "qty", "rate", "gst_rate", "amount"] as const).map((k) => {
                      const field = k === "amount" ? `items[${n}].amount` : k === "gst_rate" ? `items[${n}].gst_rate` : "";
                      const flagged = issuesFor(field).length > 0;
                      return (
                        <div key={k}>
                          <label className="text-xs text-slate-500">{({ hsn: "HSN", qty: "Qty", rate: "Rate ₹", gst_rate: "GST %", amount: "Amount ₹" })[k]}</label>
                          <input className={`input ${flagged ? "border-red-500 bg-red-50" : ""}`} disabled={readOnly} value={it[k]}
                            onChange={(e) => setItem(n, k, e.target.value)} />
                        </div>
                      );
                    })}
                  </div>
                  {[...issuesFor(`items[${n}].amount`), ...issuesFor(`items[${n}].gst_rate`)].map((i) => (
                    <p key={i.code + i.field} className="mt-1 text-xs text-red-700">{i.message}</p>
                  ))}
                </div>
              ))}
            </div>
          </div>
          {issues.length > 0 && (
            <div className="rounded-md border border-slate-200 bg-white p-3 text-sm" role="status">
              <p className="mb-1 font-medium">Checks ({issues.length})</p>
              <ul className="list-disc space-y-1 pl-5">
                {issues.map((i, n) => <li key={n} className={i.severity === "error" ? "text-red-700" : "text-amber-700"}>{i.message}</li>)}
              </ul>
            </div>
          )}
          <ErrorText message={error} />
          {!readOnly && (
            <div className="space-y-3">
              {hasErrors && (
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-1 h-4 w-4" checked={override} onChange={(e) => setOverride(e.target.checked)} />
                  <span>I have checked the bill and these problems are fine. Confirm anyway.</span>
                </label>
              )}
              <div className="flex flex-col gap-2 sm:flex-row">
                <button className="btn" disabled={busy} onClick={() => void run(save)}>Save changes</button>
                <button className="btn" disabled={busy}
                  onClick={() => void run(async () => { await save(); return api.confirmBill(id, override); })}>
                  Confirm and add to ledger
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
