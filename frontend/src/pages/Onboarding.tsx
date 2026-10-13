import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { BusinessForm } from "../components/BusinessForm";
import { ErrorText, Page } from "../components/Layout";

export default function Onboarding() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2>(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  if (!user) return null;

  async function finish(next: string, upload?: File) {
    setBusy(true);
    setError(null);
    try {
      let target = next;
      if (upload) target = `/bills/${(await api.uploadBill(upload)).bill.id}`;
      setUser(await api.updateBusiness({
        name: user!.business_name, gstin: user!.gstin, state_code: user!.state_code,
        language: user!.language, onboarding_done: true,
      }));
      navigate(target);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(false);
    }
  }

  return (
    <Page title={step === 1 ? "Step 1 of 2: your business" : "Step 2 of 2: your first bill"}>
      {step === 1 ? (
        <BusinessForm user={user} submitLabel="Continue" onSaved={(me) => { setUser(me); setStep(2); }} />
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Upload a photo or PDF of a purchase bill. Kanakku reads it and shows you what it found. Nothing is saved to
            your ledger until you confirm it.
          </p>
          <ErrorText message={error} />
          <input ref={file} type="file" className="sr-only" id="first-bill" accept="image/jpeg,image/png,image/webp,application/pdf"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void finish("/bills", f); }} />
          <label htmlFor="first-bill" className={`btn cursor-pointer ${busy ? "opacity-50" : ""}`}>{busy ? "Uploading…" : "Choose a bill"}</label>
          <button className="block w-full text-center text-sm text-slate-600 underline" disabled={busy} onClick={() => void finish("/")}>
            Skip for now
          </button>
        </div>
      )}
    </Page>
  );
}
