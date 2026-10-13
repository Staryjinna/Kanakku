// The single API client. All backend calls go through here.
export interface Me {
  user_id: number;
  email: string;
  name: string;
  business_id: number;
  business_name: string;
  state_code: string;
  language: string;
  gstin: string | null;
  onboarding_done: boolean;
  is_admin: boolean;
}

export interface SignupInput {
  email: string;
  password: string;
  name: string;
  business_name: string;
  state_code: string;
  consent: boolean;
}

export interface Health {
  status: string;
  db: string;
  ollama: string;
  reranker: string;
}

export interface Issue {
  field: string;
  code: string;
  message: string;
  severity: "error" | "warning";
}

export interface BillItem {
  description: string;
  hsn: string | null;
  qty: number;
  rate_paise: number;
  gst_rate: number | null;
  amount_paise: number;
}

export type BillStatus = "processing" | "needs_review" | "confirmed" | "failed";

export interface Bill {
  id: number;
  status: BillStatus;
  vendor_name: string | null;
  vendor_gstin: string | null;
  bill_no: string | null;
  bill_date: string | null;
  taxable_paise: number | null;
  cgst_paise: number | null;
  sgst_paise: number | null;
  igst_paise: number | null;
  total_paise: number | null;
  category: string | null;
  error: string | null;
  created_at: string;
  confirmed_at: string | null;
  file_kind: string;
  items: BillItem[];
  issues: Issue[];
  low_confidence: string[];
}

export type BillUpdate = Omit<
  Bill,
  "id" | "status" | "error" | "created_at" | "confirmed_at" | "file_kind" | "issues" | "low_confidence"
>;

export const CATEGORIES = [
  "stock purchase",
  "rent",
  "utilities",
  "salaries",
  "transport",
  "office supplies",
  "professional fees",
  "repairs",
  "other",
] as const;

export interface Citation {
  n: number;
  chunk_id: number;
  document_id: number;
  title: string;
  page: number;
  snippet: string;
  text: string;
}

export interface AskResult {
  answer: string;
  refused: boolean;
  citations: Citation[];
}

export interface GstDocument {
  id: number;
  title: string;
  source_url: string | null;
  chunks: number;
}

export interface HistoryItem {
  id: number;
  question: string;
  refused: number;
  created_at: string;
}

export interface LedgerEntry {
  id: number;
  status: BillStatus;
  bill_date: string | null;
  vendor_name: string | null;
  bill_no: string | null;
  category: string | null;
  taxable_paise: number | null;
  cgst_paise: number | null;
  sgst_paise: number | null;
  igst_paise: number | null;
  total_paise: number | null;
}

export interface LedgerResponse {
  total_count: number;
  entries: LedgerEntry[];
  totals: { taxable: number; cgst: number; sgst: number; igst: number; total: number };
}

export interface LedgerFilters {
  month?: string;
  category?: string;
  vendor_id?: string;
  status?: string;
  q?: string;
}

export interface FilterOptions {
  months: string[];
  categories: string[];
  vendors: { id: number; name: string }[];
}

export interface Dashboard {
  month: string;
  bills: number;
  purchases_paise: number;
  taxable_paise: number;
  input_gst: { cgst_paise: number; sgst_paise: number; igst_paise: number; total_paise: number };
  top_categories: { category: string; total_paise: number }[];
  needs_review: number;
  overdue: { count: number; amount_paise: number };
}

export interface BusinessInput {
  name: string;
  gstin: string | null;
  state_code: string;
  language: string;
  onboarding_done?: boolean;
}

export interface Customer {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
  open_invoices?: number;
}

export interface Invoice {
  id: number;
  customer_id: number;
  customer_name: string;
  invoice_no: string;
  invoice_date: string;
  due_date: string;
  total_paise: number;
  paid_paise: number;
  balance_paise: number;
  status: "open" | "paid";
  days_overdue: number;
  overdue: boolean;
  reminders_sent: number;
  last_reminder_at: string | null;
}

export interface InvoiceInput {
  customer_id: number;
  invoice_no: string;
  invoice_date: string;
  due_date: string;
  total_paise: number;
}

export interface Followup {
  id: number;
  invoice_id: number;
  channel: "whatsapp" | "email";
  draft_text: string;
  status: "draft" | "approved" | "sent" | "rejected";
  tone: "gentle" | "firm" | "final";
  used_template: boolean;
  created_at: string;
  sent_at: string | null;
  whatsapp_url: string | null;
  mailto_url: string | null;
}

export interface Metrics {
  window_days: number;
  totals: { calls: number; errors: number; error_rate: number; cache_hits: number; cache_hit_rate: number; prompt_tokens: number; completion_tokens: number };
  latency_ms: { p50: number | null; p95: number | null };
  per_day: { date: string; calls: number; errors: number }[];
  by_purpose: { purpose: string; calls: number; errors: number; cache_hits: number; p50_ms: number | null; p95_ms: number | null }[];
  recent_errors: { created_at: string; purpose: string; model: string; error: string }[];
  jobs: { queued: number; running: number; failed: number; done: number };
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public issues: Issue[] = [],
  ) {
    super(message);
  }
}

function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join("; ");
  }
  return "Something went wrong";
}

