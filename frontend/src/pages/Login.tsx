import { ArrowRight, FlaskConical, Moon, Sun } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, session, type User } from "../api";

const DEMO = [
  { username: "admin", password: "admin123", label: "Admin", hint: "Everything incl. audit log" },
  { username: "warehouse", password: "warehouse123", label: "Warehouse Manager", hint: "Run optimisations, simulate lots" },
  { username: "distributor", password: "distributor123", label: "Distributor", hint: "Run optimisations, accept plans" },
  { username: "retailer", password: "retailer123", label: "Retailer", hint: "Read-only + what-if" },
];

export default function Login({ onLogin, dark, toggleTheme }: {
  onLogin: (u: User) => void; dark: boolean; toggleTheme: () => void;
}) {
  const [username, setU] = useState("admin");
  const [password, setP] = useState("admin123");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e?: FormEvent, u = username, p = password) {
    e?.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await api<{ token: string; user: User }>("/auth/login", { body: { username: u, password: p } });
      session.set(r.token, r.user);
      onLogin(r.user);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Login failed");
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-full grid lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden lg:flex flex-col justify-between p-12 bg-surface border-r border-line">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent text-white font-bold">Q</div>
          <span className="text-lg font-semibold">Q-Chain AI</span>
        </div>
        <div className="max-w-lg">
          <h1 className="text-4xl font-semibold tracking-tight leading-tight">
            Turn cold-chain history into remaining-life decisions.
          </h1>
          <p className="mt-4 text-ink2 leading-relaxed">
            Q-Chain estimates how much <strong>usable quality life</strong> a shipment has left after its actual journey,
            explains why it changed, and recommends the compliant destination that wastes the least food.
            The declared expiry date is never changed.
          </p>
          <div className="mt-8 flex flex-wrap gap-2 text-[12px] font-medium text-ink2">
            {["Sense", "Reconstruct", "Predict", "Explain", "Classify", "Optimize", "Rescue"].map((s, i) => (
              <span key={s} className="flex items-center gap-2">
                <span className="rounded-md border border-line px-2 py-1">{s}</span>
                {i < 6 && <ArrowRight size={12} className="text-muted" />}
              </span>
            ))}
          </div>
        </div>
        <p className="text-[12px] text-muted max-w-lg flex gap-2">
          <FlaskConical size={14} className="shrink-0 mt-0.5" />
          Decision-support prototype. Sensor readings are synthetic, grounded in sensor variables documented by Qatar
          cold-chain / IoT providers and temperature requirements documented by Qatar MOPH.
        </p>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="flex justify-end mb-6">
            <button className="btn-ghost !p-2" onClick={toggleTheme} aria-label="Toggle theme">
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
          <h2 className="text-2xl font-semibold">Sign in</h2>
          <p className="text-sm text-muted mt-1">Demo accounts — pick a role.</p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            {DEMO.map((d) => (
              <button key={d.username} disabled={busy}
                className="card text-left px-3 py-2.5 hover:border-accent transition"
                onClick={() => { setU(d.username); setP(d.password); submit(undefined, d.username, d.password); }}>
                <div className="text-sm font-medium">{d.label}</div>
                <div className="text-[11px] text-muted leading-snug">{d.hint}</div>
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="mt-6 space-y-3">
            <input className="input w-full" value={username} onChange={(e) => setU(e.target.value)} placeholder="Username" autoComplete="username" />
            <input className="input w-full" value={password} onChange={(e) => setP(e.target.value)} placeholder="Password" type="password" autoComplete="current-password" />
            {err && <div className="text-sm text-critical">{err}</div>}
            <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        </div>
      </div>
    </div>
  );
}
