import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { useUser } from "../App";
import { api, fmt } from "../api";
import { Card, Chip, ErrorBox, SimNotice, Spinner } from "../components/ui";

export default function About() {
  const user = useUser();
  const [r, setR] = useState<any>(null);
  const [audit, setAudit] = useState<any[] | null>(null);
  const [err, setErr] = useState<unknown>(null);

  useEffect(() => {
    api("/reference").then(setR).catch(setErr);
    if (user?.role === "admin") api("/audit?limit=60").then(setAudit).catch(() => {});
  }, [user]);

  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!r) return <Spinner />;
  const mc = r.model_card;

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1200px] mx-auto">
      <h1 className="text-2xl font-semibold tracking-tight">Method, sources & honesty</h1>
      <div className="card p-4 text-[15px] leading-relaxed">{r.product_statement}</div>
      <SimNotice text={r.simulation_disclaimer} />

      <Card title="Pipeline">
        <ol className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2 text-[13px]">
          {[
            ["Sense", "Synthetic IoT readings: temperature, humidity, GPS, door, motion/shock, battery."],
            ["Reconstruct", "Data-quality screen, then journey features: time in/above/below band, degree-hours, dwell, transit, doors."],
            ["Predict", "Physics-inspired Q10 + abuse model blended 60/40 with a gradient-boosting model; quantile models give a range."],
            ["Explain", "Every day of lost life is attributed to a named factor with the sensor evidence behind it."],
            ["Classify", "GOOD / MID / LOW / HOLD from product timing needs and the separate compliance layer."],
            ["Optimize", "Demand-aware greedy allocation maximising revenue + social value minus waste, transport and delay."],
            ["Rescue", "Short-window lots go to rapid-sale or eligible food-rescue review — never on a safety claim."],
            ["Narrate", "An LLM may narrate the structured outputs; guardrails reject safety claims and ungrounded numbers."],
          ].map(([t, d], i) => (
            <li key={t} className="rounded-lg border border-line p-3">
              <div className="font-semibold">{i + 1}. {t}</div>
              <div className="text-ink2 text-[12px] mt-0.5">{d}</div>
            </li>
          ))}
        </ol>
      </Card>

      <Card title="Public sources used for grounding">
        <ul className="space-y-2">
          {Object.values(r.sources).map((s: any) => (
            <li key={s.url} className="text-sm">
              <a href={s.url} target="_blank" rel="noreferrer" className="font-medium text-accent inline-flex items-center gap-1">{s.title} <ExternalLink size={12} /></a>
              <div className="text-[12px] text-ink2">{s.used_for}</div>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[12px] text-muted">No Qatar company has provided data to this prototype. Sources establish which variables and thresholds exist; all readings are simulated.</p>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="official_regulatory_thresholds">
          <table className="w-full">
            <tbody className="divide-y divide-line">
              {Object.entries(r.official_regulatory_thresholds).map(([k, v]: any) => (
                <tr key={k}><td className="td font-medium capitalize">{k}</td><td className="td">{v.label}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Prototype model card">
          <dl className="grid grid-cols-[140px_1fr] gap-y-1 text-[13px]">
            <dt className="text-muted">Model</dt><dd>{mc.type}</dd>
            <dt className="text-muted">Version</dt><dd>{mc.version}</dd>
            <dt className="text-muted">Training data</dt><dd>{mc.training_data} ({mc.metrics.samples} journeys)</dd>
            <dt className="text-muted">Synthetic holdout</dt><dd>MAE {(mc.metrics.holdout_mae_fraction * 100).toFixed(1)}% of declared life · R² {mc.metrics.holdout_r2}</dd>
            <dt className="text-muted">Status</dt><dd><Chip tone="warn">{mc.status}</Chip></dd>
          </dl>
          <div className="mt-2 text-[11px] text-muted">{mc.metrics.note}</div>
          <div className="mt-3 card-t mb-1">Top feature importances</div>
          <ul className="space-y-1">
            {Object.entries(mc.importances).slice(0, 6).map(([k, v]: any) => (
              <li key={k} className="grid grid-cols-[180px_1fr_40px] items-center gap-2 text-[12px]">
                <span className="text-ink2 truncate">{k}</span>
                <div className="h-1.5 rounded-full bg-line"><div className="h-full rounded-full bg-accent" style={{ width: `${v * 100}%` }} /></div>
                <span className="tabnum text-right">{(v * 100).toFixed(0)}%</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="demo_product_parameters (prototype — not legal shelf-life rules)" bodyClass="!px-0 overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line"><tr>
            <th className="th pl-4">Product</th><th className="th">Class</th><th className="th">Band</th><th className="th">Humidity</th>
            <th className="th text-right">Declared life</th><th className="th">Sensitivity</th><th className="th text-right">Q10</th>
            <th className="th text-right">Min window</th><th className="th">High-risk</th></tr></thead>
          <tbody className="divide-y divide-line">
            {r.demo_product_parameters.map((p: any) => (
              <tr key={p.product_id}>
                <td className="td pl-4 font-medium">{p.name}</td><td className="td">{p.storage_class}</td>
                <td className="td tabnum">{p.required_min_temperature}–{p.required_max_temperature} °C</td>
                <td className="td tabnum">{p.humidity_min ? `${p.humidity_min}–${p.humidity_max}%` : "—"}</td>
                <td className="td text-right tabnum">{p.declared_shelf_life_days} d</td><td className="td">{p.sensitivity}</td>
                <td className="td text-right tabnum">{p.q10}</td><td className="td text-right tabnum">{p.min_window_days} d</td>
                <td className="td">{p.high_risk ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Compliance rule engine" bodyClass="!px-0 overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line"><tr><th className="th pl-4">Rule</th><th className="th">Type</th><th className="th">Outcome</th><th className="th">Description</th></tr></thead>
          <tbody className="divide-y divide-line">
            {r.compliance_rules.map((c: any) => (
              <tr key={c.rule_id}>
                <td className="td pl-4"><code className="text-[12px]">{c.rule_id}</code><div className="text-[12px] text-ink2">{c.name}</div></td>
                <td className="td"><Chip tone={c.rule_type === "official_threshold" ? "accent" : "neutral"}>{c.rule_type === "official_threshold" ? "Official (MOPH)" : "Prototype policy"}</Chip></td>
                <td className="td text-[12px] font-semibold">{c.outcome}</td>
                <td className="td text-[12px] text-ink2 whitespace-normal min-w-[320px]">{c.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="What Q-Chain does not claim">
        <ul className="list-disc pl-5 text-sm text-ink2 space-y-1">
          <li>It does not determine food safety, and it never changes or extends a legal expiry date.</li>
          <li>It is not clinically or scientifically validated; the ML model is not production-ready.</li>
          <li>Sensor readings are synthetic — not commercial data from Vodafone Qatar or any other provider.</li>
          <li>It does not claim Qatar lacks cold-chain monitoring or food-rescue systems; it adds a decision layer on top.</li>
        </ul>
      </Card>

      {audit && (
        <Card title="Audit log (admin)" bodyClass="!px-0 overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-line"><tr><th className="th pl-4">Time (UTC)</th><th className="th">User</th><th className="th">Role</th><th className="th">Action</th><th className="th">Resource</th><th className="th">Detail</th></tr></thead>
            <tbody className="divide-y divide-line">
              {audit.map((a, i) => (
                <tr key={i}><td className="td pl-4 tabnum text-[12px]">{fmt.dt(a.ts)}</td><td className="td">{a.username}</td><td className="td text-[12px]">{a.role}</td>
                  <td className="td font-medium">{a.action}</td><td className="td">{a.resource}</td><td className="td text-[12px] text-ink2 max-w-[360px] truncate">{a.detail}</td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
