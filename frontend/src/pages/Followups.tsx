import { useCallback, useEffect, useState } from "react";
import { api, formatINR, type Customer, type Invoice } from "../api";
import { AppShell } from "../components/AppShell";
import { CustomersTab } from "../components/CustomersTab";
import { InvoicesTab } from "../components/InvoicesTab";
import { ErrorText, Spinner } from "../components/Layout";
import { ReminderPanel } from "../components/ReminderPanel";

type Tab = "overdue" | "invoices" | "customers";
const TABS: [Tab, string][] = [["overdue", "Overdue"], ["invoices", "Invoices"], ["customers", "Customers"]];

export default function Followups() {
  const [tab, setTab] = useState<Tab>("overdue");
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.invoices().then(setInvoices).catch((e: Error) => setError(e.message));
    api.customers().then(setCustomers).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(reload, [reload]);

  const overdue = (invoices ?? []).filter((i) => i.overdue);
  const dueTotal = overdue.reduce((a, i) => a + i.balance_paise, 0);

  return (
    <AppShell>
      <h2 className="mb-1 text-lg font-semibold">Payment follow-ups</h2>
      <p className="mb-4 text-sm text-slate-500">Kanakku drafts reminders. You approve them and send them yourself from your own WhatsApp or email.</p>
      <div role="tablist" className="mb-4 flex gap-1 rounded-lg bg-slate-200 p-1">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm ${tab === id ? "bg-white font-medium shadow-sm" : "text-slate-600"}`}>
            {label}{id === "overdue" && overdue.length > 0 ? ` (${overdue.length})` : ""}
          </button>
        ))}
      </div>
      <ErrorText message={error} />
      {tab === "overdue" && (
        invoices === null ? <Spinner /> : overdue.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">Nothing is overdue. 🎉 Add sales invoices in the Invoices tab to track them.</p>
        ) : (
          <>
            <p className="mb-3 text-sm text-slate-600">{overdue.length} overdue · {formatINR(dueTotal)} to collect</p>
            <ul className="space-y-3">
              {overdue.map((i) => (
                <li key={i.id} className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{i.customer_name}</p>
                      <p className="text-xs text-slate-500">Invoice {i.invoice_no} · due {i.due_date}</p>
                      <p className="mt-1 text-xs text-red-700">{i.days_overdue} days overdue{i.reminders_sent ? ` · ${i.reminders_sent} reminder${i.reminders_sent > 1 ? "s" : ""} sent` : ""}</p>
                    </div>
                    <p className="shrink-0 text-lg font-semibold tabular-nums">{formatINR(i.balance_paise)}</p>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button className="rounded-md border border-emerald-700 px-3 py-1.5 text-sm font-medium text-emerald-800" aria-expanded={open === i.id}
                      onClick={() => setOpen(open === i.id ? null : i.id)}>{open === i.id ? "Close" : "Draft reminder"}</button>
                  </div>
                  {open === i.id && <ReminderPanel invoice={i} customer={customers?.find((c) => c.id === i.customer_id)} onChanged={reload} />}
                </li>
              ))}
            </ul>
          </>
        )
      )}
      {tab === "invoices" && <InvoicesTab invoices={invoices} customers={customers} reload={reload} />}
      {tab === "customers" && <CustomersTab customers={customers} reload={reload} />}
    </AppShell>
  );
}
