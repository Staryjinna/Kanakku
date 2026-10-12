import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ErrorText, Page } from "../components/Layout";

export default function Signup() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [states, setStates] = useState<Record<string, string> | null>(null);
  const [form, setForm] = useState({
    name: "", email: "", password: "", business_name: "", state_code: "", consent: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.states().then(setStates).catch((e: Error) => setError(e.message));
  }, []);

  if (user) return <Navigate to="/" replace />;

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setUser(await api.signup(form));
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page title="Create your account">
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label" htmlFor="name">Your name</label>
          <input id="name" required autoComplete="name" className="input" value={form.name} onChange={set("name")} />
        </div>
        <div>
          <label className="label" htmlFor="business">Business name</label>
          <input id="business" required className="input" value={form.business_name} onChange={set("business_name")} />
        </div>
        <div>
          <label className="label" htmlFor="state">State</label>
          <select id="state" required className="input" value={form.state_code} onChange={set("state_code")}>
            <option value="">{states ? "Select state" : "Loading…"}</option>
            {states && Object.entries(states).map(([code, name]) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="email" className="input" value={form.email} onChange={set("email")} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password (10+ characters)</label>
          <input id="password" type="password" required minLength={10} autoComplete="new-password" className="input"
            value={form.password} onChange={set("password")} />
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" required className="mt-1 h-4 w-4" checked={form.consent}
            onChange={(e) => setForm((f) => ({ ...f, consent: e.target.checked }))} />
          <span>I agree to the privacy policy. My data stays on this server.</span>
        </label>
        <ErrorText message={error} />
        <button className="btn" disabled={busy}>{busy ? "Creating…" : "Sign up"}</button>
      </form>
      <p className="mt-6 text-sm text-slate-600">
        Already registered? <Link className="text-emerald-700 underline" to="/login">Log in</Link>
      </p>
    </Page>
  );
}
