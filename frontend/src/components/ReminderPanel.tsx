import { useEffect, useState } from "react";
import { api, type Customer, type Followup, type Invoice } from "../api";
import { ErrorText } from "./Layout";

const TONE: Record<Followup["tone"], string> = { gentle: "Gentle", firm: "Firm", final: "Final reminder" };

export function ReminderPanel({ invoice, customer, onChanged }: { invoice: Invoice; customer?: Customer; onChanged: () => void }) {
  const [followup, setFollowup] = useState<Followup | null>(null);
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<"whatsapp" | "email">(customer?.phone ? "whatsapp" : "email");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const show = (f: Followup | null) => { setFollowup(f); setText(f?.draft_text ?? ""); };

  useEffect(() => {
    api.followups(invoice.id)
      .then((list) => show(list.find((f) => f.status === "draft" || f.status === "approved") ?? null))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoaded(true));
  }, [invoice.id]);

  async function run(label: string, fn: () => Promise<Followup>, after?: () => void) {
    setBusy(label);
    setError(null);
    try {
      const f = await fn();
      show(f.status === "sent" || f.status === "rejected" ? (f.status === "sent" ? f : null) : f);
      after?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }

  if (!loaded) return <p className="mt-3 text-sm text-slate-500">Loading…</p>;
  const noPhone = !customer?.phone, noEmail = !customer?.email;
  const dirty = followup !== null && text !== followup.draft_text;

  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3" aria-label="Reminder">
      <ErrorText message={error} />
      {!followup && (
        <div className="space-y-2">
          <p className="text-sm text-slate-600">Kanakku writes a draft from the invoice details. You review it, then send it yourself.</p>
          <div className="flex gap-2" role="radiogroup" aria-label="Send by">
            {(["whatsapp", "email"] as const).map((c) => (
              <label key={c} className={`flex-1 cursor-pointer rounded-md border px-3 py-2 text-center text-sm ${channel === c ? "border-emerald-600 bg-emerald-50" : "border-slate-300 bg-white"}`}>
                <input type="radio" className="sr-only" name={`ch-${invoice.id}`} checked={channel === c} onChange={() => setChannel(c)} />
                {c === "whatsapp" ? "WhatsApp" : "Email"}
              </label>
            ))}
          </div>
          {channel === "whatsapp" && noPhone && <p className="text-xs text-amber-800">Add a phone number for this customer (Customers tab) to use WhatsApp.</p>}
          {channel === "email" && noEmail && <p className="text-xs text-amber-800">Add an email address for this customer (Customers tab) to use email.</p>}
          <button className="btn" disabled={busy !== null || (channel === "whatsapp" ? noPhone : noEmail)}
            onClick={() => void run("draft", () => api.draftFollowup(invoice.id, channel))}>
            {busy === "draft" ? "Writing a draft… this can take a minute" : "Draft reminder"}
          </button>
        </div>
      )}
      {followup && followup.status !== "sent" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded bg-slate-200 px-2 py-0.5">{TONE[followup.tone]}</span>
            <span className="rounded bg-slate-200 px-2 py-0.5">{followup.channel === "whatsapp" ? "WhatsApp" : "Email"}</span>
            <span className={`rounded px-2 py-0.5 ${followup.status === "approved" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
              {followup.status === "approved" ? "Approved" : "Draft: not approved yet"}
            </span>
          </div>
          {followup.used_template && (
            <p className="text-xs text-slate-600">The AI draft did not pass our checks (amount, name or invented details), so a standard message is shown.</p>
          )}
          <label className="sr-only" htmlFor={`draft-${invoice.id}`}>Reminder message</label>
          <textarea id={`draft-${invoice.id}`} rows={6} className="input" value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} />
          {followup.status === "draft" || dirty ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              {dirty && <button className="btn" disabled={busy !== null} onClick={() => void run("save", () => api.editFollowup(followup.id, text))}>Save edits</button>}
              {!dirty && <button className="btn" disabled={busy !== null} onClick={() => void run("approve", () => api.followupAction(followup.id, "approve"))}>Approve message</button>}
              <button className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm" disabled={busy !== null}
                onClick={() => void run("again", () => api.draftFollowup(invoice.id, followup.channel, true))}>Write again</button>
              <button className="rounded-md px-4 py-2 text-sm text-slate-600 underline" disabled={busy !== null}
                onClick={() => void run("reject", () => api.followupAction(followup.id, "reject"))}>Discard</button>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-slate-600">Nothing is sent from Kanakku. These buttons open your own WhatsApp or email with the message ready to send.</p>
              <div className="flex flex-col gap-2 sm:flex-row">
                {followup.channel === "whatsapp" && followup.whatsapp_url && (
                  <a className="btn" href={followup.whatsapp_url} target="_blank" rel="noopener noreferrer">Open WhatsApp</a>
                )}
                {followup.channel === "email" && followup.mailto_url && (
                  <a className="btn" href={followup.mailto_url}>Open email</a>
                )}
                <button className="rounded-md border border-emerald-700 bg-white px-4 py-2 text-sm font-medium text-emerald-800" disabled={busy !== null}
                  onClick={() => void run("sent", () => api.followupAction(followup.id, "sent"), onChanged)}>
                  I have sent it
                </button>
              </div>
              <p className="text-xs text-slate-500">Edit the text above if you want to change it; you will need to approve it again.</p>
            </div>
          )}
        </div>
      )}
      {followup?.status === "sent" && (
        <p role="status" className="text-sm text-emerald-800">Marked as sent{followup.sent_at ? ` on ${followup.sent_at.slice(0, 10)}` : ""}.</p>
      )}
    </div>
  );
}