/** The CSRF cookie is readable by design: we echo it in a header on every state-changing call. */
function csrfHeaders(): Record<string, string> {
  const m = /(?:^|;\s*)kanakku_csrf=([^;]+)/.exec(document.cookie);
  return m ? { "X-CSRF-Token": decodeURIComponent(m[1]) } : {};
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  const isForm = body instanceof FormData;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        ...(body && !isForm ? { "Content-Type": "application/json" } : {}),
        ...(method === "GET" ? {} : csrfHeaders()),
      },
      body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection.");
  }
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const issues = (detail as { issues?: Issue[] } | undefined)?.issues;
    throw new ApiError(res.status, errorMessage(detail), Array.isArray(issues) ? issues : []);
  }
  return data as T;
}

export const api = {
  me: () => request<Me>("GET", "/auth/me"),
  login: (email: string, password: string) => request<Me>("POST", "/auth/login", { email, password }),
  signup: (input: SignupInput) => request<Me>("POST", "/auth/signup", input),
  logout: () => request<void>("POST", "/auth/logout"),
  states: () => request<Record<string, string>>("GET", "/auth/states"),
  health: () => request<Health>("GET", "/health"),
  listBills: (status?: BillStatus) =>
    request<{ total: number; bills: Bill[] }>("GET", `/bills${status ? `?status=${status}` : ""}`),
  uploadBill: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ bill: Bill; job_id: number }>("POST", "/bills", form);
  },
  getBill: (id: number) => request<Bill>("GET", `/bills/${id}`),
  updateBill: (id: number, body: BillUpdate) => request<Bill>("PATCH", `/bills/${id}`, body),
  confirmBill: (id: number, override: boolean) =>
    request<Bill>("POST", `/bills/${id}/confirm`, { override }),
  retryBill: (id: number) => request<unknown>("POST", `/bills/${id}/retry`),
  billFileUrl: (id: number) => `/api/bills/${id}/file`,
  customers: () => request<Customer[]>("GET", "/customers"),
  createCustomer: (c: Omit<Customer, "id">) => request<Customer>("POST", "/customers", c),
  updateCustomer: (id: number, c: Omit<Customer, "id">) => request<Customer>("PUT", `/customers/${id}`, c),
  deleteCustomer: (id: number) => request<void>("DELETE", `/customers/${id}`),
  invoices: (overdue = false) => request<Invoice[]>("GET", `/invoices${overdue ? "?overdue=true" : ""}`),
  createInvoice: (i: InvoiceInput) => request<Invoice>("POST", "/invoices", i),
  deleteInvoice: (id: number) => request<void>("DELETE", `/invoices/${id}`),
  payInvoice: (id: number, amountPaise?: number) =>
    request<Invoice>("POST", `/invoices/${id}/pay`, amountPaise ? { amount_paise: amountPaise } : undefined),
  followups: (invoiceId: number) => request<Followup[]>("GET", `/invoices/${invoiceId}/followups`),
  draftFollowup: (invoiceId: number, channel: string, variation = false) =>
    request<Followup>("POST", `/invoices/${invoiceId}/followups`, { channel, variation }),
  editFollowup: (id: number, draftText: string, channel?: string) =>
    request<Followup>("PATCH", `/followups/${id}`, { draft_text: draftText, channel }),
  followupAction: (id: number, action: "approve" | "sent" | "reject") =>
    request<Followup>("POST", `/followups/${id}/${action}`),
  metrics: (days = 14) => request<Metrics>("GET", `/admin/metrics?days=${days}`),
  dashboard: () => request<Dashboard>("GET", "/dashboard"),
  ledger: (f: LedgerFilters, limit: number, offset: number) => {
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => v && p.set(k, v));
    p.set("limit", String(limit));
    p.set("offset", String(offset));
    return request<LedgerResponse>("GET", `/ledger?${p}`);
  },
  ledgerFilters: () => request<FilterOptions>("GET", "/ledger/filters"),
  exportUrl: (month: string, format: "csv" | "xlsx") => `/api/ledger/export?month=${month}&format=${format}`,
  updateBusiness: (b: BusinessInput) => request<Me>("PATCH", "/account/business", b),
  deleteAccount: (confirmEmail: string) => request<void>("DELETE", "/account", { confirm_email: confirmEmail }),
  accountExportUrl: "/api/account/export",
  gstDocuments: () => request<GstDocument[]>("GET", "/gst/documents"),
  gstHistory: () => request<HistoryItem[]>("GET", "/gst/history"),
};

/** Ask a GST question; `onDelta` gets answer text as it streams. Resolves with the final answer. */
export async function askGst(
  question: string,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<AskResult> {
  let res: Response;
  try {
    res = await fetch("/api/gst/ask", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...csrfHeaders() },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "Cannot reach the server. Check your connection.");
  }
  if (!res.ok || !res.body) {
    const data: unknown = await res.json().catch(() => null);
    throw new ApiError(res.status, errorMessage((data as { detail?: unknown } | null)?.detail));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AskResult | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data) as Record<string, unknown>;
      if (event === "delta") onDelta(String(payload.text));
      else if (event === "done") result = payload as unknown as AskResult;
      else if (event === "error") throw new ApiError(502, String(payload.detail));
    }
  }
  if (!result) throw new ApiError(502, "The answer was cut off. Please try again.");
  return result;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

/** "1234.5" -> 123450 paise; "" -> null; invalid -> NaN */
export function rupeesToPaise(text: string): number | null {
  const t = text.replace(/[,₹\s]/g, "");
  if (t === "") return null;
  if (!/^\d+(\.\d{0,2})?$/.test(t)) return NaN;
  return Math.round(parseFloat(t) * 100);
}

export function paiseToRupees(paise: number | null): string {
  return paise === null ? "" : (paise / 100).toFixed(2);
}

export function formatINR(paise: number | null): string {
  if (paise === null) return "—";
  return "₹" + (paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
