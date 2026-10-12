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

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join("; ");
  }
  return "Something went wrong";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection.");
  }
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, errorMessage((data as { detail?: unknown } | null)?.detail));
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
};
