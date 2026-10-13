import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { AppShell } from "../components/AppShell";
import { BusinessForm } from "../components/BusinessForm";
import { ErrorText } from "../components/Layout";

export default function Account() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!user) return null;

  async function remove() {
    if (!window.confirm("Delete your account and ALL your bills, ledger and uploaded files? This cannot be undone.")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(confirm);
      setUser(null);
      navigate("/signup");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete");
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <h2 className="mb-4 text-lg font-semibold">Account</h2>
      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-medium">Business details</h3>
        <BusinessForm user={user} submitLabel="Save" onSaved={(me) => { setUser(me); setSaved(true); }}>
          {saved && <p role="status" className="text-sm text-emerald-700">Saved.</p>}
        </BusinessForm>
      </section>
      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-medium">Your data</h3>
        <p className="mt-1 text-sm text-slate-600">Signed in as {user.email}. Your data stays on this server. <Link to="/privacy" className="text-emerald-700 underline">Privacy policy</Link></p>
        <a href={api.accountExportUrl} download className="mt-3 inline-block rounded-md border border-emerald-700 px-3 py-2 text-sm font-medium text-emerald-800">
          Download all my data (.zip)
        </a>
      </section>
      <section className="rounded-lg border border-red-200 bg-red-50 p-4">
        <h3 className="text-sm font-medium text-red-800">Delete account</h3>
        <p className="mt-1 text-sm text-red-900">Permanently removes your account, bills, ledger, customers, invoices and uploaded files. Download your data first if you need it.</p>
        <label className="label mt-3" htmlFor="confirm-email">Type your email to confirm</label>
        <input id="confirm-email" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        <div className="mt-3"><ErrorText message={error} /></div>
        <button className="mt-3 w-full rounded-md bg-red-700 px-4 py-2 font-medium text-white disabled:opacity-50 sm:w-auto"
          disabled={busy || confirm.trim().toLowerCase() !== user.email} onClick={() => void remove()}>
          {busy ? "Deleting…" : "Delete everything"}
        </button>
      </section>
    </AppShell>
  );
}
