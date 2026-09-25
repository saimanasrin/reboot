// Thin API client. The token is a per-browser convenience; the backend enforces roles on every call.
export type Classification = "GOOD" | "MID" | "LOW" | "HOLD";
export type Role = "admin" | "warehouse_manager" | "distributor" | "retailer";

export interface User { username: string; role: Role; name: string }

const TOKEN_KEY = "qchain-token";
const USER_KEY = "qchain-user";

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* ignore */ }
}

let token: string | null = read(TOKEN_KEY);
let onUnauthorized: () => void = () => {};

export const session = {
  user(): User | null {
    const raw = read(USER_KEY);
    try { return raw && token ? (JSON.parse(raw) as User) : null; } catch { return null; }
  },
  set(t: string, u: User) { token = t; write(TOKEN_KEY, t); write(USER_KEY, JSON.stringify(u)); },
  clear() { token = null; write(TOKEN_KEY, null); write(USER_KEY, null); },
  onUnauthorized(fn: () => void) { onUnauthorized = fn; },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    session.clear();
    onUnauthorized();
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const canOperate = (u: User | null) => !!u && ["admin", "warehouse_manager", "distributor"].includes(u.role);

export const CLASS_META: Record<Classification, { label: string; short: string; action: string; tone: string }> = {
  GOOD: { label: "Good", short: "GOOD", action: "Normal", tone: "good" },
  MID: { label: "Mid", short: "MID", action: "Accelerate", tone: "warn" },
  LOW: { label: "Low", short: "LOW", action: "Rescue", tone: "serious" },
  HOLD: { label: "Hold", short: "HOLD", action: "Hold / review", tone: "hold" },
};

export const fmt = {
  d: (v: number | null | undefined, digits = 1) => (v === null || v === undefined ? "—" : v.toFixed(digits)),
  kg: (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v).toLocaleString()} kg`),
  qar: (v: number | null | undefined) => (v === null || v === undefined ? "—" : `QAR ${Math.round(v).toLocaleString()}`),
  qarShort: (v: number | null | undefined) => (v === null || v === undefined ? "—"
    : `QAR ${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v)}`),
  pct: (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? "—" : `${v.toFixed(digits)}%`),
  dt: (iso: string | null | undefined) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  },
  date: (iso: string | null | undefined) =>
    iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—",
};
