import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { api, askGst, type AskResult, type Citation, type GstDocument, type HistoryItem } from "../api";
import { AppShell } from "../components/AppShell";

interface Turn {
  id: number;
  question: string;
  text: string;
  result: AskResult | null;
  error: string | null;
}

const CITE_SPLIT = /(\[\d+(?:\s*,\s*\d+)*\])/;

function AnswerText({ text, citations, onPick }: { text: string; citations: Citation[]; onPick: (c: Citation) => void }) {
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {text.split(CITE_SPLIT).map((part, i) => {
        const m = /^\[(\d+(?:\s*,\s*\d+)*)\]$/.exec(part);
        if (!m) return <Fragment key={i}>{part}</Fragment>;
        return (
          <Fragment key={i}>
            {m[1].split(",").map((raw, j) => {
              const n = Number(raw);
              const c = citations.find((x) => x.n === n);
              return c ? (
                <button key={j} onClick={() => onPick(c)} aria-label={`Source ${n}: ${c.title}, page ${c.page}`}
                  className="mx-0.5 rounded bg-emerald-100 px-1.5 text-xs font-medium text-emerald-900 hover:bg-emerald-200">
                  {n}
                </button>
              ) : (
                <span key={j}>[{n}]</span>
              );
            })}
          </Fragment>
        );
      })}
    </p>
  );
}

export default function Ask() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [docs, setDocs] = useState<GstDocument[] | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [picked, setPicked] = useState<{ turn: number; cite: Citation } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.gstDocuments().then(setDocs).catch(() => setDocs([]));
    api.gstHistory().then(setHistory).catch(() => undefined);
    return () => abort.current?.abort();
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [turns]);

  const update = (id: number, patch: Partial<Turn>) =>
    setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 3 || busy) return;
    const id = Date.now();
    setTurns((ts) => [...ts, { id, question: q, text: "", result: null, error: null }]);
    setQuestion("");
    setBusy(true);
    setPicked(null);
    abort.current = new AbortController();
    let acc = "";
    try {
      const result = await askGst(q, (d) => { acc += d; update(id, { text: acc }); }, abort.current.signal);
      update(id, { text: result.answer, result });
      api.gstHistory().then(setHistory).catch(() => undefined);
    } catch (err) {
      if (!(err instanceof DOMException)) update(id, { error: err instanceof Error ? err.message : "Something went wrong" });
    } finally {
      setBusy(false);
    }
  }

  const noDocs = docs !== null && docs.length === 0;

  return (
    <AppShell>
      <h2 className="text-lg font-semibold">Ask about GST</h2>
      <p className="mb-4 text-sm text-slate-500">
        Answers come only from the official documents loaded on this server, with sources.
        {docs && docs.length > 0 ? ` ${docs.length} document${docs.length > 1 ? "s" : ""} loaded.` : ""}
      </p>
      {noDocs && (
        <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">
          No GST documents are loaded yet, so questions cannot be answered. Ask your administrator to run <code>make ingest</code>.
        </p>
      )}
      <div className="space-y-4">
        {turns.length === 0 && history.length > 0 && (
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Recent questions</p>
            <ul className="flex flex-wrap gap-2">
              {history.slice(0, 5).map((h) => (
                <li key={h.id}>
                  <button className="rounded-full border border-slate-300 bg-white px-3 py-1 text-left text-xs" onClick={() => setQuestion(h.question)}>
                    {h.question.length > 60 ? h.question.slice(0, 57) + "…" : h.question}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {turns.map((t) => (
          <div key={t.id} className="space-y-2">
            <p className="ml-auto w-fit max-w-[90%] rounded-lg bg-emerald-700 px-3 py-2 text-sm text-white">{t.question}</p>
            <div className={`rounded-lg border p-3 ${t.result?.refused ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
              {t.error ? (
                <p role="alert" className="text-sm text-red-700">{t.error}</p>
              ) : t.text === "" ? (
                <p className="text-sm text-slate-500">Searching the documents…</p>
              ) : (
                <AnswerText text={t.text} citations={t.result?.citations ?? []} onPick={(c) => setPicked({ turn: t.id, cite: c })} />
              )}
              {t.result && t.result.citations.length > 0 && (
                <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2">
                  {t.result.citations.map((c) => (
                    <li key={c.n}>
                      <button className="text-left text-xs text-emerald-800 underline" onClick={() => setPicked({ turn: t.id, cite: c })}>
                        [{c.n}] {c.title}, page {c.page}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {picked?.turn === t.id && (
                <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3" role="region" aria-label="Source passage">
                  <div className="mb-1 flex items-start justify-between gap-2">
                    <p className="text-xs font-semibold text-emerald-900">{picked.cite.title} · page {picked.cite.page}</p>
                    <button className="text-xs text-slate-500" onClick={() => setPicked(null)} aria-label="Close source">✕</button>
                  </div>
                  <p className="max-h-60 overflow-y-auto whitespace-pre-wrap text-xs text-slate-700">{picked.cite.text}</p>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <form onSubmit={onSubmit} className="sticky bottom-0 mt-4 space-y-2 bg-slate-50 pb-2 pt-2">
        <label htmlFor="q" className="sr-only">Your GST question</label>
        <textarea id="q" rows={2} maxLength={500} className="input" placeholder="e.g. What is the turnover limit for the composition scheme?"
          value={question} onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-slate-500">An assistant, not tax advice. Please verify with your CA before acting.</p>
          <button className="btn" disabled={busy || question.trim().length < 3}>{busy ? "Answering…" : "Ask"}</button>
        </div>
      </form>
    </AppShell>
  );
}
