import clsx from "clsx";
import {
  ArrowRight, Boxes, CircleDollarSign, Clock, Leaf, Radio, ThermometerSun, TrendingDown, TriangleAlert,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, CLASS_META, fmt, type Classification } from "../api";
import FleetMap, { CLASS_HEX, type MapPoint } from "../components/FleetMap";
import { Card, ClassBadge, ErrorBox, Kpi, RiskBadge, SimNotice, Spinner } from "../components/ui";
import { useDark } from "../App";

interface Row {
  shipment_id: string; product: string; quantity_kg: number; estimated_remaining_days: number;
  declared_remaining_days: number; risk_level: string; classification: Classification; location: string;
  recommended_action: string; featured: boolean; confidence: number;
}
interface Dash {
  as_of: string;
  kpis: Record<string, number>;
  by_class: Record<Classification, number>;
  by_product: { product: string; shipments: number; at_risk: number; kg: number; avg_loss_pct: number }[];
  map: MapPoint[];
  attention: Row[];
  alerts: { id: number; shipment_id: string; ts: string; kind: string; severity: string; message: string }[];
  disclaimer: string;
}

const CLASSES: Classification[] = ["GOOD", "MID", "LOW", "HOLD"];
const SEV_TONE: Record<string, string> = { critical: "text-hold", high: "text-critical", medium: "text-[rgb(var(--warn))]", low: "text-muted" };

