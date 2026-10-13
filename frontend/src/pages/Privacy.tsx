import { Link } from "react-router-dom";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="mt-6">
    <h2 className="text-base font-semibold">{title}</h2>
    <div className="mt-1 space-y-2 text-sm text-slate-700">{children}</div>
  </section>
);

export default function Privacy() {
  return (
    <main className="mx-auto min-h-screen max-w-2xl px-4 py-8">
      <Link to="/" className="text-sm text-emerald-700 underline">← Back</Link>
      <h1 className="mt-2 text-2xl font-semibold text-emerald-800">Privacy policy</h1>
      <p className="mt-1 text-sm text-slate-500">Kanakku AI is an assistant, not a tax filing service. Please verify with your CA before acting.</p>
      <Section title="What we store">
        <p>Your name, email and a hashed password; your business details; the bills you upload (the files and the details read from them); customers, invoices and reminder drafts; and the GST questions you ask and the answers given.</p>
      </Section>
      <Section title="Where it lives">
        <p>Everything is stored on the server that runs this app: one database file and one uploads folder. Bills are read by an AI model running on that same server. Your data is not sent to any outside AI service, analytics tool, email or messaging provider, or cloud storage.</p>
      </Section>
      <Section title="What the AI can and cannot do">
        <p>Bills it reads are drafts until you confirm them. Reminder messages are drafts until you approve them, and you send them yourself from your own WhatsApp or email. Nothing is sent automatically.</p>
      </Section>
      <Section title="Logs">
        <p>We keep a log of AI calls (purpose, model, timing) to monitor the service. PAN, GSTIN, phone numbers, email addresses and long account-like numbers are removed before anything is written to these logs.</p>
      </Section>
      <Section title="Your choices">
        <p>You can download all your data, and delete your account with all its data and uploaded files, from the Account page. Deleting is permanent. Backups taken before deletion may still hold older copies until they are rotated out (the last 14 are kept).</p>
      </Section>
      <Section title="Consent">
        <p>When you sign up, you agree to this policy. The time you agreed is recorded with your account.</p>
      </Section>
    </main>
  );
}
