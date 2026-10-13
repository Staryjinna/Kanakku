import { useEffect, useState, type FormEvent } from "react";
import { api, type Customer } from "../api";
import { ErrorText, Spinner } from "./Layout";

const blank = { name: "", phone: "", email: "" };

export function CustomersTab({ customers, reload }: { customers: Customer[] | null; reload: () => void }) {
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (editing === null) setForm(blank); }, [editing]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { name: form.name, phone: form.phone.trim() || null, email: form.email.trim() || null };
    try {
      if (editing === null) await api.createCustomer(body); else await api.updateCustomer(editing, body);
      setEditing(null);
      setForm(blank);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function remove(c: Customer) {
    if (!window.confirm(`Delete ${c.name}?`)) return;
    setError(null);
    try { await api.deleteCustomer(c.id); reload(); } catch (err) { setError(err instanceof Error ? err.message : "Could not delete"); }
  }

  const set = (k: keyof typeof blank) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-medium">{editing === null ? "Add a customer" : "Edit customer"}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <div><label className="label" htmlFor="c-name">Name</label><input id="c-name" required className="input" value={form.name} onChange={set("name")} /></div>
          <div><label className="label" htmlFor="c-phone">Phone (for WhatsApp)</label><input id="c-phone" inputMode="tel" className="input" value={form.phone} onChange={set("phone")} placeholder="98765 43210" /></div>
          <div><label className="label" htmlFor="c-email">Email</label><input id="c-email" type="email" className="input" value={form.email} onChange={set("email")} /></div>
        </div>
        <ErrorText message={error} />
        <div className="flex gap-2">
          <button className="btn" disabled={busy}>{editing === null ? "Add customer" : "Save"}</button>
          {editing !== null && <button type="button" className="rounded-md border border-slate-300 px-4 py-2 text-sm" onClick={() => setEditing(null)}>Cancel</button>}
        </div>
      </form>
      {customers === null ? <Spinner /> : customers.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">No customers yet. Add the people who owe you money.</p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {customers.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{c.name}</p>
                <p className="truncate text-xs text-slate-500">{[c.phone, c.email].filter(Boolean).join(" · ") || "No contact details"}</p>
              </div>
              <div className="flex shrink-0 gap-3 text-sm">
                <button className="text-emerald-800 underline" onClick={() => { setEditing(c.id); setForm({ name: c.name, phone: c.phone ?? "", email: c.email ?? "" }); window.scrollTo({ top: 0 }); }}>Edit</button>
                <button className="text-red-700 underline" onClick={() => void remove(c)}>Delete</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
