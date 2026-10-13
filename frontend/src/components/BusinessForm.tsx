import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, type Me } from "../api";
import { ErrorText } from "./Layout";

/** Business details form shared by onboarding and the account page. */
export function BusinessForm({ user, submitLabel, onSaved, children }: {
  user: Me; submitLabel: string; onSaved: (me: Me) => void; children?: ReactNode;
}) {
  const [states, setStates] = useState<Record<string, string> | null>(null);
  const [form, setForm] = useState({
    name: user.business_name, gstin: user.gstin ?? "", state_code: user.state_code, language: user.language,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.states().then(setStates).catch((e: Error) => setError(e.message));
  }, []);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.updateBusiness({ ...form, gstin: form.gstin.trim() || null }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label className="label" htmlFor="bname">Business name</label>
        <input id="bname" required className="input" value={form.name} onChange={set("name")} />
      </div>
      <div>
        <label className="label" htmlFor="bstate">State</label>
        <select id="bstate" required className="input" value={form.state_code} onChange={set("state_code")}>
          {states ? Object.entries(states).map(([c, n]) => <option key={c} value={c}>{n}</option>) : <option>Loading…</option>}
        </select>
      </div>
      <div>
        <label className="label" htmlFor="bgstin">Your GSTIN <span className="font-normal text-slate-500">(optional)</span></label>
        <input id="bgstin" className="input uppercase" maxLength={15} value={form.gstin} onChange={set("gstin")} placeholder="33ABCDE1234F1Z5" />
      </div>
      <div>
        <label className="label" htmlFor="blang">Language for customer reminders</label>
        <select id="blang" className="input" value={form.language} onChange={set("language")}>
          <option value="en">English</option>
          <option value="ta">தமிழ் (Tamil)</option>
        </select>
      </div>
      <ErrorText message={error} />
      {children}
      <button className="btn" disabled={busy}>{busy ? "Saving…" : submitLabel}</button>
    </form>
  );
}