export default function Dashboard() {
  const [d, setD] = useState<Dash | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [visible, setVisible] = useState<Set<Classification>>(new Set(CLASSES));
  const nav = useNavigate();
  const dark = useDark();

  useEffect(() => { api<Dash>("/dashboard").then(setD).catch(setErr); }, []);
  if (err) return <div className="p-6"><ErrorBox error={err} /></div>;
  if (!d) return <Spinner label="Loading fleet…" />;

  const k = d.kpis;
  const hero = d.attention.find((r) => r.shipment_id === "Q4821");
  const heroAlert = d.alerts.find((a) => a.shipment_id === "Q4821" && a.kind === "TEMP_EXCURSION");
  const total = k.total_shipments;
  const pal = CLASS_HEX[dark ? "dark" : "light"];

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-[1600px] mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-[12px] font-semibold uppercase tracking-wider text-accent">Qatar cold-chain command centre</div>
          <h1 className="text-2xl md:text-[28px] font-semibold tracking-tight mt-0.5">
            <span className="tabnum">{total.toLocaleString()}</span> shipments monitored
          </h1>
          <p className="text-sm text-muted mt-0.5">
            {fmt.kg(k.monitored_kg)} of perishable food in the network · as of {fmt.dt(d.as_of)}
          </p>
        </div>
        <SimNotice text={d.disclaimer} compact />
      </div>

      {hero && heroAlert && (
        <button onClick={() => nav("/shipments/Q4821")}
          className="w-full text-left card border-critical/40 bg-critical/[0.06] px-4 py-3 flex flex-wrap items-center gap-3 hover:border-critical transition fade-up">
          <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-critical/15 text-critical">
            <ThermometerSun size={18} />
            <span className="absolute inset-0 rounded-full ring-2 ring-critical/40 animate-ping" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold flex flex-wrap items-center gap-2">
              Temperature excursion detected · Shipment Q4821 <ClassBadge c={hero.classification} withAction /> <RiskBadge r={hero.risk_level} />
            </div>
            <div className="text-[13px] text-ink2 truncate">
              {heroAlert.message} Usable window now {fmt.d(hero.estimated_remaining_days)} d vs {fmt.d(hero.declared_remaining_days)} d declared.
            </div>
          </div>
          <span className="btn-primary shrink-0">Investigate <ArrowRight size={15} /></span>
        </button>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Kpi label="Total shipments" value={total.toLocaleString()} sub="IoT-tracked lots" icon={<Boxes size={16} />} />
        <Kpi label="At-risk shipments" value={k.at_risk_shipments.toLocaleString()} tone="warn" icon={<TriangleAlert size={16} />}
          sub={`${k.hold_shipments} on compliance hold`} />
        <Kpi label="Food saved (potential)" value={fmt.kg(k.food_saved_kg)} tone="good" icon={<Leaf size={16} />}
          sub="vs current routes, if plans accepted" />
        <Kpi label="Potential food waste" value={fmt.kg(k.potential_food_waste_kg)} tone="critical" icon={<TrendingDown size={16} />}
          sub="expected on current routes" />
        <Kpi label="Revenue recoverable" value={fmt.qarShort(k.revenue_recovered_qar)} tone="accent" icon={<CircleDollarSign size={16} />}
          sub="prototype calculation" />
        <Kpi label="Avg usable life (fresh)" value={`${fmt.d(k.avg_remaining_days_fresh)} d`} icon={<Clock size={16} />}
          sub={`vs ${fmt.d(k.avg_declared_remaining_days_fresh)} d declared`} />
      </div>

      <div className="grid xl:grid-cols-[1.55fr_1fr] gap-4">
        <Card title={<span className="flex items-center gap-2"><Radio size={14} className="text-good" /> Qatar cold-chain live</span>}
          right={<span className="text-[11px] text-muted">Click a shipment to open it</span>}>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {CLASSES.map((c) => {
              const on = visible.has(c);
              return (
                <button key={c} onClick={() => {
                  const n = new Set(visible); on ? n.delete(c) : n.add(c); setVisible(n);
                }}
                  className={clsx("flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium transition",
                    on ? "border-line bg-raised text-ink" : "border-dashed border-line text-muted opacity-60")}>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: pal[c] }} />
                  {CLASS_META[c].label} · {CLASS_META[c].action}
                  <span className="tabnum text-muted">{d.by_class[c]}</span>
                </button>
              );
            })}
          </div>
          <FleetMap points={d.map} visible={visible} height={430} />
          <div className="mt-3 flex h-2.5 w-full overflow-hidden rounded-full gap-[2px]" aria-label="Fleet status distribution">
            {CLASSES.map((c) => (
              <div key={c} style={{ width: `${(100 * d.by_class[c]) / total}%`, background: pal[c] }}
                title={`${CLASS_META[c].label}: ${d.by_class[c]}`} />
            ))}
          </div>
          <div className="mt-1.5 flex justify-between text-[11px] text-muted tabnum">
            {CLASSES.map((c) => <span key={c}>{CLASS_META[c].label} {((100 * d.by_class[c]) / total).toFixed(1)}%</span>)}
          </div>
        </Card>

        <Card title="Live alerts" right={<Link to="/shipments" className="text-[12px] text-accent">All shipments</Link>}
          bodyClass="!px-0">
          <ul className="divide-y divide-line max-h-[540px] overflow-y-auto">
            {d.alerts.map((a) => (
              <li key={a.id}>
                <Link to={`/shipments/${a.shipment_id}`} className="flex gap-3 px-4 py-2.5 hover:bg-page">
                  <TriangleAlert size={15} className={clsx("mt-0.5 shrink-0", SEV_TONE[a.severity])} />
                  <div className="min-w-0">
                    <div className="text-[13px] font-medium flex items-center gap-2">
                      {a.shipment_id}
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">{a.kind.replace("_", " ")}</span>
                      <span className={clsx("text-[10px] font-semibold uppercase", SEV_TONE[a.severity])}>{a.severity}</span>
                    </div>
                    <div className="text-[12px] text-ink2 leading-snug">{a.message}</div>
                    <div className="text-[11px] text-muted">{fmt.dt(a.ts)}</div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="What needs attention" right={<span className="text-[11px] text-muted">Rescuable lots first, then compliance holds · top 40 of {k.at_risk_shipments}</span>}
        bodyClass="!px-0 overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line">
            <tr>
              <th className="th pl-4">Shipment</th><th className="th">Product</th><th className="th text-right">Quantity</th>
              <th className="th">Remaining usable life</th><th className="th">Status</th><th className="th">Risk</th>
              <th className="th">Current location</th><th className="th">Recommended action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {d.attention.map((r) => (
              <tr key={r.shipment_id} onClick={() => nav(`/shipments/${r.shipment_id}`)}
                className={clsx("cursor-pointer hover:bg-page", r.featured && "bg-accent/[0.05]")}>
                <td className="td pl-4 font-semibold">{r.shipment_id}{r.featured && <span className="ml-1.5 chip bg-accent/12 text-accent">demo</span>}</td>
                <td className="td">{r.product}</td>
                <td className="td text-right tabnum">{fmt.kg(r.quantity_kg)}</td>
                <td className="td">
                  <LifeBar est={r.estimated_remaining_days} declared={r.declared_remaining_days} />
                </td>
                <td className="td"><ClassBadge c={r.classification} /></td>
                <td className="td"><RiskBadge r={r.risk_level} /></td>
                <td className="td text-ink2">{r.location}</td>
                <td className="td font-medium">{r.recommended_action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Exposure by product" bodyClass="!px-0 overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-line">
            <tr><th className="th pl-4">Product</th><th className="th text-right">Shipments</th><th className="th text-right">At risk</th>
              <th className="th text-right">Volume</th><th className="th">Avg usable life lost (vs declared remaining)</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {d.by_product.map((p) => (
              <tr key={p.product}>
                <td className="td pl-4 font-medium">{p.product}</td>
                <td className="td text-right tabnum">{p.shipments}</td>
                <td className="td text-right tabnum">{p.at_risk}</td>
                <td className="td text-right tabnum">{fmt.kg(p.kg)}</td>
                <td className="td">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-40 rounded-full bg-line overflow-hidden">
                      <div className="h-full rounded-full bg-serious" style={{ width: `${Math.min(100, p.avg_loss_pct)}%` }} />
                    </div>
                    <span className="tabnum text-[12px] text-ink2">{p.avg_loss_pct.toFixed(1)}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

export function LifeBar({ est, declared }: { est: number; declared: number }) {
  const pct = declared > 0 ? Math.max(0, Math.min(100, (100 * est) / declared)) : 0;
  return (
    <div className="flex items-center gap-2 min-w-[190px]" title={`${est.toFixed(1)} d usable of ${declared.toFixed(1)} d declared remaining`}>
      <div className="relative h-1.5 w-24 rounded-full bg-line overflow-hidden">
        <div className={clsx("h-full rounded-full", pct > 66 ? "bg-good" : pct > 33 ? "bg-warn" : "bg-critical")} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabnum text-sm font-semibold">{est.toFixed(1)} d</span>
      <span className="tabnum text-[11px] text-muted">/ {declared.toFixed(1)} d</span>
    </div>
  );
}
