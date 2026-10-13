import { useState, type FormEvent } from "react";
import { api, formatINR, rupeesToPaise, type Customer, type Invoice } from "../api";
import { ErrorText, Spinner } from "./Layout";

const today = () => new Date().toISOString().slice(0, 10);

export function InvoicesTab({ invoices, customers, reload }: { invoices: Invoice[] | null; customers: Customer[] | null; reload: () => void }) {
  const [form, setForm] = useState({ customer_id: "", invoice_no: "", invoice_date: today(), due_date: today(), amount: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [paying, setPaying] = useState<number | null>(null);
  const [payAmount, setPayAmount] = useState("");
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const total = rupeesToPaise(form.amount);
    if (!total || Number.isNaN(total)) return setError("Enter the invoice amount in rupees, like 12500 or 12500.50");
    setBusy(true);
    setError(null);
    try {
      await api.createInvoice({ customer_id: Number(form.customer_id), invoice_no: form.invoice_no, invoice_date: form.invoice_date, due_date: form.due_date, total_paise: total });
      setForm({ ...form, invoice_no: "", amount: "" });
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function pay(inv: Invoice, partial?: number) {
    setError(null);
    try { await api.payInvoice(inv.id, partial); setPaying(null); setPayAmount(""); reload(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not record payment"); }
  }

  async function remove(inv: Invoice) {
    if (!window.confirm(`Delete invoice ${inv.invoice_no}?`)) return;
    try { await api.deleteInvoice(inv.id); reload(); } catch (err) { setError(err instanceof Error ? err.message : "Could not delete"); }
  }

  return (
    <div className="space-y-4">
      {customers && customers.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600">Add a customer first (Customers tab), then create invoices for them.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-medium">New sales invoice</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><label className="label" htmlFor="i-cust">Customer</label>
              <select id="i-cust" required className="input" value={form.customer_id} onChange={set("customer_id")}>
                <option value="">Select…</option>{customers?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select></div>
            <div><label className="label" htmlFor="i-no">Invoice number</label><input id="i-no" required className="input" value={form.invoice_no} onChange={set("invoice_no")} /></div>
            <div><label className="label" htmlFor="i-date">Invoice date</label><input id="i-date" type="date" required className="input" value={form.invoice_date} onChange={set("invoice_date")} /></div>
            <div><label className="label" htmlFor="i-due">Due date</label><input id="i-due" type="date" required className="input" value={form.due_date} onChange={set("due_date")} /></div>
            <div><label className="label" htmlFor="i-amt">Amount (₹)</label><input id="i-amt" inputMode="decimal" required className="input" value={form.amount} onChange={set("amount")} /></div>
          </div>
          <ErrorText message={error} />
          <button className="btn" disabled={busy}>Add invoice</button>
        </form>
      )}
      {error && !busy && customers && customers.length === 0 && <ErrorText message={error} />}
      {invoices === null ? <Spinner /> : invoices.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">No invoices yet.</p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {invoices.map((i) => (
            <li key={i.id} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{i.customer_name} · {i.invoice_no}</p>
                  <p className="text-xs text-slate-500">Due {i.due_date}{i.overdue ? ` · ${i.days_overdue} days overdue` : ""}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-medium tabular-nums">{formatINR(i.total_paise)}</p>
                  <span className={`rounded px-2 py-0.5 text-xs ${i.status === "paid" ? "bg-emerald-100 text-emerald-800" : i.overdue ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-700"}`}>
                    {i.status === "paid" ? "Paid" : i.overdue ? "Overdue" : "Open"}
                  </span>
                </div>
              </div>
              {i.status === "open" && (
                <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                  {i.paid_paise > 0 && <span className="text-xs text-slate-500">Balance {formatINR(i.balance_paise)}</span>}
                  <button className="text-emerald-800 underline" onClick={() => void pay(i)}>Mark paid</button>
                  <button className="text-emerald-800 underline" onClick={() => setPaying(paying === i.id ? null : i.id)}>Part payment</button>
                  <button className="text-red-700 underline" onClick={() => void remove(i)}>Delete</button>
                </div>
              )}
              {paying === i.id && (
                <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); const p = rupeesToPaise(payAmount); if (!p || Number.isNaN(p)) return setError("Enter a valid amount"); void pay(i, p); }}>
                  <label className="sr-only" htmlFor={`pay-${i.id}`}>Amount received (₹)</label>
                  <input id={`pay-${i.id}`} className="input" inputMode="decimal" placeholder="Amount received (₹)" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} />
                  <button className="rounded-md bg-emerald-700 px-4 py-2 text-sm text-white">Save</button>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
