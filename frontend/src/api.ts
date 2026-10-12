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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  const isForm = body instanceof FormData;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
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
};

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
